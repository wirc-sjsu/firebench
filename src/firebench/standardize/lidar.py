"""
Doppler wind lidar scans in the FireBench standard file, and the points they give.

An instrument is stored under ``/spatial_3d/lidar/<INSTRUMENT>`` the way it observed: one row per
ray (time, azimuth, elevation), a fixed axis of gate ranges, and one row per scan file in
``scans/``. Nothing is gridded or filtered at standardization; a reader applies the heading of the
instrument and the quality thresholds of ``resources/lidar.toml``.

- :func:`read_halo_hpl` reads a raw scan of a Halo Photonics StreamLine lidar (``.hpl``), and
  :func:`read_halo_time_sync` the GPS fixes of its ``Time_Sync`` file.
- :func:`standardize_halo_lidar` writes the scans of one or more instruments.
- :func:`lidar_scans` lists the scans of an instrument, and :func:`lidar_points` gives the gates of
  one scan that pass the quality thresholds, as east, north, and up from the lidar.

Licence attributes are not written: the caller sets them.
"""

import hashlib
import json
import logging
import math
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Literal

import h5py
import hdf5plugin
import numpy as np

from ..tools.namespace import StandardVariableNames as svn
from .std_file_info import LIDAR, SPATIAL_3D
from .tools import check_std_version

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

logger = logging.getLogger(__name__)

GROUP = f"/{SPATIAL_3D}/{LIDAR}"
SCANS = "scans"
CRS = "EPSG:4326"
PARAMETER_FILE = "resources/lidar.toml"

FIELDS = (
    (svn.LIDAR_RADIAL_VELOCITY.value, "m/s", "Doppler velocity, positive away from the lidar"),
    (svn.LIDAR_INTENSITY.value, "1", "Signal-to-noise ratio plus one"),
    (svn.LIDAR_ATTENUATED_BACKSCATTER.value, "1/m/sr", "Attenuated backscatter coefficient"),
)

# The two kinds of file of a Halo lidar this module reads, told by their first bytes.
_HPL_HEAD = "Filename:"
_TIME_SYNC_HEAD = "Time before:"
_HEAD_BYTES = 4096
# Rays whose azimuths and elevations each span less than this point the same way (a stare), as do
# rays all within this of the zenith, whatever their azimuth.
_SAME_DIRECTION_DEG = 0.05

_FIX = re.compile(
    r"Time before:\s*\*(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)\*"
    r".*?Satellites in view:\s*\*(?P<satellites>\d+)\*"
    r".*?Lat:\s*(?P<lat_deg>\d+)\s+(?P<lat_min>\d+)'\s+(?P<lat_sec>[\d.]+)\"(?P<lat_hem>[NS])"
    r".*?Long:\s*(?P<lon_deg>\d+)\s+(?P<lon_min>\d+)'\s+(?P<lon_sec>[\d.]+)\"(?P<lon_hem>[EW])"
    r".*?Height \(m\):\s*\*(?P<height>-?[\d.]+)"
)


@dataclass(frozen=True)
class LidarParameters:
    """The values of ``resources/lidar.toml``."""

    max_fix_gap_h: float
    snr_min_db: float
    backscatter_min: float
    radial_velocity_max_abs: float
    sha256: str


@dataclass
class HaloScan:  # pylint: disable=too-many-instance-attributes
    """A raw ``.hpl`` scan as read: its header, its rays, and its gates."""

    filename: str
    system_id: int
    scan_type: str
    start: datetime
    gate_length: float  # m, the range gate length of the header
    gate_points: int
    gate_spacing: float  # m between gate centres
    focus_range: float | None
    pulses_per_ray: int | None
    velocity_resolution: float | None
    time: list[datetime]  # one per ray, UTC
    azimuth: np.ndarray  # degree, as recorded by the instrument
    elevation: np.ndarray
    pitch: np.ndarray
    roll: np.ndarray
    radial_velocity: np.ndarray  # (n_ray, n_gate)
    intensity: np.ndarray
    backscatter: np.ndarray
    sha256: str = ""
    truncated: bool = False

    @property
    def n_gates(self) -> int:
        """The gates of each ray."""
        return self.radial_velocity.shape[1]

    @property
    def range(self) -> np.ndarray:
        """Centre of each gate, ``(gate + 0.5) * gate_spacing``, in m."""
        return (np.arange(self.n_gates) + 0.5) * self.gate_spacing


