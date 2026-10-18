"""
Satellite fire detections in the FireBench standard file, and the fire radiative power (FRP) series
they give.

A stream is one satellite of one product family, stored under
``/unstructured/fire_detections/<stream>`` with two tables: ``detections`` (one row per fire pixel)
and ``observations`` (one row per time the sensor looked at the frame). Storing the observations
tells a time the sensor saw no fire (an FRP total of 0) from a time it did not look (no value):
see :func:`frp_time_series`.

- :func:`standardize_firms_bundle` writes the VIIRS and MODIS streams of a FIRMS bundle
  (:mod:`firebench.acquisition.firms`), with the overpasses found in NASA CMR.
- :func:`standardize_goes_fdc` writes one GOES stream from FDCC scans
  (:mod:`firebench.acquisition.goes_fdc`), read with h5py by :func:`read_fdc_file`.

Every detection the product reports is stored, with its product-native confidence; filtering is a
choice of the reader (``min_confidence``). Licence attributes are not written: the caller sets them.
"""

import hashlib
import io
import json
import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import h5py
import hdf5plugin
import numpy as np
import pandas as pd

from ..acquisition import firms as firms_acquisition
from ..acquisition.goes_fdc import PRODUCT as GOES_PRODUCT
from ..acquisition.goes_fdc import FetchedScan, scan_times
from ..tools.namespace import StandardVariableNames as svn
from .std_file_info import FIRE_DETECTIONS, UNSTRUCTURED
from .tools import check_std_version

logger = logging.getLogger(__name__)

GROUP = f"/{UNSTRUCTURED}/{FIRE_DETECTIONS}"
DETECTIONS = "detections"
OBSERVATIONS = "observations"
CRS = "EPSG:4326"

CONFIDENCE_LEVELS = ("low", "nominal", "high")
# FDC mask codes of a fire pixel, and of a pixel assessed and found clear
GOES_FIRE_CODES = (10, 11, 12, 13, 14, 15, 30, 31, 32, 33, 34, 35)
GOES_CLEAR_CODE = 100
_GOES_CLASSES = {
    0: (12, 15, 32, 35),  # cloud contaminated, low probability
    1: (14, 34),  # medium probability
    2: (10, 11, 13, 30, 31, 33),  # processed, saturated, high probability
}
_VIIRS_CONFIDENCE = {"l": 0, "n": 1, "h": 2}
# Length of a granule, for an observation rebuilt from detections FIRMS gives outside every overpass
_GRANULE_SECONDS = {"VIIRS": 360, "MODIS": 300}
# FIRMS gives the minute of a pixel, which can fall just outside the span of its granule
_MATCH_SLACK_S = 60

GOES_SATELLITES = {f"goes{number}": f"GOES-{number}" for number in (16, 17, 18, 19)}
STREAMS = (*firms_acquisition.STREAMS, *GOES_SATELLITES)


@dataclass(frozen=True)
class FdcScene:
    """The fire pixels of one FDCC scan inside a box, and how much of the box was assessed."""

    platform_id: str
    time_start: datetime
    time_end: datetime
    lat: np.ndarray
    lon: np.ndarray
    footprint_lat: np.ndarray  # (n, 4): SW, SE, NE, NW in scan-angle space
    footprint_lon: np.ndarray
    mask: np.ndarray  # FDC mask code of each fire pixel
    power: np.ndarray  # MW, NaN when filled
    temperature: np.ndarray  # K, NaN when filled
    n_pixels: int  # grid pixels whose centre is in the box
    n_assessed: int  # of those, the pixels the algorithm cleared or found burning

    @property
    def observed_fraction(self) -> float:
        """Share of the box's grid pixels the algorithm assessed; NaN when the box has none."""
        return self.n_assessed / self.n_pixels if self.n_pixels else math.nan


@dataclass(frozen=True)
class FrpSeries:
    """Total FRP of a stream at each observation."""

    stream: str
    time: np.ndarray  # datetime64[ms], UTC: observation start
    time_end: np.ndarray
    frp_total: np.ndarray  # MW; 0 without detection, NaN when every detection lacks FRP
    n_detections: np.ndarray
    observed_fraction: np.ndarray


def confidence_class(values, scale: str) -> np.ndarray:
    """
    Map product-native confidences to 0 (low), 1 (nominal), 2 (high), or -1 (none).

    ``viirs_lnh``: FIRMS ``l``, ``n``, ``h`` stored as 0, 1, 2. ``modis_percent``: 0–29 low, 30–79
    nominal, 80–100 high. ``goes_fdc_mask``: FDC mask codes 12, 15, 32, 35 low (cloud contaminated,
    low probability), 14, 34 nominal (medium probability), 10, 11, 13, 30, 31, 33 high (processed,
    saturated, high probability).
    """
    values = np.asarray(values, dtype=np.int64)
    classes = np.full(values.shape, -1, dtype=np.int8)
    if scale == "viirs_lnh":
        for level in (0, 1, 2):
            classes[values == level] = level
    elif scale == "modis_percent":
        classes[(values >= 0) & (values < 30)] = 0
        classes[(values >= 30) & (values < 80)] = 1
        classes[(values >= 80) & (values <= 100)] = 2
    elif scale == "goes_fdc_mask":
        for level, codes in _GOES_CLASSES.items():
            classes[np.isin(values, codes)] = level
    else:
        raise ValueError(f"unknown confidence scale {scale!r}")
    return classes


