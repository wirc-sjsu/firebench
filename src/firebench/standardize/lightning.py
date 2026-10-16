"""
Cloud-to-ground lightning in the FireBench standard file, and the strike counts it gives.

A stream is stored under ``/unstructured/lightning/<stream>`` with one table, ``strikes``, one row
per record: a cell of a grid on one period (``aggregation`` = ``cell_day``) or one stroke
(``aggregation`` = ``stroke``). Each row has a start and an end time, a position, and a number of
strikes, so a reader treats both the same way. Only strikes that reached the ground are stored.

- :func:`standardize_nldn_tiles` writes the stream ``nldn_tiles``: NCEI's daily counts of NLDN
  cloud-to-ground strikes per 0.1° cell (:mod:`firebench.acquisition.nldn_tiles`).
- :func:`standardize_lightning_strokes` writes the stream ``strokes`` from a CSV file of a lightning
  network, keeping its cloud-to-ground strokes.
- :func:`lightning_time_series` counts the strikes of a stream per time step.

Licence attributes are not written: the caller sets them.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import h5py
import hdf5plugin
import numpy as np
import pandas as pd

from ..acquisition.nldn_tiles import BASE_URL as NLDN_TILES_URL
from ..acquisition.nldn_tiles import CELL_SIZE as NLDN_CELL_SIZE
from ..acquisition.nldn_tiles import PRODUCT as NLDN_TILES_PRODUCT
from ..acquisition.nldn_tiles import NldnTiles
from ..tools.namespace import StandardVariableNames as svn
from .std_file_info import LIGHTNING, UNSTRUCTURED
from .tools import check_std_version

logger = logging.getLogger(__name__)

GROUP = f"/{UNSTRUCTURED}/{LIGHTNING}"
STRIKES = "strikes"
CRS = "EPSG:4326"
STREAMS = ("nldn_tiles", "strokes")
DAY_S = 86400
HOUR_S = 3600

# Values of a stroke-type column: a stroke to ground, or a discharge in the cloud.
GROUND_TYPES = frozenset({"G", "CG", "0", "GROUND", "CLOUD_TO_GROUND"})
CLOUD_TYPES = frozenset({"C", "IC", "1", "CLOUD", "INTRACLOUD", "INTRA_CLOUD"})
# Accepted column names of a stroke file, after lower-casing and stripping.
TIME_COLUMNS = ("time", "timestamp", "datetime", "date_time", "utc_time", "time_utc")
LAT_COLUMNS = ("latitude", "lat")
LON_COLUMNS = ("longitude", "lon", "long")
TYPE_COLUMNS = ("type", "cloud_ground", "stroke_type", "flash_type", "cg_ic", "discharge")
CURRENT_COLUMNS = ("peak_current", "peakcurrent", "peak_current_ka", "current_ka", "ka", "amplitude")


@dataclass(frozen=True)
class LightningSeries:
    """Strikes of a stream per time step: one entry per step of the stream's window, 0 without strike."""

    stream: str
    time: np.ndarray  # datetime64[ms], UTC: step start
    time_end: np.ndarray
    count: np.ndarray
    step_s: int


def list_lightning_streams(h5file: h5py.File) -> list[str]:
    """The lightning streams of a file, sorted; empty when the file has none."""
    group = h5file.get(GROUP)
    return sorted(group.keys()) if isinstance(group, h5py.Group) else []