@dataclass(frozen=True)
class GpsFix:
    """One GPS fix of a ``Time_Sync`` file."""

    time: datetime
    latitude: float
    longitude: float
    altitude: float  # m, as the receiver gives it
    satellites: int


@dataclass(frozen=True)
class LidarScanInfo:  # pylint: disable=too-many-instance-attributes
    """One row of ``scans/``."""

    index: int
    time: datetime
    time_end: datetime
    scan_type: str
    n_rays: int
    first_ray: int
    latitude: float
    longitude: float
    altitude: float
    position_source: str
    source_file: str
    # Every ray points the same way: a stare, a time-height record rather than a scan.
    is_stare: bool


@dataclass(frozen=True)
class LidarPoints:
    """The gates of one scan that pass the quality thresholds, from the lidar's position."""

    instrument: str
    scan: LidarScanInfo
    heading: float  # degree, the azimuth of the instrument's 0, clockwise from true north
    east: np.ndarray  # m
    north: np.ndarray
    up: np.ndarray
    range: np.ndarray
    radial_velocity: np.ndarray
    intensity: np.ndarray
    backscatter: np.ndarray
    # Gates of the scan with a value, before the thresholds.
    n_gates: int


@lru_cache(maxsize=1)
def lidar_parameters() -> LidarParameters:
    """The parameters of the installed FireBench."""
    content = files("firebench").joinpath(PARAMETER_FILE).read_bytes()
    document = tomllib.loads(content.decode("utf-8"))
    try:
        position, qc = document["position"], document["qc"]
        return LidarParameters(
            max_fix_gap_h=float(position["max_fix_gap_h"]),
            snr_min_db=float(qc["snr_min_db"]),
            backscatter_min=float(qc["backscatter_min"]),
            radial_velocity_max_abs=float(qc["radial_velocity_max_abs"]),
            sha256=hashlib.sha256(content).hexdigest(),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{PARAMETER_FILE} is not what the lidar reader expects: {error}") from None


# Reading the raw files ------------------------------------------------------------------------------


def halo_file_kind(path: Path | str) -> Literal["scan", "time_sync"] | None:
    """``scan`` for a raw ``.hpl`` file, ``time_sync`` for a ``Time_Sync`` file, None otherwise."""
    with open(path, "rb") as stream:
        head = stream.read(_HEAD_BYTES).decode("utf-8", errors="replace").lstrip("﻿")
    if head.startswith(_HPL_HEAD) and "System ID:" in head:
        return "scan"
    if head.startswith(_TIME_SYNC_HEAD):
        return "time_sync"
    return None


def read_halo_hpl(path: Path | str) -> HaloScan:
    """
    Read a raw Halo Photonics StreamLine scan (``.hpl``).

    The header gives the gates: their number, the range gate length, and its length in points. In an
    overlapping scan (the scan type says ``overlapping``) a gate starts every point, so the gate
    spacing is the range gate length divided by the points; otherwise it is the range gate length.
    The centre of gate ``k`` is at ``(k + 0.5)`` times the spacing. Ray times are decimal hours of
    the UTC day of the start time, and roll over to the next day after midnight. A last ray cut short
    (a file copied while it was written) is left out.

    Raises
    ------
    ValueError
        If the file is not a raw scan (a processed wind profile, a background file), its header lacks
        a field, or a ray cannot be read.
    """
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace").lstrip("﻿")
    if not text.startswith(_HPL_HEAD):
        raise ValueError("not a raw Halo scan: the file does not start with a `Filename:` header")
    lines = text.splitlines()
    header: dict[str, str] = {}
    data_start = None
    for number, line in enumerate(lines):
        if line.startswith("****"):
            data_start = number + 1
            break
        key, sep, value = line.partition(":")
        if sep:
            header[key.strip()] = value.strip()
    if data_start is None:
        raise ValueError("the header has no end (a line of `****`)")

    n_gates = int(_header(header, "Number of gates", float))
    gate_length = _header(header, "Range gate length (m)", float)
    gate_points = int(_header(header, "Gate length (pts)", float))
    scan_type = header.get("Scan type", "")
    if n_gates <= 0 or gate_length <= 0 or gate_points <= 0:
        raise ValueError("the header gives no gate")
    overlapping = "overlapping" in scan_type.lower()
    gate_spacing = gate_length / gate_points if overlapping else gate_length
    start = _start_time(_header(header, "Start time", str))

    body = [line for line in lines[data_start:] if line.strip()]
    block = n_gates + 1
    n_rays = len(body) // block
    truncated = len(body) % block != 0
    if n_rays == 0:
        raise ValueError("the file holds no complete ray")
    rays = _numbers(body[0 : n_rays * block : block], 5, "ray")
    gate_lines = [line for index, line in enumerate(body[: n_rays * block]) if index % block]
    columns = len(gate_lines[0].split())
    if columns < 4:
        raise ValueError("a gate line has fewer than four columns: gate, Doppler, intensity, beta")
    gates = np.reshape(_numbers(gate_lines, columns, "gate"), (n_rays, n_gates, columns))
    if not np.array_equal(gates[:, :, 0], np.broadcast_to(np.arange(n_gates), (n_rays, n_gates))):
        raise ValueError("the gates of a ray are not numbered 0 to `Number of gates` - 1")

    hours = rays[:, 0]
    if np.any((hours < 0) | (hours >= 24)):
        raise ValueError("a ray time is not a decimal hour of the day")
    day = datetime.combine(start.date(), datetime.min.time(), tzinfo=timezone.utc)
    start_hours = (start - day).total_seconds() / 3600
    # A ray before the start by more than half a day is on the next day, and so is any ray after a
    # time that went back.
    rolls = np.cumsum(np.concatenate([[hours[0] < start_hours - 12], np.diff(hours) < -12]))
    times = [day + timedelta(hours=float(hour) + 24 * int(roll)) for hour, roll in zip(hours, rolls)]
    return HaloScan(
        filename=header.get("Filename", path.name),
        system_id=int(_header(header, "System ID", float)),
        scan_type=scan_type,
        start=start,
        gate_length=gate_length,
        gate_points=gate_points,
        gate_spacing=gate_spacing,
        focus_range=_optional(header, "Focus range"),
        pulses_per_ray=_optional_int(header, "Pulses/ray"),
        velocity_resolution=_optional(header, "Resolution (m/s)"),
        time=times,
        azimuth=rays[:, 1],
        elevation=rays[:, 2],
        pitch=rays[:, 3],
        roll=rays[:, 4],
        radial_velocity=gates[:, :, 1].astype(np.float32),
        intensity=gates[:, :, 2].astype(np.float32),
        backscatter=gates[:, :, 3].astype(np.float32),
        sha256=hashlib.sha256(raw).hexdigest(),
        truncated=truncated,
    )


def read_halo_time_sync(path: Path | str) -> list[GpsFix]:
    """
    Read the GPS fixes of a Halo ``Time_Sync`` file, in time order.

    Each line holds the time the clock was set (``dd/mm/yyyy``, UTC), the satellites in view, and
    the position in degrees, minutes, and seconds with the height in m. A line without a position is
    left out.

    Raises
    ------
    ValueError
        If the file holds no fix.
    """
    text = Path(path).read_bytes().decode("utf-8", errors="replace")
    fixes = []
    for line in text.splitlines():
        match = _FIX.search(line)
        if match is None:
            continue
        time = datetime.strptime(f"{match['date']} {match['time']}", "%d/%m/%Y %H:%M:%S.%f")
        fixes.append(
            GpsFix(
                time=time.replace(tzinfo=timezone.utc),
                latitude=_degrees(match, "lat"),
                longitude=_degrees(match, "lon"),
                altitude=float(match["height"]),
                satellites=int(match["satellites"]),
            )
        )
    if not fixes:
        raise ValueError("no GPS fix could be read: expected lines of `Time before: *dd/mm/yyyy ...`")
    return sorted(fixes, key=lambda fix: fix.time)


# Writing -------------------------------------------------------------------------------------------


def standardize_halo_lidar(  # pylint: disable=too-many-locals
    scans: Iterable[Path | str],
    h5file: h5py.File,
    *,
    bbox,
    start: datetime,
    end: datetime,
    heading_deg: float,
    time_sync: Sequence[Path | str] = (),
    position: tuple[float, float] | None = None,
    altitude: float | None = None,
    altitude_source: str = "entered",
    altitude_of: Callable[[float, float], tuple[float, str] | None] | None = None,
    overwrite: bool = False,
    compression_lvl: int = 6,
) -> list[h5py.Group]:
    """
    Write the raw scans of Halo lidars, one group ``/spatial_3d/lidar/HALO_<system id>`` each.

    A scan is kept when its start is in ``[start, end)``. The lidar is static: every scan has the same
    position. Its latitude and longitude are ``position`` when given, else the median of the GPS fixes
    of ``time_sync`` from ``max_fix_gap_h`` (``resources/lidar.toml``) before the first scan kept to as
    long after the last; its altitude is ``altitude`` when given, else ``altitude_of`` of that position
    (*e.g.* the ground elevation of :func:`firebench.standardize.ground_elevation`), else the median
    height of those fixes. A file read twice and a file whose gates differ from the first file of its
    instrument are not written: they are in the ``failed`` attribute with the reason, as is a file
    that cannot be read.

    Parameters
    ----------
    scans : Iterable of path
        Raw ``.hpl`` files.
    h5file : h5py.File
        The standard file to write to.
    bbox : sequence of float
        The frame, ``(west, south, east, north)`` in degrees.
    start, end : datetime
        The window, aware.
    heading_deg : float
        The azimuth of the instrument's 0 degree, clockwise from true north. The azimuths are stored
        as recorded and the heading as the attribute ``azimuth_offset``.
    time_sync : sequence of path
        ``Time_Sync`` files of the lidars.
    position : (latitude, longitude) or None
        The position of the lidar, in degrees, instead of the GPS.
    altitude : float or None
        The altitude of the lidar, in m above mean sea level, instead of the GPS height.
    altitude_source : str
        What ``altitude`` comes from, recorded in the group (*e.g.* ``entered``, ``LANDFIRE``).
    altitude_of : callable or None
        ``(latitude, longitude) -> (altitude, source)`` or None, asked when ``altitude`` is not given.

    Raises
    ------
    ValueError
        If the heading or the position is invalid, a ``Time_Sync`` file cannot be read, no scan can
        be written, the lidar has no position or is outside the frame, or a group exists and
        ``overwrite`` is False.
    """
    check_std_version(h5file)
    start, end = _utc(start), _utc(end)
    frame = _bbox(bbox)
    heading = float(heading_deg)
    if not 0 <= heading < 360:
        raise ValueError(f"the heading must be in [0, 360) degree, not {heading_deg!r}")
    if position is not None:
        position = _position(position)
    if altitude is not None and not math.isfinite(float(altitude)):
        raise ValueError(f"invalid altitude {altitude!r}")
    fixes = [fix for path in time_sync for fix in read_halo_time_sync(path)]
    fixes.sort(key=lambda fix: fix.time)
    max_gap = timedelta(hours=lidar_parameters().max_fix_gap_h)

    failed: list[dict] = []
    seen: set[str] = set()
    kept: dict[int, list[HaloScan]] = {}
    for path in scans:
        name = Path(path).name
        try:
            scan = read_halo_hpl(path)
        except (ValueError, OSError) as error:
            failed.append({"file": name, "reason": f"unreadable: {error}"})
            continue
        name = scan.filename
        if scan.sha256 in seen:
            failed.append({"file": name, "reason": "the same file was given twice"})
            continue
        seen.add(scan.sha256)
        if not start <= scan.time[0] < end:
            continue
        group = kept.setdefault(scan.system_id, [])
        if group and not _same_gates(group[0], scan):
            failed.append(
                {"file": name, "reason": "its gates differ from the first scan of the same lidar"}
            )
            continue
        group.append(scan)
    if not kept:
        reasons = "; ".join(f"{item['file']}: {item['reason']}" for item in failed[:5])
        raise ValueError(f"no lidar scan in the window could be written{': ' + reasons if reasons else ''}")

    groups = []
    for system_id, rows in sorted(kept.items()):
        path = f"{GROUP}/HALO_{system_id}"
        if path in h5file and not overwrite:
            raise ValueError(f"group {path} already exists in {h5file.filename}. Set `overwrite` to True.")
        rows.sort(key=lambda row: row.time[0])
        where = _static_position(
            rows, position, (altitude, altitude_source, altitude_of), fixes, max_gap, frame
        )
        groups.append(
            _write_instrument(
                h5file,
                path,
                [(row, where.origin, where.source) for row in rows],
                frame,
                start,
                heading,
                failed,
                where,
                compression_lvl=compression_lvl,
            )
        )
    return groups


@dataclass(frozen=True)
class _Position:
    origin: tuple[float, float, float]
    source: str
    altitude_source: str
    fixes: int
    spread: float  # m, the farthest fix from the position


def _static_position(rows, position, height, fixes, max_gap, frame) -> _Position:
    """The one position of a static lidar: entered, or the median of the GPS fixes around its scans."""
    altitude, altitude_source, altitude_of = height
    first, last = rows[0].time[0], max(row.time[-1] for row in rows)
    near = [fix for fix in fixes if first - max_gap <= fix.time <= last + max_gap]
    if position is None and not near:
        raise ValueError("the lidar has no position: no GPS fix near its scans and none entered")
    lat, lon = (
        position
        if position is not None
        else (
            float(np.median([fix.latitude for fix in near])),
            float(np.median([fix.longitude for fix in near])),
        )
    )
    if altitude is None and altitude_of is not None:
        found = altitude_of(lat, lon)
        if found is not None:
            altitude, altitude_source = found
    if altitude is None and not near:
        raise ValueError("the lidar has no altitude: no GPS fix near its scans and none given")
    alt = float(altitude) if altitude is not None else float(np.median([fix.altitude for fix in near]))
    west, south, east, north = frame
    if not (west <= lon <= east and south <= lat <= north):
        raise ValueError(f"the lidar ({lat:.5f}, {lon:.5f}) is outside the frame")
    scale = 111_320.0
    spread = max(
        (
            math.hypot(
                (fix.latitude - lat) * scale, (fix.longitude - lon) * scale * math.cos(math.radians(lat))
            )
            for fix in near
        ),
        default=0.0,
    )
    return _Position(
        origin=(lat, lon, alt),
        source="entered" if position is not None else "gps",
        altitude_source=altitude_source if altitude is not None else "gps",
        fixes=len(near),
        spread=spread,
    )


def _write_instrument(  # pylint: disable=too-many-arguments,too-many-locals
    h5file, path, rows, frame, start, heading, failed, where, *, compression_lvl
) -> h5py.Group:
    first = rows[0][0]
    instrument = path.rsplit("/", 1)[-1]
    if path in h5file:
        del h5file[path]
    # The parent groups carry no attribute, so fragments that each hold a lidar merge without conflict.
    group = h5file.require_group(f"/{SPATIAL_3D}").require_group(LIDAR).create_group(instrument)
    west, south, east, north = frame
    lat, lon, alt = rows[0][1]
    time_end = max(row[0].time[-1] for row in rows)
    attrs = {
        "instrument": "Halo Photonics StreamLine",
        "system_id": int(first.system_id),
        "data_source": "file",
        "crs": CRS,
        "position_origin_lat": lat,
        "position_origin_lat_units": "degree",
        "position_origin_lon": lon,
        "position_origin_lon_units": "degree",
        "position_origin_alt": alt,
        "position_origin_alt_units": "m",
        "position_source": where.source,
        "altitude_source": where.altitude_source,
        "position_fixes": where.fixes,
        "position_spread": round(where.spread, 1),
        "position_spread_units": "m",
        "azimuth_offset": heading,
        "azimuth_offset_units": "degree",
        "gate_length": first.gate_length,
        "gate_length_units": "m",
        "gate_points": int(first.gate_points),
        "gate_spacing": first.gate_spacing,
        "gate_spacing_units": "m",
        "n_gates": int(first.n_gates),
        "time_start": start.isoformat(),
        "time_end": max(time_end, start).isoformat(),
        "fields": json.dumps([name for name, _, _ in FIELDS]),
        "failed": json.dumps(failed),
        "source_files": json.dumps([{"name": row[0].filename, "rays": len(row[0].time)} for row in rows]),
        "description": (
            f"Halo Photonics StreamLine Doppler lidar {first.system_id}: raw rays as observed. The true "
            "azimuth of a ray is its azimuth plus azimuth_offset; pitch and roll are not applied."
        ),
    }
    for name, value in (("west", west), ("south", south), ("east", east), ("north", north)):
        attrs[f"frame_{name}"] = float(value)
        attrs[f"frame_{name}_units"] = "degree"
    for key, value in attrs.items():
        group.attrs[key] = value

    compression = hdf5plugin.Zstd(clevel=compression_lvl)
    gates = group.create_dataset("range", data=first.range.astype(np.float32), **compression)
    gates.attrs["units"] = "m"
    gates.attrs["description"] = "Distance from the lidar to the gate centre along the ray"

    first_rays = np.cumsum([0] + [len(row[0].time) for row in rows[:-1]])
    ray_columns = {
        svn.TIME.value: (
            np.concatenate([_seconds(row[0].time, start) for row in rows]),
            _time_attrs(start),
        ),
        "azimuth": (
            np.concatenate([row[0].azimuth for row in rows]).astype(np.float32),
            {"units": "degree", "description": "As recorded, clockwise from the instrument's 0"},
        ),
        "elevation": (
            np.concatenate([row[0].elevation for row in rows]).astype(np.float32),
            {"units": "degree"},
        ),
        "pitch": (np.concatenate([row[0].pitch for row in rows]).astype(np.float32), {"units": "degree"}),
        "roll": (np.concatenate([row[0].roll for row in rows]).astype(np.float32), {"units": "degree"}),
        "scan_index": (
            np.concatenate(
                [np.full(len(row[0].time), index, dtype=np.int32) for index, row in enumerate(rows)]
            ),
            {"units": "1", "description": "Row of scans/ the ray belongs to"},
        ),
    }
    _write_columns(group, ray_columns, compression_lvl)
    for (name, units, description), attribute in zip(
        FIELDS, ("radial_velocity", "intensity", "backscatter")
    ):
        values = np.concatenate([getattr(row[0], attribute) for row in rows], axis=0).astype(np.float32)
        dataset = group.create_dataset(
            name,
            data=values,
            chunks=(min(len(values), 256), values.shape[1]),
            fillvalue=np.float32(np.nan),
            **compression,
        )
        dataset.attrs["units"] = units
        dataset.attrs["description"] = description

    table = group.create_group(SCANS)
    scan_columns = {
        svn.TIME.value: (_seconds([row[0].time[0] for row in rows], start), _time_attrs(start)),
        "time_end": (_seconds([row[0].time[-1] for row in rows], start), _time_attrs(start)),
        "n_rays": (np.array([len(row[0].time) for row in rows], dtype=np.int32), {"units": "1"}),
        "first_ray": (np.asarray(first_rays, dtype=np.int64), {"units": "1"}),
        "position_origin_lat": (np.array([row[1][0] for row in rows]), {"units": "degree"}),
        "position_origin_lon": (np.array([row[1][1] for row in rows]), {"units": "degree"}),
        "position_origin_alt": (np.array([row[1][2] for row in rows]), {"units": "m"}),
        "focus_range": (np.array([_nan(row[0].focus_range) for row in rows]), {"units": "m"}),
        "pulses_per_ray": (
            np.array([row[0].pulses_per_ray or -1 for row in rows], dtype=np.int32),
            {"_FillValue": np.int32(-1)},
        ),
        "velocity_resolution": (
            np.array([_nan(row[0].velocity_resolution) for row in rows]),
            {"units": "m/s"},
        ),
        # Fixed-length ASCII: the signing digest reads variable-length strings as object arrays, whose
        # bytes are pointers, so it would differ from one read to the next.
        "scan_type": (_ascii([row[0].scan_type for row in rows]), {}),
        "position_source": (_ascii([row[2] for row in rows]), {}),
        "source_file": (_ascii([row[0].filename for row in rows]), {}),
        "source_sha256": (_ascii([row[0].sha256 for row in rows]), {}),
    }
    _write_columns(table, scan_columns, compression_lvl)
    logger.info(
        "[lidar] %s: %d scans, %d rays, %d files not written",
        instrument,
        len(rows),
        int(sum(len(row[0].time) for row in rows)),
        len(failed),
    )
    return group


def _write_columns(group: h5py.Group, columns: dict, compression_lvl: int) -> None:
    for name, (data, attrs) in columns.items():
        data = np.asarray(data)
        dataset = group.create_dataset(
            name,
            data=data,
            fillvalue=attrs.get("_FillValue"),
            **hdf5plugin.Zstd(clevel=compression_lvl),
        )
        for key, value in attrs.items():
            dataset.attrs[key] = value


# Reading the standard file --------------------------------------------------------------------------


def list_lidar_instruments(h5file: h5py.File) -> list[str]:
    """The lidars of a file, sorted. An empty list when the group is absent."""
    group = h5file.get(GROUP)
    if not isinstance(group, h5py.Group):
        return []
    return sorted(name for name, item in group.items() if isinstance(item, h5py.Group))


def lidar_scans(h5file: h5py.File | Path | str, instrument: str) -> list[LidarScanInfo]:
    """The scans of a lidar, in time order."""
    with _opened(h5file) as h5:
        group = _instrument(h5, instrument)
        table = group[SCANS]
        times = _absolute(table[svn.TIME.value])
        ends = _absolute(table["time_end"])
        first = table["first_ray"][()]
        counts = table["n_rays"][()]
        azimuth = group["azimuth"][()]
        elevation = group["elevation"][()]
        scans = []
        for index, (ray, count) in enumerate(zip(first, counts)):
            rays = slice(int(ray), int(ray + count))
            stare = bool(
                np.ptp(elevation[rays]) < _SAME_DIRECTION_DEG
                and (
                    np.ptp(azimuth[rays]) < _SAME_DIRECTION_DEG
                    or np.min(elevation[rays]) > 90 - _SAME_DIRECTION_DEG
                )
            )
            scans.append(
                LidarScanInfo(
                    index=index,
                    time=times[index],
                    time_end=ends[index],
                    scan_type=_text(table["scan_type"][index]),
                    n_rays=int(count),
                    first_ray=int(ray),
                    latitude=float(table["position_origin_lat"][index]),
                    longitude=float(table["position_origin_lon"][index]),
                    altitude=float(table["position_origin_alt"][index]),
                    position_source=_text(table["position_source"][index]),
                    source_file=_text(table["source_file"][index]),
                    is_stare=stare,
                )
            )
        return scans


def lidar_points(
    h5file: h5py.File | Path | str, instrument: str, scan: int, *, qc: bool = True
) -> LidarPoints:
    """
    The gates of one scan with a value, as east, north, and up from the lidar, in m.

    The true azimuth of a ray is its recorded azimuth plus the heading (``azimuth_offset``). The
    geometry is flat: no Earth curvature nor refraction, which a lidar's few kilometres allow. Pitch
    and roll are not applied. With ``qc``, a gate is kept when it passes the thresholds of
    ``resources/lidar.toml``: the signal-to-noise ratio, the backscatter, and the radial velocity.
    """
    parameters = lidar_parameters()
    with _opened(h5file) as h5:
        group = _instrument(h5, instrument)
        info = lidar_scans(h5, instrument)[scan]
        rays = slice(info.first_ray, info.first_ray + info.n_rays)
        heading = float(group.attrs["azimuth_offset"])
        gate_range = group["range"][()].astype(np.float64)
        velocity = group[svn.LIDAR_RADIAL_VELOCITY.value][rays].astype(np.float64)
        intensity = group[svn.LIDAR_INTENSITY.value][rays].astype(np.float64)
        backscatter = group[svn.LIDAR_ATTENUATED_BACKSCATTER.value][rays].astype(np.float64)
        azimuth = np.deg2rad(group["azimuth"][rays].astype(np.float64) + heading)[:, None]
        elevation = np.deg2rad(group["elevation"][rays].astype(np.float64))[:, None]
    keep = np.isfinite(velocity) & np.isfinite(intensity) & np.isfinite(backscatter)
    n_gates = int(keep.sum())
    if qc:
        with np.errstate(divide="ignore", invalid="ignore"):
            snr_db = 10 * np.log10(intensity - 1)
        keep &= snr_db >= parameters.snr_min_db
        keep &= backscatter > parameters.backscatter_min
        keep &= (velocity != 0) & (np.abs(velocity) < parameters.radial_velocity_max_abs)
    distance = np.broadcast_to(gate_range[None, :], keep.shape)
    horizontal = distance * np.cos(elevation)
    return LidarPoints(
        instrument=instrument,
        scan=info,
        heading=heading,
        east=(horizontal * np.sin(azimuth))[keep],
        north=(horizontal * np.cos(azimuth))[keep],
        up=(distance * np.sin(elevation))[keep],
        range=distance[keep],
        radial_velocity=velocity[keep],
        intensity=intensity[keep],
        backscatter=backscatter[keep],
        n_gates=n_gates,
    )


# Helpers -------------------------------------------------------------------------------------------


class _opened:  # pylint: disable=invalid-name
    """A file given open stays open; a path is opened for reading and closed after."""

    def __init__(self, h5file):
        self.given = h5file
        self.file = None

    def __enter__(self) -> h5py.File:
        if isinstance(self.given, (h5py.File, h5py.Group)):
            return self.given
        self.file = h5py.File(self.given, "r")
        return self.file

    def __exit__(self, *exc):
        if self.file is not None:
            self.file.close()


def _instrument(h5, instrument: str) -> h5py.Group:
    group = h5.get(f"{GROUP}/{instrument}")
    if not isinstance(group, h5py.Group):
        raise ValueError(
            f"no lidar {instrument!r} in the file; found {', '.join(list_lidar_instruments(h5)) or 'none'}"
        )
    return group


def _header(header: dict, key: str, kind):
    if key not in header:
        raise ValueError(f"the header has no `{key}`")
    try:
        return kind(header[key])
    except ValueError:
        raise ValueError(f"the header's `{key}` cannot be read: {header[key]!r}") from None


def _optional(header: dict, key: str) -> float | None:
    try:
        return float(header[key])
    except (KeyError, ValueError):
        return None


def _optional_int(header: dict, key: str) -> int | None:
    value = _optional(header, key)
    return None if value is None else int(value)


def _start_time(text: str) -> datetime:
    for layout in ("%Y%m%d %H:%M:%S.%f", "%Y%m%d %H:%M:%S"):
        try:
            return datetime.strptime(text.strip(), layout).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"the header's `Start time` cannot be read: {text!r}")