def list_fire_detection_streams(h5file: h5py.File) -> list[str]:
    """The fire detection streams of a file, sorted; empty when the file has none."""
    group = h5file.get(GROUP)
    return sorted(group.keys()) if isinstance(group, h5py.Group) else []


# FIRMS ---------------------------------------------------------------------------------------------


def standardize_firms_bundle(
    bundle_path: Path,
    h5file: h5py.File,
    streams: list[str] | None = None,
    overwrite: bool = False,
    compression_lvl: int = 6,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[h5py.Group]:
    """
    Write the VIIRS and MODIS streams of a FIRMS bundle to ``/unstructured/fire_detections``.

    One group per stream with at least one FIRMS request answered. VIIRS rows belong to the stream
    of their product; MODIS rows are split by the CSV ``satellite`` column. Rows identical in every
    column, and rows outside the window, are dropped.

    Observations are the bundle's CMR overpasses whose start is in the window. A detection belongs to
    the overpass whose span, widened by 60 s on each side, holds its time. A detection outside every
    overpass gets an observation of its own (its minute, the length of a granule, an unknown
    observed fraction), and the stream is marked ``observations_complete = False``; when the CMR
    search failed or found nothing, every observation is built that way and
    ``observation_source`` is ``detections``. A day FIRMS did not answer, or that no product covers,
    loses its observations and detections and is listed in ``failed``: it must never read as a pass
    with no fire.

    The window is the bundle's, or the part of it ``start`` and ``end`` give: rows, overpasses, and
    failed days outside it are left out, and the group records it as its ``time_start`` and
    ``time_end`` and as the origin of its times.

    Parameters
    ----------
    bundle_path : Path
        A bundle written by ``firebench.acquisition.firms.write_firms_bundle``.
    h5file : h5py.File
        Target standard file.
    streams : list[str] | None
        Streams to write, among the bundle's. None writes every stream of the bundle.
    overwrite : bool
        Replace a stream group that exists. Default: False
    compression_lvl : int
        Zstandard compression level of the datasets.
    start, end : datetime | None
        Part of the bundle's window to write, timezone-aware. None keeps the bundle's start or end.

    Returns
    -------
    list[h5py.Group]
        The stream groups written.

    Raises
    ------
    ValueError
        If the file is not a bundle, a stream is not in the bundle, a MODIS row has an unknown
        satellite code, a group exists and ``overwrite`` is False, or ``start`` and ``end`` do not
        give a part of the bundle's window.
    """
    check_std_version(h5file)
    bundle_path = Path(bundle_path)
    bundle = firms_acquisition.read_firms_bundle(bundle_path)
    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    wanted = list(bundle["streams"]) if streams is None else list(streams)
    missing = [stream for stream in wanted if stream not in bundle["streams"]]
    if missing:
        raise ValueError(f"streams {missing} are not in the bundle {bundle_path.name}: {bundle['streams']}")
    for stream in wanted:
        _check_new_group(h5file, stream, overwrite)

    first, last = _utc(datetime.fromisoformat(bundle["start"])), _utc(datetime.fromisoformat(bundle["end"]))
    start = first if start is None else _utc(start)
    end = last if end is None else _utc(end)
    if not first <= start < end <= last:
        raise ValueError(
            f"the window {start.isoformat()} to {end.isoformat()} is not a part of the bundle's, "
            f"{first.isoformat()} to {last.isoformat()}"
        )
    frame = tuple(float(value) for value in bundle["bbox"])
    frames = _firms_frames(bundle)
    written = []
    for stream in wanted:
        info = firms_acquisition.STREAMS[stream]
        requests = [request for request in bundle["requests"] if stream in request["streams"]]
        answered = [request for request in requests if request["status"] == "ok"]
        if not answered:
            logger.info("[fire detections] %s: no FIRMS request answered, no group written", stream)
            continue
        excluded = [
            item
            for item in _excluded_days(bundle, stream, requests)
            if start.date().isoformat() <= item["day"] <= end.date().isoformat()
        ]
        rows = frames.get(stream, pd.DataFrame())
        rows = _firms_rows_in_window(rows, start, end, {item["day"] for item in excluded})

        overpass_record = bundle["overpasses"].get(stream) or {"status": "failed", "items": []}
        overpasses = [
            firms_acquisition.overpass_from_dict(item) for item in overpass_record.get("items", [])
        ]
        overpasses = [
            item
            for item in overpasses
            if start <= item.time_start <= end
            and item.time_start.date().isoformat() not in {entry["day"] for entry in excluded}
        ]
        from_cmr = overpass_record.get("status") == "ok" and bool(overpasses)
        observations, index, rebuilt = _match_overpasses(
            rows["time"].to_numpy() if len(rows) else np.array([], dtype="datetime64[ns]"),
            overpasses if from_cmr else [],
            _GRANULE_SECONDS[info.instrument],
        )

        detections = _firms_detection_columns(rows, info.instrument)
        detections[svn.TIME.value] = (_seconds_since(rows["time"].to_numpy(), start), _time_attrs(start))
        detections["observation_index"] = (index.astype(np.int32), {"units": "1"})
        products = sorted({request["product"] for request in answered}, key=info.products.index)
        versions = sorted({str(value) for value in rows["version"].dropna()}) if "version" in rows else []
        attrs = {
            "satellite": info.satellite,
            "instrument": info.instrument,
            "provider": "NASA FIRMS",
            "product": json.dumps(products),
            "product_version": ";".join(versions),
            "data_source": firms_acquisition.AREA_CSV,
            "observation_source": "cmr" if from_cmr else "detections",
            "observations_complete": bool(from_cmr and not rebuilt and not excluded),
            "failed": json.dumps(excluded),
            "source_files": json.dumps(
                {
                    "firms_bundle_sha256": bundle_sha256,
                    "cmr_collections": list(overpass_record.get("collections") or []),
                }
            ),
            "description": f"{info.instrument} active fire detections of {info.satellite} from NASA FIRMS",
        }
        written.append(
            _write_stream(
                h5file,
                stream,
                _frame_attrs(frame, start, end) | attrs,
                detections,
                _observation_columns(observations, start, "swath"),
                compression_lvl,
            )
        )
        logger.info(
            "[fire detections] %s: %d detections, %d observations (%d rebuilt from detections)",
            stream,
            len(rows),
            len(observations),
            rebuilt,
        )
    return written


def _firms_frames(bundle: dict) -> dict[str, pd.DataFrame]:
    """The rows of the answered requests, per stream, without duplicates."""
    per_stream: dict[str, list[pd.DataFrame]] = {}
    for request in bundle["requests"]:
        if request["status"] != "ok" or not request.get("csv"):
            continue
        frame = pd.read_csv(
            io.StringIO(request["csv"]),
            dtype={"acq_date": str, "acq_time": str, "satellite": str, "confidence": str, "daynight": str},
            keep_default_na=False,
            na_values=[""],
        )
        if frame.empty:
            continue
        frame["product"] = request["product"]
        if len(request["streams"]) == 1:
            per_stream.setdefault(request["streams"][0], []).append(frame)
            continue
        codes = frame["satellite"].astype(str).str.strip().str.upper()
        known = set()
        for stream in request["streams"]:
            stream_codes = firms_acquisition.STREAMS[stream].csv_satellites
            known |= set(stream_codes)
            selected = frame[codes.isin(stream_codes)]
            if len(selected):
                per_stream.setdefault(stream, []).append(selected)
        unknown = sorted(set(codes) - known)
        if unknown:
            raise ValueError(
                f"FIRMS rows of {request['product']} have satellite codes {unknown}, "
                f"none of {', '.join(request['streams'])}"
            )
    frames = {}
    for stream, parts in per_stream.items():
        frame = pd.concat(parts, ignore_index=True)
        before = len(frame)
        frame = frame.drop_duplicates(subset=[column for column in frame.columns if column != "product"])
        if len(frame) < before:
            logger.info("[fire detections] %s: %d duplicate rows dropped", stream, before - len(frame))
        frames[stream] = frame.reset_index(drop=True)
    return frames


def _excluded_days(bundle: dict, stream: str, requests: list[dict]) -> list[dict]:
    """Days without a FIRMS answer for a stream: failed requests, and days no product covers."""
    excluded = {}
    for request in requests:
        if request["status"] == "ok":
            continue
        first = date.fromisoformat(request["day"])
        for offset in range(int(request["n_days"])):
            day = (first + timedelta(days=offset)).isoformat()
            excluded[day] = {"day": day, "reason": f"request failed: {request.get('error') or 'unknown'}"}
    for day in (bundle.get("uncovered_days") or {}).get(stream, []):
        excluded.setdefault(day, {"day": day, "reason": "no FIRMS product covers the day"})
    return [excluded[day] for day in sorted(excluded)]


def _firms_rows_in_window(
    rows: pd.DataFrame, start: datetime, end: datetime, excluded: set[str]
) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame({"time": pd.Series(dtype="datetime64[ns]")})
    acq_time = rows["acq_time"].astype(str).str.strip().str.zfill(4)
    times = pd.to_datetime(
        rows["acq_date"].astype(str).str.strip() + " " + acq_time.str[:2] + ":" + acq_time.str[2:],
        format="%Y-%m-%d %H:%M",
        utc=True,
    )
    rows = rows.assign(time=times.dt.tz_localize(None))
    keep = (times >= pd.Timestamp(start)) & (times <= pd.Timestamp(end))
    keep &= ~rows["acq_date"].astype(str).str.strip().isin(excluded)
    return rows[keep.to_numpy()].sort_values("time", kind="stable").reset_index(drop=True)


def _firms_detection_columns(rows: pd.DataFrame, instrument: str) -> dict:
    """The detection datasets of FIRMS rows, except time and observation index."""

    def number(name: str) -> np.ndarray:
        if name not in rows or rows.empty:
            return np.full(len(rows), np.nan)
        return pd.to_numeric(rows[name], errors="coerce").to_numpy(dtype=np.float64)

    def text(name: str) -> pd.Series:
        if name not in rows or rows.empty:
            return pd.Series([""] * len(rows), dtype=object)
        return rows[name].astype(str).str.strip()

    if instrument == "VIIRS":
        confidence = text("confidence").str.lower().map(_VIIRS_CONFIDENCE).fillna(-1)
        scale, mir, tir = "viirs_lnh", number("bright_ti4"), number("bright_ti5")
    else:
        confidence = pd.Series(np.nan_to_num(number("confidence"), nan=-1.0))
        scale, mir, tir = "modis_percent", number("brightness"), number("bright_t31")
    daynight = text("daynight").str.upper().to_numpy()
    day_night = np.where(daynight == "D", 1, np.where(daynight == "N", 0, -1)).astype(np.int8)
    return {
        "position_lat": (number("latitude"), {"units": "degree"}),
        "position_lon": (number("longitude"), {"units": "degree"}),
        svn.FIRE_RADIATIVE_POWER.value: (number("frp"), {"units": "MW"}),
        svn.FIRE_DETECTION_CONFIDENCE.value: (
            confidence.to_numpy(dtype=np.int16),
            {"units": "1", "confidence_scale": scale, "_FillValue": np.int16(-1)},
        ),
        svn.BRIGHTNESS_TEMPERATURE_MIR.value: (mir, {"units": "K"}),
        svn.BRIGHTNESS_TEMPERATURE_TIR.value: (tir, {"units": "K"}),
        svn.PIXEL_SIZE_SCAN.value: (number("scan") * 1000.0, {"units": "m"}),
        svn.PIXEL_SIZE_TRACK.value: (number("track") * 1000.0, {"units": "m"}),
        svn.DAY_NIGHT_FLAG.value: (day_night, {"units": "1", "_FillValue": np.int8(-1)}),
    }


def _match_overpasses(times: np.ndarray, overpasses: list, granule_seconds: int):
    """
    Observations and the observation index of each detection.

    Returns ``(observations, index, rebuilt)``: observations as ``(start, end, granule_ids,
    observed_fraction)`` sorted by start, the row of each detection, and how many observations were
    rebuilt from detections.
    """
    rows = [
        (
            np.datetime64(item.time_start.replace(tzinfo=None), "ms"),
            np.datetime64(item.time_end.replace(tzinfo=None), "ms"),
            ";".join(item.granule_ids),
            item.observed_fraction,
        )
        for item in overpasses
    ]
    rows.sort(key=lambda row: row[0])
    times = times.astype("datetime64[ms]")
    slack = np.timedelta64(_MATCH_SLACK_S, "s")
    owner = np.full(len(times), -1, dtype=np.int64)
    if rows:
        starts = np.array([row[0] for row in rows])
        ends = np.array([row[1] for row in rows])
        candidate = np.searchsorted(starts - slack, times, side="right") - 1
        valid = candidate >= 0
        hit = valid.copy()
        hit[valid] = times[valid] <= ends[candidate[valid]] + slack
        owner[hit] = candidate[hit]
    unmatched = sorted(set(times[owner < 0].tolist()))
    rebuilt = len(unmatched)
    for minute in unmatched:
        stamp = np.datetime64(minute, "ms")
        rows.append((stamp, stamp + np.timedelta64(granule_seconds, "s"), "", math.nan))
    order = sorted(range(len(rows)), key=lambda position: (rows[position][0], position))
    new_position = {old: new for new, old in enumerate(order)}
    observations = [rows[position] for position in order]
    if rebuilt:
        first_rebuilt = len(rows) - rebuilt
        by_minute = {
            np.datetime64(minute, "ms"): first_rebuilt + offset for offset, minute in enumerate(unmatched)
        }
        for position in np.nonzero(owner < 0)[0]:
            owner[position] = by_minute[times[position]]
    index = np.array([new_position[int(position)] for position in owner], dtype=np.int64)
    return observations, index, rebuilt


# GOES ----------------------------------------------------------------------------------------------


def read_fdc_file(path: Path, bbox) -> FdcScene:
    """
    Read the fire pixels of an ABI FDC file inside ``bbox`` (west, south, east, north), with h5py.

    The netCDF packing is applied by hand: ``scale_factor``, ``add_offset``, ``_FillValue``,
    ``valid_range``, and ``_Unsigned``, as netCDF4 does. Pixel positions invert the geostationary
    fixed-grid projection over the part of the grid that covers the box. A fire pixel has one of the
    FDC fire codes (10 to 15, 30 to 35); every one is kept. The corners of a pixel are half a grid
    step away in scan angle, in the order SW, SE, NE, NW.
    """
    import pyproj  # pylint: disable=import-outside-toplevel

    west, south, east, north = (float(value) for value in bbox)
    path = Path(path)
    time_start, time_end = scan_times(path.name)
    with h5py.File(path, "r") as nc:
        x_grid = _unpack(nc["x"], ())
        y_grid = _unpack(nc["y"], ())
        projection = nc["goes_imager_projection"].attrs
        height = float(_scalar(projection["perspective_point_height"]))
        proj = pyproj.Proj(
            proj="geos",
            h=height,
            lon_0=float(_scalar(projection["longitude_of_projection_origin"])),
            sweep=_text(projection["sweep_angle_axis"]),
            a=float(_scalar(projection["semi_major_axis"])),
            b=float(_scalar(projection["semi_minor_axis"])),
        )
        platform_id = _text(nc.attrs.get("platform_ID", b""))
        rows, cols = _grid_window(proj, height, x_grid, y_grid, (west, south, east, north))
        if rows.stop - rows.start <= 0 or cols.stop - cols.start <= 0:
            mask = np.zeros((0, 0), dtype=np.int64)
            power = temperature = np.zeros((0, 0))
        else:
            mask = _unpack(nc["Mask"], (rows, cols), integer=True)
            power = _unpack(nc["Power"], (rows, cols))
            temperature = _unpack(nc["Temp"], (rows, cols))

    xs, ys = x_grid[cols], y_grid[rows]
    xx, yy = np.meshgrid(xs, ys)
    lon, lat = _inverse(proj, xx * height, yy * height)
    finite = np.isfinite(lon) & np.isfinite(lat) & (np.abs(lon) < 1e10)
    in_box = finite & (lon >= west) & (lon <= east) & (lat >= south) & (lat <= north)
    fire = np.isin(mask, GOES_FIRE_CODES)
    assessed = in_box & (fire | (mask == GOES_CLEAR_CODE))
    selected = in_box & fire

    dx2 = abs(float(x_grid[1] - x_grid[0])) / 2 if len(x_grid) > 1 else 0.0
    dy2 = abs(float(y_grid[1] - y_grid[0])) / 2 if len(y_grid) > 1 else 0.0
    xc, yc = xx[selected], yy[selected]
    corners_lon, corners_lat = [], []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        clon, clat = _inverse(proj, (xc + sx * dx2) * height, (yc + sy * dy2) * height)
        corners_lon.append(clon)
        corners_lat.append(clat)
    order = np.lexsort((lon[selected], lat[selected]))
    return FdcScene(
        platform_id=platform_id,
        time_start=time_start,
        time_end=time_end,
        lat=lat[selected][order],
        lon=lon[selected][order],
        footprint_lat=np.column_stack(corners_lat).reshape(-1, 4)[order],
        footprint_lon=np.column_stack(corners_lon).reshape(-1, 4)[order],
        mask=mask[selected].astype(np.int16)[order],
        power=power[selected][order],
        temperature=temperature[selected][order],
        n_pixels=int(in_box.sum()),
        n_assessed=int(assessed.sum()),
    )


def standardize_goes_fdc(
    scans: Iterable[FetchedScan],
    h5file: h5py.File,
    *,
    bbox,
    start: datetime,
    end: datetime,
    time_step_min: int,
    overwrite: bool = False,
    compression_lvl: int = 6,
) -> h5py.Group:
    """
    Write one GOES stream, ``goes{NN}``, from the FDCC scans of one bucket.

    Each scan read is an observation: its start and end, its S3 key and SHA-256, and the share of the
    box's grid pixels the algorithm assessed (``observed_fraction``, method ``assessed_pixels``).
    A scan that could not be fetched or read is no observation; its key is in ``failed``. Scans whose
    start is outside ``[start, end]`` are skipped. The iterable is consumed once, scan by scan, so it
    may delete each file after it is read (``fetch_fdc_scans``).

    Raises
    ------
    ValueError
        If the scans come from several buckets, no scan could be read, or the group exists and
        ``overwrite`` is False.
    """
    check_std_version(h5file)
    start, end = _utc(start), _utc(end)
    frame = tuple(float(value) for value in bbox)
    bucket, failed = None, []
    observations, parts = [], []
    for fetched in scans:
        if bucket is None:
            bucket = fetched.scan.bucket
            stream = f"goes{bucket.removeprefix('noaa-goes')}"
            if stream not in GOES_SATELLITES:
                raise ValueError(f"unknown GOES bucket {bucket!r}")
            _check_new_group(h5file, stream, overwrite)
        elif fetched.scan.bucket != bucket:
            raise ValueError(f"scans of {bucket} and {fetched.scan.bucket} cannot share one stream")
        if not start <= fetched.scan.time_start <= end:
            continue
        if fetched.path is None:
            failed.append({"key": fetched.scan.key, "reason": fetched.error or "not fetched"})
            continue
        try:
            scene = read_fdc_file(fetched.path, frame)
        except (OSError, KeyError, ValueError) as error:
            failed.append({"key": fetched.scan.key, "reason": f"unreadable: {error}"})
            continue
        position = len(observations)
        observations.append((fetched.scan, fetched.sha256, scene.observed_fraction))
        parts.append((position, scene))
    if bucket is None or not observations:
        raise ValueError(f"no GOES scan could be read{f' from {bucket}' if bucket else ''}")

    count = sum(len(scene.lat) for _, scene in parts)

    def concat(name: str, dtype) -> np.ndarray:
        return np.concatenate([getattr(scene, name) for _, scene in parts]).astype(dtype)

    det_times = np.concatenate(
        [
            np.full(len(scene.lat), np.datetime64(scene.time_start.replace(tzinfo=None), "ms"))
            for _, scene in parts
        ]
    )
    index = np.concatenate([np.full(len(scene.lat), position, dtype=np.int32) for position, scene in parts])
    detections = {
        svn.TIME.value: (_seconds_since(det_times, start), _time_attrs(start)),
        "position_lat": (concat("lat", np.float64), {"units": "degree"}),
        "position_lon": (concat("lon", np.float64), {"units": "degree"}),
        svn.FIRE_RADIATIVE_POWER.value: (concat("power", np.float64), {"units": "MW"}),
        svn.FIRE_DETECTION_CONFIDENCE.value: (
            concat("mask", np.int16),
            {"units": "1", "confidence_scale": "goes_fdc_mask", "_FillValue": np.int16(-1)},
        ),
        svn.FIRE_TEMPERATURE.value: (concat("temperature", np.float64), {"units": "K"}),
        svn.FOOTPRINT_LAT.value: (concat("footprint_lat", np.float64), {"units": "degree"}),
        svn.FOOTPRINT_LON.value: (concat("footprint_lon", np.float64), {"units": "degree"}),
        svn.DAY_NIGHT_FLAG.value: (
            np.full(count, -1, dtype=np.int8),
            {"units": "1", "_FillValue": np.int8(-1)},
        ),
        "observation_index": (index, {"units": "1"}),
    }
    observation_rows = [
        (
            np.datetime64(scan.time_start.replace(tzinfo=None), "ms"),
            np.datetime64(scan.time_end.replace(tzinfo=None), "ms"),
            None,
            fraction,
        )
        for scan, _, fraction in observations
    ]
    observation_columns = _observation_columns(observation_rows, start, "assessed_pixels")
    observation_columns["source_key"] = (
        np.array([scan.key for scan, _, _ in observations], dtype=object),
        {},
    )
    observation_columns["source_sha256"] = (np.array([sha for _, sha, _ in observations], dtype=object), {})
    satellite = GOES_SATELLITES[stream]
    attrs = {
        "satellite": satellite,
        "instrument": "ABI",
        "provider": "NOAA",
        "product": json.dumps([GOES_PRODUCT]),
        "data_source": f"s3://{bucket}/{GOES_PRODUCT}",
        "observation_source": "goes_scans",
        "observations_complete": not failed,
        "failed": json.dumps(failed),
        "time_step": int(time_step_min),
        "time_step_units": "min",
        "source_files": json.dumps({"bucket": bucket, "scans": len(observations)}),
        "description": f"ABI fire detections of {satellite} (FDC, CONUS) from the NOAA archive on AWS",
    }
    group = _write_stream(
        h5file,
        stream,
        _frame_attrs(frame, start, end) | attrs,
        detections,
        observation_columns,
        compression_lvl,
    )
    logger.info(
        "[fire detections] %s: %d detections in %d scans, %d failed",
        stream,
        count,
        len(observations),
        len(failed),
    )
    return group


def _unpack(dataset: h5py.Dataset, selection, integer: bool = False) -> np.ndarray:
    """Read a netCDF variable as netCDF4 would: masked values become NaN (or -1 for integers)."""
    raw = dataset[selection] if selection != () else dataset[()]
    raw = np.asarray(raw)
    attrs = dataset.attrs
    if _text(attrs.get("_Unsigned", b"")).lower() == "true" and raw.dtype.kind == "i":
        raw = raw.view(raw.dtype.str.replace("i", "u"))
    invalid = np.zeros(raw.shape, dtype=bool)
    if "_FillValue" in attrs:
        invalid |= raw == np.asarray(attrs["_FillValue"]).astype(raw.dtype).reshape(-1)[0]
    if "valid_range" in attrs:
        low, high = np.asarray(attrs["valid_range"]).astype(raw.dtype)[:2]
        invalid |= (raw < low) | (raw > high)
    if integer and "scale_factor" not in attrs and "add_offset" not in attrs:
        values = raw.astype(np.int64)
        values[invalid] = -1
        return values
    # CF: packed values unpack in the type of scale_factor and add_offset (float32 in FDC files), as
    # netCDF4 does; computing in float64 would move positions by about a metre from other readers.
    packing = [
        np.asarray(attrs[name]).reshape(-1)[:1] for name in ("scale_factor", "add_offset") if name in attrs
    ]
    unpacked = np.result_type(*packing) if packing else np.float64
    values = raw.astype(unpacked)
    if "scale_factor" in attrs:
        values = values * np.asarray(attrs["scale_factor"]).reshape(-1)[0]
    if "add_offset" in attrs:
        values = values + np.asarray(attrs["add_offset"]).reshape(-1)[0]
    values = values.astype(np.float64)
    values[invalid] = np.nan
    return values


def _inverse(proj, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Inverse projection of arrays of any size; pyproj takes a one-element array for a point."""
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    if x.size != 1:
        lon, lat = proj(x, y, inverse=True)
        return np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)
    lon, lat = proj(np.repeat(x.reshape(-1), 2), np.repeat(y.reshape(-1), 2), inverse=True)
    return np.asarray(lon)[:1].reshape(x.shape), np.asarray(lat)[:1].reshape(y.shape)


def _grid_window(proj, height: float, x_grid: np.ndarray, y_grid: np.ndarray, box, pad: int = 2):
    """Row and column slices of the fixed grid that cover the box (spear's ``fixed_grid_window``)."""
    west, south, east, north = box
    edge = np.linspace(0.0, 1.0, 21)
    lon = np.concatenate(
        [west + (east - west) * edge, np.full(21, east), east - (east - west) * edge, np.full(21, west)]
    )
    lat = np.concatenate(
        [
            np.full(21, south),
            south + (north - south) * edge,
            np.full(21, north),
            north - (north - south) * edge,
        ]
    )
    xs, ys = proj(lon, lat)
    xs, ys = np.asarray(xs, dtype=float) / height, np.asarray(ys, dtype=float) / height
    on_disk = np.isfinite(xs) & np.isfinite(ys) & (np.abs(xs) < 1e10) & (np.abs(ys) < 1e10)
    if not on_disk.any():
        return slice(0, 0), slice(0, 0)
    rows = np.nonzero((y_grid >= ys[on_disk].min()) & (y_grid <= ys[on_disk].max()))[0]
    cols = np.nonzero((x_grid >= xs[on_disk].min()) & (x_grid <= xs[on_disk].max()))[0]
    if rows.size == 0 or cols.size == 0:
        return slice(0, 0), slice(0, 0)
    return (
        slice(max(0, rows.min() - pad), min(len(y_grid), rows.max() + 1 + pad)),
        slice(max(0, cols.min() - pad), min(len(x_grid), cols.max() + 1 + pad)),
    )


# The FRP series --------------------------------------------------------------------------------------


def frp_time_series(
    h5file: h5py.File | Path | str,
    stream: str,
    start: datetime | None = None,
    end: datetime | None = None,
    corners=None,
    min_confidence: Literal["low", "nominal", "high"] | None = None,
) -> FrpSeries:
    """
    Total fire radiative power of a stream at each observation.

    One entry per observation whose start is in ``[start, end]``; a time the sensor did not look at
    has no entry. ``frp_total`` is the sum of the FRP of the detections kept: 0 when none is kept,
    NaN when some are kept and every one lacks FRP. A missing FRP is left out of a sum that has
    others.

    Parameters
    ----------
    h5file : h5py.File | Path | str
        A standard file, open or by path.
    stream : str
        A stream of ``list_fire_detection_streams``.
    start, end : datetime | None
        Aware datetimes bounding the observation starts. None: unbounded.
    corners : tuple | None
        ``((lat, lon), (lat, lon))``: keep the detections inside. ``observed_fraction`` still
        describes the stream's frame.
    min_confidence : "low" | "nominal" | "high" | None
        Keep the detections of at least this confidence class (see :func:`confidence_class`). None
        keeps every detection.
    """
    if not isinstance(h5file, h5py.File):
        with h5py.File(h5file, "r") as opened:
            return frp_time_series(opened, stream, start, end, corners, min_confidence)
    if min_confidence is not None and min_confidence not in CONFIDENCE_LEVELS:
        raise ValueError(
            f"min_confidence must be one of {CONFIDENCE_LEVELS} or None, got {min_confidence!r}"
        )
    group = h5file.get(f"{GROUP}/{stream}")
    if not isinstance(group, h5py.Group):
        raise ValueError(
            f"no fire detection stream {stream!r}; the file has {list_fire_detection_streams(h5file)}"
        )

    observations, detections = group[OBSERVATIONS], group[DETECTIONS]
    obs_start = _absolute_times(observations[svn.TIME.value])
    obs_end = _absolute_times(observations["time_end"])
    fraction = observations[svn.OBSERVED_FRACTION.value][()].astype(np.float64)
    keep_obs = np.ones(len(obs_start), dtype=bool)
    if start is not None:
        keep_obs &= obs_start >= np.datetime64(_utc(start).replace(tzinfo=None), "ms")
    if end is not None:
        keep_obs &= obs_start <= np.datetime64(_utc(end).replace(tzinfo=None), "ms")

    frp = detections[svn.FIRE_RADIATIVE_POWER.value][()].astype(np.float64)
    owner = detections["observation_index"][()].astype(np.int64)
    keep = np.ones(len(frp), dtype=bool)
    if min_confidence is not None:
        confidence = detections[svn.FIRE_DETECTION_CONFIDENCE.value]
        classes = confidence_class(confidence[()], _text(confidence.attrs["confidence_scale"]))
        keep &= classes >= CONFIDENCE_LEVELS.index(min_confidence)
    if corners is not None:
        (lat_a, lon_a), (lat_b, lon_b) = corners
        lat, lon = detections["position_lat"][()], detections["position_lon"][()]
        keep &= (lat >= min(lat_a, lat_b)) & (lat <= max(lat_a, lat_b))
        keep &= (lon >= min(lon_a, lon_b)) & (lon <= max(lon_a, lon_b))

    size = len(obs_start)
    count = np.bincount(owner[keep], minlength=size)[:size]
    with_frp = keep & np.isfinite(frp)
    total = np.bincount(owner[with_frp], weights=frp[with_frp], minlength=size)[:size]
    n_with_frp = np.bincount(owner[with_frp], minlength=size)[:size]
    total = np.where(count == 0, 0.0, np.where(n_with_frp == 0, np.nan, total))
    return FrpSeries(
        stream=stream,
        time=obs_start[keep_obs],
        time_end=obs_end[keep_obs],
        frp_total=total[keep_obs],
        n_detections=count[keep_obs],
        observed_fraction=fraction[keep_obs],
    )


# Writing -------------------------------------------------------------------------------------------


def _check_new_group(h5file: h5py.File, stream: str, overwrite: bool) -> None:
    if stream not in STREAMS:
        raise ValueError(f"unknown fire detection stream {stream!r}; known: {', '.join(STREAMS)}")
    if f"{GROUP}/{stream}" in h5file and not overwrite:
        raise ValueError(
            f"group {GROUP}/{stream} already exists in {h5file.filename}. Set `overwrite` to True."
        )


def _write_stream(h5file, stream, attrs, detections, observations, compression_lvl) -> h5py.Group:
    path = f"{GROUP}/{stream}"
    if path in h5file:
        del h5file[path]
    # The parent groups carry no attribute, so fragments that each hold streams merge without conflict.
    group = h5file.require_group(f"/{UNSTRUCTURED}").require_group(FIRE_DETECTIONS).create_group(stream)
    for name, value in attrs.items():
        group.attrs[name] = value
    for table_name, columns in ((DETECTIONS, detections), (OBSERVATIONS, observations)):
        table = group.create_group(table_name)
        for name, (data, dataset_attrs) in columns.items():
            data = np.asarray(data)
            dtype = h5py.string_dtype() if data.dtype == object else data.dtype
            values = data.astype(object) if data.dtype == object else data
            if data.dtype == object:
                values = np.array(
                    ["" if item is None else str(item) for item in values.reshape(-1)], dtype=object
                )
            fill = dataset_attrs.get("_FillValue")
            dataset = table.create_dataset(
                name,
                data=values,
                dtype=dtype,
                fillvalue=fill,
                **hdf5plugin.Zstd(clevel=compression_lvl),
            )
            for key, value in dataset_attrs.items():
                dataset.attrs[key] = value
    return group


def _observation_columns(rows, origin: datetime, method: str) -> dict:
    starts = np.array([row[0] for row in rows], dtype="datetime64[ms]")
    ends = np.array([row[1] for row in rows], dtype="datetime64[ms]")
    columns = {
        svn.TIME.value: (_seconds_since(starts, origin), _time_attrs(origin)),
        "time_end": (_seconds_since(ends, origin), _time_attrs(origin)),
        svn.OBSERVED_FRACTION.value: (
            np.array([row[3] for row in rows], dtype=np.float64),
            {"units": "1", "method": method},
        ),
    }
    if method == "swath":
        columns["granule_ids"] = (np.array([row[2] or "" for row in rows], dtype=object), {})
    return columns


def _frame_attrs(frame, start: datetime, end: datetime) -> dict:
    west, south, east, north = frame
    attrs = {"crs": CRS, "time_start": start.isoformat(), "time_end": end.isoformat()}
    for name, value in (("west", west), ("south", south), ("east", east), ("north", north)):
        attrs[f"frame_{name}"] = float(value)
        attrs[f"frame_{name}_units"] = "degree"
    return attrs


def _time_attrs(origin: datetime) -> dict:
    return {"units": "s", "time_origin": origin.isoformat(), "time_units": "s"}


def _seconds_since(times: np.ndarray, origin: datetime) -> np.ndarray:
    stamp = np.datetime64(_utc(origin).replace(tzinfo=None), "ms")
    return (np.asarray(times, dtype="datetime64[ms]") - stamp).astype(np.float64) / 1000.0


def _absolute_times(dataset: h5py.Dataset) -> np.ndarray:
    origin = _utc(datetime.fromisoformat(_text(dataset.attrs["time_origin"])))
    seconds = dataset[()].astype(np.float64)
    return np.datetime64(origin.replace(tzinfo=None), "ms") + np.round(seconds * 1000).astype(
        "timedelta64[ms]"
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{value!r} has no time zone")
    return value.astimezone(timezone.utc)


def _scalar(value):
    return np.asarray(value).reshape(-1)[0]


def _text(value) -> str:
    if isinstance(value, np.ndarray):
        value = value.reshape(-1)[0] if value.size else b""
    return value.decode() if isinstance(value, (bytes, np.bytes_)) else str(value)