def standardize_nldn_tiles(
    tiles: NldnTiles,
    h5file: h5py.File,
    *,
    overwrite: bool = False,
    compression_lvl: int = 6,
) -> h5py.Group:
    """
    Write the stream ``nldn_tiles``: one row per 0.1° cell and UTC day with at least one strike.

    ``time`` is the start of the cell's day and ``time_end`` its end, relative to the start of the
    first day that overlaps the window. A cell with no row had no strike that day. The group is
    written even when no cell has a strike: it says that the network saw none.
    """
    check_std_version(h5file)
    _check_new_group(h5file, "nldn_tiles", overwrite)
    first_day = np.datetime64(tiles.start.date(), "D")
    origin = datetime.combine(tiles.start.date(), datetime.min.time(), tzinfo=timezone.utc)
    starts = (tiles.day.astype("datetime64[D]") - first_day).astype(np.int64) * float(DAY_S)
    columns = _strike_columns(
        origin,
        starts,
        starts + DAY_S,
        tiles.lat,
        tiles.lon,
        tiles.count,
        position_note="cell centre",
    )
    attrs = {
        "network": "NLDN",
        "provider": "NOAA NCEI",
        "product": json.dumps([NLDN_TILES_PRODUCT]),
        "data_source": NLDN_TILES_URL,
        "discharge": "cloud_to_ground",
        "aggregation": "cell_day",
        "cell_size": float(NLDN_CELL_SIZE),
        "cell_size_units": "degree",
        "period": DAY_S,
        "period_units": "s",
        "complete": not tiles.missing,
        "missing": json.dumps(tiles.missing),
        "source_files": json.dumps(tiles.files),
        "description": (
            "Daily counts of Vaisala NLDN cloud-to-ground lightning strikes per 0.1 degree cell, from "
            "the NOAA NCEI Severe Weather Data Inventory"
        ),
    }
    group = _write_stream(
        h5file,
        "nldn_tiles",
        _frame_attrs(tiles.bbox, tiles.start, tiles.end) | attrs,
        columns,
        compression_lvl,
    )
    logger.info(
        "[lightning] nldn_tiles: %d strikes in %d cell-days", int(tiles.count.sum()), len(tiles.count)
    )
    return group


def standardize_lightning_strokes(
    csv_path: Path | str,
    h5file: h5py.File,
    *,
    bbox,
    start: datetime,
    end: datetime,
    network: str = "unknown",
    overwrite: bool = False,
    compression_lvl: int = 6,
) -> h5py.Group:
    """
    Write the stream ``strokes``: the cloud-to-ground strokes of a CSV file inside a box and window.

    The file has a header row. Its columns are found by name, whatever the case: the time
    (``time``, ``timestamp``, ``datetime``, or ``date`` and ``time``; UTC when no zone is given), the
    position (``latitude``/``lat``, ``longitude``/``lon``), the type of each stroke (``type``,
    ``cloud_ground``, ...: ``G``, ``CG``, or ``0`` for ground, ``C``, ``IC``, or ``1`` for cloud), and
    optionally the peak current in kA (``peak_current``, ``peakcurrent``, ``ka``, ...). Strokes in
    ``[start, end]`` whose position is in the box are kept; ``time_end`` equals ``time``.

    Raises
    ------
    ValueError
        If a column is missing (in particular the type, without which ground strokes cannot be told
        from cloud discharges), a type or time cannot be read, or the group exists and ``overwrite``
        is False.
    """
    check_std_version(h5file)
    _check_new_group(h5file, "strokes", overwrite)
    start, end = _utc(start), _utc(end)
    west, south, east, north = (float(value) for value in bbox)
    table = pd.read_csv(csv_path, dtype=str, skipinitialspace=True)
    table.columns = [str(name).strip().lower() for name in table.columns]

    lat_name = _column(table, LAT_COLUMNS, "latitude")
    lon_name = _column(table, LON_COLUMNS, "longitude")
    type_name = _column(
        table,
        TYPE_COLUMNS,
        "stroke type (cloud-to-ground or cloud); without it ground strokes cannot be told from "
        "cloud flashes",
    )
    times = _stroke_times(table)
    types = table[type_name].fillna("").str.strip().str.upper()
    unknown = sorted(set(types) - GROUND_TYPES - CLOUD_TYPES)
    if unknown:
        raise ValueError(f"unknown stroke types {unknown[:5]} in column {type_name!r}")
    try:
        lat = table[lat_name].astype(np.float64).to_numpy()
        lon = table[lon_name].astype(np.float64).to_numpy()
    except ValueError as error:
        raise ValueError(f"unreadable position: {error}") from None
    current_name = next((name for name in CURRENT_COLUMNS if name in table.columns), None)
    if current_name is None:
        current = np.full(len(table), np.nan)
    else:
        current = pd.to_numeric(
            table[current_name].str.replace("kA", "", case=False), errors="coerce"
        ).to_numpy(dtype=np.float64)

    stamps = times.to_numpy(dtype="datetime64[ms]")
    window_start = np.datetime64(start.replace(tzinfo=None), "ms")
    window_end = np.datetime64(end.replace(tzinfo=None), "ms")
    keep = (
        types.isin(GROUND_TYPES).to_numpy()
        & (stamps >= window_start)
        & (stamps <= window_end)
        & (lat >= south)
        & (lat <= north)
        & (lon >= west)
        & (lon <= east)
    )
    order = np.argsort(stamps[keep], kind="stable")
    seconds = (stamps[keep][order] - window_start).astype(np.float64) / 1000.0
    columns = _strike_columns(
        start,
        seconds,
        seconds,
        lat[keep][order],
        lon[keep][order],
        np.ones(int(keep.sum()), dtype=np.int64),
        position_note="stroke position",
    )
    columns[svn.LIGHTNING_PEAK_CURRENT.value] = (
        current[keep][order],
        {
            "units": "kA",
            "_FillValue": np.nan,
            "description": "Signed peak current; NaN when the file gives none",
        },
    )
    n_cloud = int(types.isin(CLOUD_TYPES).sum())
    attrs = {
        "network": network,
        "provider": network,
        "product": json.dumps(["strokes"]),
        "data_source": "file",
        "discharge": "cloud_to_ground",
        "aggregation": "stroke",
        "complete": True,
        "missing": json.dumps([]),
        "source_files": json.dumps(
            {"name": Path(csv_path).name, "rows": len(table), "cloud_rows_dropped": n_cloud}
        ),
        "description": f"Cloud-to-ground lightning strokes of the {network} network",
    }
    group = _write_stream(
        h5file,
        "strokes",
        _frame_attrs((west, south, east, north), start, end) | attrs,
        columns,
        compression_lvl,
    )
    logger.info("[lightning] strokes: %d ground strokes kept of %d rows", int(keep.sum()), len(table))
    return group