def _numbers(lines: list[str], columns: int, what: str) -> np.ndarray:
    try:
        values = np.array(" ".join(lines).split(), dtype=np.float64)
    except ValueError:
        raise ValueError(f"a {what} line holds something other than numbers") from None
    if values.size != len(lines) * columns:
        raise ValueError(f"the {what} lines do not all have {columns} columns")
    return np.reshape(values, (len(lines), columns))


def _degrees(match: re.Match, prefix: str) -> float:
    value = (
        float(match[f"{prefix}_deg"])
        + float(match[f"{prefix}_min"]) / 60
        + float(match[f"{prefix}_sec"]) / 3600
    )
    return -value if match[f"{prefix}_hem"] in ("S", "W") else value


def _same_gates(first: HaloScan, other: HaloScan) -> bool:
    return first.n_gates == other.n_gates and np.isclose(first.gate_spacing, other.gate_spacing)


def _position(position) -> tuple[float, float]:
    lat, lon = (float(value) for value in position)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"invalid position {position!r}: expected latitude and longitude")
    return lat, lon


def _bbox(bbox) -> tuple[float, float, float, float]:
    west, south, east, north = (float(value) for value in bbox)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError(f"invalid box {bbox!r}: expected west < east and south < north, in degrees")
    return west, south, east, north


def _time_attrs(origin: datetime) -> dict:
    return {"units": "s", "time_origin": origin.isoformat(), "time_units": "s"}


def _seconds(times: Sequence[datetime], origin: datetime) -> np.ndarray:
    return np.array([(_utc(time) - origin).total_seconds() for time in times], dtype=np.float64)


def _absolute(dataset: h5py.Dataset) -> list[datetime]:
    origin = _utc(datetime.fromisoformat(_text(dataset.attrs["time_origin"])))
    return [origin + timedelta(seconds=float(value)) for value in dataset[()]]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{value!r} has no time zone")
    return value.astimezone(timezone.utc)


def _ascii(values: Sequence[str]) -> np.ndarray:
    return np.array([value.encode("ascii", errors="replace") for value in values])


def _nan(value: float | None) -> float:
    return np.nan if value is None else float(value)


def _text(value) -> str:
    if isinstance(value, np.ndarray):
        value = value.reshape(-1)[0] if value.size else b""
    return value.decode() if isinstance(value, (bytes, np.bytes_)) else str(value)