def lightning_time_series(
    h5file: h5py.File | Path | str, stream: str, step_s: int | None = None
) -> LightningSeries:
    """
    Strikes of a stream per time step, from the start of the window's first step to its end.

    Steps are aligned on 00 UTC. The default step is the stream's ``period`` (a day for the NLDN
    tiles), or an hour for strokes. A record is counted in the step its start falls in, so a step
    shorter than a record's period is refused.
    """
    if not isinstance(h5file, h5py.File):
        with h5py.File(h5file, "r") as opened:
            return lightning_time_series(opened, stream, step_s)
    group = h5file.get(f"{GROUP}/{stream}")
    if not isinstance(group, h5py.Group):
        raise ValueError(f"no lightning stream {stream!r}; the file has {list_lightning_streams(h5file)}")
    period = int(_scalar(group.attrs["period"])) if "period" in group.attrs else 0
    step_s = int(step_s or period or HOUR_S)
    if step_s <= 0 or DAY_S % step_s:
        raise ValueError(f"the step must divide a day, got {step_s} s")
    if period and step_s < period:
        raise ValueError(f"the step ({step_s} s) is shorter than the records of {stream} ({period} s)")

    window_start = _utc(datetime.fromisoformat(_text(group.attrs["time_start"])))
    window_end = _utc(datetime.fromisoformat(_text(group.attrs["time_end"])))
    first = _floor(window_start, step_s)
    last = _floor(window_end, step_s)
    if last == window_end and last > first:
        last -= timedelta(seconds=step_s)
    n_steps = int((last - first).total_seconds() // step_s) + 1

    strikes = group[STRIKES]
    stamps = _absolute_times(strikes[svn.TIME.value])
    offset = (stamps - np.datetime64(first.replace(tzinfo=None), "ms")).astype(np.int64) // 1000
    index = offset // step_s
    counts = strikes[svn.LIGHTNING_STROKE_COUNT.value][()].astype(np.int64)
    inside = (index >= 0) & (index < n_steps)
    count = np.bincount(index[inside], weights=counts[inside], minlength=n_steps).astype(np.int64)
    time = np.datetime64(first.replace(tzinfo=None), "ms") + np.arange(n_steps) * np.timedelta64(
        step_s, "s"
    )
    return LightningSeries(
        stream=stream,
        time=time,
        time_end=time + np.timedelta64(step_s, "s"),
        count=count,
        step_s=step_s,
    )


# Writing -------------------------------------------------------------------------------------------


def _strike_columns(origin: datetime, starts, ends, lat, lon, count, *, position_note: str) -> dict:
    time_attrs = {"units": "s", "time_origin": origin.isoformat(), "time_units": "s"}
    return {
        svn.TIME.value: (np.asarray(starts, dtype=np.float64), time_attrs),
        "time_end": (np.asarray(ends, dtype=np.float64), dict(time_attrs)),
        "position_lat": (
            np.asarray(lat, dtype=np.float64),
            {"units": "degree", "description": position_note},
        ),
        "position_lon": (
            np.asarray(lon, dtype=np.float64),
            {"units": "degree", "description": position_note},
        ),
        svn.LIGHTNING_STROKE_COUNT.value: (np.asarray(count, dtype=np.int64), {"units": "1"}),
    }


def _check_new_group(h5file: h5py.File, stream: str, overwrite: bool) -> None:
    if f"{GROUP}/{stream}" in h5file and not overwrite:
        raise ValueError(
            f"group {GROUP}/{stream} already exists in {h5file.filename}. Set `overwrite` to True."
        )


def _write_stream(h5file, stream, attrs, columns, compression_lvl) -> h5py.Group:
    path = f"{GROUP}/{stream}"
    if path in h5file:
        del h5file[path]
    # The parent groups carry no attribute, so fragments that each hold streams merge without conflict.
    group = h5file.require_group(f"/{UNSTRUCTURED}").require_group(LIGHTNING).create_group(stream)
    for name, value in attrs.items():
        group.attrs[name] = value
    table = group.create_group(STRIKES)
    for name, (data, dataset_attrs) in columns.items():
        data = np.asarray(data)
        # A filter needs chunks, and an empty dataset has none.
        options = hdf5plugin.Zstd(clevel=compression_lvl) if len(data) else {}
        dataset = table.create_dataset(
            name, data=data, fillvalue=dataset_attrs.get("_FillValue"), **options
        )
        for key, value in dataset_attrs.items():
            dataset.attrs[key] = value
    return group


def _column(table: pd.DataFrame, names, what: str) -> str:
    for name in names:
        if name in table.columns:
            return name
    raise ValueError(f"no column for the {what}; expected one of {', '.join(names)}")


def _stroke_times(table: pd.DataFrame) -> pd.Series:
    if "date" in table.columns and "time" in table.columns:
        text = table["date"].str.strip() + " " + table["time"].str.strip()
    else:
        text = table[_column(table, TIME_COLUMNS, "time")]
    try:
        return pd.to_datetime(text, utc=True, format="mixed")
    except (ValueError, TypeError) as error:
        raise ValueError(f"unreadable stroke time: {error}") from None


def _frame_attrs(frame, start: datetime, end: datetime) -> dict:
    west, south, east, north = frame
    attrs = {"crs": CRS, "time_start": _utc(start).isoformat(), "time_end": _utc(end).isoformat()}
    for name, value in (("west", west), ("south", south), ("east", east), ("north", north)):
        attrs[f"frame_{name}"] = float(value)
        attrs[f"frame_{name}_units"] = "degree"
    return attrs


def _floor(value: datetime, step_s: int) -> datetime:
    day = datetime.combine(value.date(), datetime.min.time(), tzinfo=timezone.utc)
    return day + timedelta(seconds=(int((value - day).total_seconds()) // step_s) * step_s)


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
