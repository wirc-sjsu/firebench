"""
Weather radar volumes in the FireBench standard file, and the plume readings they give.

A site is stored under ``/spatial_3d/radar/<SITE>`` as polar sweeps, the way the radar observed
them: one row per sweep, a fixed azimuth axis of 0.5 degree bins and a range axis of 250 m gates,
both cropped to the cells that can fall inside the frame below a height ceiling. Nothing is gridded
at standardization; a reader grids or cuts what it needs.

- :func:`standardize_nexrad_level2` writes one WSR-88D site from NEXRAD Level II volumes
  (:mod:`firebench.acquisition.nexrad`), read with xradar (the optional ``radar`` extra), one
  volume at a time.
- :func:`radar_echo_top_series` gives the height of the plume gates of each volume,
  :func:`radar_composite` the column maximum of a field over the plume gates on a lon/lat grid, and
  :func:`radar_points` the plume gates of a volume as points.
- :func:`radar_cross_section` cuts every volume on a plane given by three points
  (:class:`RadarPlane`); :func:`write_radar_sections` stores sections beside the sweeps, under
  ``sections/``, and :func:`read_radar_section` reads one back.

The plume mask is the pyrometeor mask of Krishna et al. (2024): reflectivity at least ``min_dbz``
and a correlation coefficient strictly between the bounds of ``rhohv_range``; its defaults and the
limits of a section are in ``resources/radar.toml``. Licence attributes are not written: the caller
sets them.
"""

import gzip
import hashlib
import json
import logging
import re
import shutil
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime, timezone
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

import h5py
import hdf5plugin
import numpy as np
from matplotlib.path import Path as PolygonPath
from pyproj import Geod, Proj

from ..acquisition.nexrad import BUCKET, FetchedVolume
from ..tools.namespace import StandardVariableNames as svn
from .std_file_info import RADAR, SPATIAL_3D
from .tools import check_std_version

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib

logger = logging.getLogger(__name__)

GROUP = f"/{SPATIAL_3D}/{RADAR}"
VOLUMES = "volumes"
CRS = "EPSG:4326"

# Level II moment names, as xradar names them, and the standard dataset each one becomes.
FIELDS: dict[str, tuple[str, str]] = {
    "DBZH": (svn.RADAR_REFLECTIVITY.value, "dBZ"),
    "RHOHV": (svn.RADAR_CORRELATION_COEFFICIENT.value, "1"),
    "ZDR": (svn.RADAR_DIFFERENTIAL_REFLECTIVITY.value, "dB"),
    "VRADH": (svn.RADAR_RADIAL_VELOCITY.value, "m/s"),
}
DEFAULT_FIELDS = ("DBZH", "RHOHV", "ZDR", "VRADH")
# The name of each field in the Level II data blocks.
_LEVEL2_NAMES = {"DBZH": "REF", "RHOHV": "RHO", "ZDR": "ZDR", "VRADH": "VEL"}
# Fields taken from the Doppler cut of a split cut; the others come from its surveillance cut.
_DOPPLER = ("VRADH",)

AZIMUTH_STEP = 0.5  # degree
N_AZIMUTH = int(round(360 / AZIMUTH_STEP))
GATE_SPACING = 250.0  # m
MAX_RANGE = 460_000.0  # m, the longest range of a WSR-88D surveillance cut
BEAM_WIDTH = 0.95  # degree, WSR-88D half-power beam width
DEFAULT_MAX_HEIGHT = 20_000.0  # m above mean sea level
# Elevations a WSR-88D can scan, for the crop: the axes hold every cell that one of them places in
# the frame below the ceiling, whatever the volume coverage pattern.
_CROP_ELEVATIONS = np.arange(0.0, 19.76, 0.25)
# Raw Level II codes with no value: 0 below the signal threshold, 1 range folded.
_NO_DATA_CODES = (0, 1)
EARTH_RADIUS = 6_371_000.0  # m
EFFECTIVE_RADIUS = 4.0 / 3.0 * EARTH_RADIUS  # standard refraction (Doviak and Zrnic, 1993)
_GEOD = Geod(ellps="WGS84")

PARAMETER_FILE = "resources/radar.toml"
SECTIONS = "sections"
_SECTION_NAME = re.compile(r"^[a-z0-9-]{1,40}$")


@dataclass(frozen=True)
class RadarParameters:  # pylint: disable=too-many-instance-attributes
    """The values of ``resources/radar.toml``."""

    version: str
    min_dbz: float
    rhohv_range: tuple[float, float]
    min_spacing: float
    max_spacing: float
    max_length: float
    max_span: float
    max_cells: int
    max_elevation_gap: float
    sha256: str


@lru_cache(maxsize=1)
def radar_parameters() -> RadarParameters:
    """The parameters of the installed FireBench."""
    content = files("firebench").joinpath(PARAMETER_FILE).read_bytes()
    document = tomllib.loads(content.decode("utf-8"))
    try:
        mask, sections = document["plume_mask"], document["sections"]
        low, high = (float(value) for value in mask["rhohv_range"])
        return RadarParameters(
            version=str(document["version"]),
            min_dbz=float(mask["min_dbz"]),
            rhohv_range=(low, high),
            min_spacing=float(sections["min_spacing"]),
            max_spacing=float(sections["max_spacing"]),
            max_length=float(sections["max_length"]),
            max_span=float(sections["max_span"]),
            max_cells=int(sections["max_cells"]),
            max_elevation_gap=float(sections["max_elevation_gap"]),
            sha256=hashlib.sha256(content).hexdigest(),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{PARAMETER_FILE} is not what the radar reader expects: {error}") from None


DEFAULT_MIN_DBZ = radar_parameters().min_dbz
DEFAULT_RHOHV_RANGE = radar_parameters().rhohv_range


@dataclass
class RadarSweep:
    """One row of the standard file: a sweep, or the two cuts of a split cut merged."""

    time: datetime
    elevation: float
    azimuth_resolution: float
    nyquist_velocity: float
    first_gate: float
    # Level II moment name -> (n_rays, n_gates) values, with the ray azimuths below
    data: dict[str, np.ndarray]
    azimuth: np.ndarray


@dataclass
class RadarVolume:
    """A Level II volume as read, with its split cuts merged."""

    site: str
    latitude: float
    longitude: float
    altitude: float
    vcp: int | None
    time_start: datetime
    time_end: datetime
    sweeps: list[RadarSweep] = dataclass_field(default_factory=list)


@dataclass(frozen=True)
class EchoTopSeries:
    """Heights of the plume gates of each volume, in m above mean sea level."""

    site: str
    time: np.ndarray  # datetime64[ms], volume start
    height_max: np.ndarray
    height_quantiles: dict[float, np.ndarray]
    n_gates: np.ndarray


@dataclass(frozen=True)
class RadarComposite:
    """The column maximum of a field over the plume gates of one volume, on a lon/lat grid."""

    site: str
    time: np.datetime64
    field: str
    bounds: tuple[float, float, float, float]  # west, south, east, north of the grid edges
    resolution: float  # degree
    values: np.ndarray  # (n_lat, n_lon), row 0 to the north, NaN where no gate counts


# Geometry ------------------------------------------------------------------------------------------


def beam_height(range_m, elevation_deg, antenna_altitude: float = 0.0) -> np.ndarray:
    """Height of the beam centre above mean sea level, with the 4/3 effective Earth radius."""
    r = np.asarray(range_m, dtype=np.float64)
    e = np.radians(np.asarray(elevation_deg, dtype=np.float64))
    return (
        np.sqrt(r**2 + EFFECTIVE_RADIUS**2 + 2 * r * EFFECTIVE_RADIUS * np.sin(e))
        - EFFECTIVE_RADIUS
        + antenna_altitude
    )


def beam_ground_distance(range_m, elevation_deg) -> np.ndarray:
    """Distance along the ground from the radar to the point under the beam centre."""
    r = np.asarray(range_m, dtype=np.float64)
    e = np.radians(np.asarray(elevation_deg, dtype=np.float64))
    height = beam_height(r, np.degrees(e))
    return EFFECTIVE_RADIUS * np.arcsin(r * np.cos(e) / (EFFECTIVE_RADIUS + height))


def azimuth_bins() -> np.ndarray:
    """Centres of the 0.5 degree azimuth bins, clockwise from north."""
    return (np.arange(N_AZIMUTH) + 0.5) * AZIMUTH_STEP


def frame_axes(
    latitude: float,
    longitude: float,
    altitude: float,
    bbox,
    max_height: float = DEFAULT_MAX_HEIGHT,
    first_gate: float = GATE_SPACING / 2,
) -> tuple[np.ndarray, np.ndarray]:
    """
    The azimuth bins and range gates a radar file keeps for a frame.

    A cell is kept when the beam centre of some elevation from 0 to 19.75 degree lies above the
    box at a height of at most ``max_height`` above mean sea level. The axes are the smallest arc
    of azimuth bins and the smallest interval of gates that hold every such cell, so a radar inside
    the box keeps the whole circle.

    Returns
    -------
    (np.ndarray, np.ndarray)
        Indices into :func:`azimuth_bins`, in clockwise order from the start of the arc, and the
        slant ranges of the gates, in m.

    Raises
    ------
    ValueError
        If no cell of the radar can fall inside the box below the ceiling.
    """
    west, south, east, north = _bbox(bbox)
    gates = first_gate + GATE_SPACING * np.arange(int((MAX_RANGE - first_gate) // GATE_SPACING) + 1)
    proj = Proj(proj="aeqd", lat_0=latitude, lon_0=longitude, ellps="WGS84")
    edge = np.linspace(0.0, 1.0, 200)
    ring_lon = np.concatenate(
        [
            west + (east - west) * edge,
            np.full_like(edge, east),
            east - (east - west) * edge,
            np.full_like(edge, west),
        ]
    )
    ring_lat = np.concatenate(
        [
            np.full_like(edge, south),
            south + (north - south) * edge,
            np.full_like(edge, north),
            north - (north - south) * edge,
        ]
    )
    ring = PolygonPath(np.column_stack(proj(ring_lon, ring_lat)))
    bearings = np.radians(azimuth_bins())
    # Ground distances inside the box along each bearing, sampled every gate spacing.
    distances = gates
    points = np.column_stack(
        [
            (np.sin(bearings)[:, None] * distances[None, :]).ravel(),
            (np.cos(bearings)[:, None] * distances[None, :]).ravel(),
        ]
    )
    inside = ring.contains_points(points).reshape(len(bearings), len(distances))
    inside[:, 0] |= ring.contains_point((0.0, 0.0))
    reached = inside.any(axis=1)
    if not reached.any():
        raise ValueError("the radar's beams never pass over the box")
    near = np.where(reached, distances[np.argmax(inside, axis=1)], np.inf)
    far = np.where(reached, distances[len(distances) - 1 - np.argmax(inside[:, ::-1], axis=1)], -np.inf)
    near = np.where(inside[:, 0], 0.0, near)

    low, high = np.full(len(bearings), len(gates)), np.full(len(bearings), -1)
    for elevation in _CROP_ELEVATIONS:
        ground = beam_ground_distance(gates, elevation)
        under = beam_height(gates, elevation, altitude) <= max_height
        if not under.any():
            continue
        last_under = int(np.nonzero(under)[0][-1])
        first = np.searchsorted(ground, near - GATE_SPACING / 2, side="left")
        last = np.minimum(np.searchsorted(ground, far + GATE_SPACING / 2, side="right") - 1, last_under)
        ok = reached & (first <= last)
        low = np.where(ok, np.minimum(low, first), low)
        high = np.where(ok, np.maximum(high, last), high)
    kept = high >= low
    if not kept.any():
        raise ValueError(f"no gate of the radar falls over the box below {max_height:.0f} m")
    return _arc(kept), gates[int(low[kept].min()) : int(high[kept].max()) + 1]


def _arc(kept: np.ndarray) -> np.ndarray:
    """The bin indices of the smallest circular arc holding every kept bin."""
    if kept.all():
        return np.arange(len(kept))
    idle = ~kept
    # The arc starts after the longest circular run of bins that are not kept.
    doubled = np.concatenate([idle, idle])
    best_len, best_end, run = 0, 0, 0
    for index, value in enumerate(doubled):
        run = run + 1 if value else 0
        if run > best_len:
            best_len, best_end = run, index
    start = (best_end + 1) % len(kept)
    length = len(kept) - min(best_len, len(kept))
    return (start + np.arange(length)) % len(kept)


# Reading Level II ----------------------------------------------------------------------------------


def read_level2_volume(path: Path, fields: Sequence[str] = DEFAULT_FIELDS) -> RadarVolume:
    """
    Read a NEXRAD Level II volume with xradar, and merge its split cuts.

    A low tilt is scanned twice: a surveillance cut (reflectivity and dual-polarization fields, to
    460 km) then a Doppler cut (reflectivity and velocity, to 300 km). The two become one sweep:
    reflectivity and the dual-polarization fields of the first, velocity of the second, and the time
    of the first. A tilt scanned again later in the volume (SAILS) is a sweep of its own. Codes 0
    (below threshold) and 1 (range folded) are NaN.

    Raises
    ------
    ImportError
        If xradar is not installed (``pip install firebench[radar]``).
    ValueError
        If the file is not a Level II volume xradar can read, or a field is unknown.
    """
    unknown = [name for name in fields if name not in FIELDS]
    if unknown:
        raise ValueError(f"unknown radar fields {unknown}; known: {', '.join(FIELDS)}")
    path = Path(path)
    if path.suffix == ".gz":
        with tempfile.TemporaryDirectory(dir=path.parent) as scratch:
            plain = Path(scratch) / path.stem
            with gzip.open(path, "rb") as source, open(plain, "wb") as target:
                shutil.copyfileobj(source, target)
            return read_level2_volume(plain, fields)
    try:
        # pylint: disable=import-outside-toplevel
        from xradar.io.backends.nexrad_level2 import NEXRADLevel2File
    except ImportError as error:
        raise ImportError("reading NEXRAD Level II needs xradar: pip install 'firebench[radar]'") from error

    try:
        level2 = NEXRADLevel2File(str(path))
    except (OSError, EOFError, KeyError, IndexError, TypeError, ValueError) as error:
        raise ValueError(f"not a readable NEXRAD Level II volume: {error}") from error
    try:
        return _read_level2(level2, fields)
    except (OSError, EOFError, KeyError, IndexError, TypeError) as error:
        raise ValueError(
            f"not a readable NEXRAD Level II volume: {type(error).__name__} {error}"
        ) from error
    finally:
        level2.close()


@dataclass(frozen=True)
class _RawMoment:
    """Raw Level II codes with their scaling, as xradar names it: value = code * scale + offset."""

    values: np.ndarray
    attrs: dict


def _read_level2(level2, fields: Sequence[str]) -> RadarVolume:
    """
    The cuts of a volume read with xradar's Level II file, then merged.

    xradar's data tree pairs the n-th finished sweep with the n-th sweep started, which mixes the
    coordinates of two sweeps when the archive holds a sweep that never finished (about one volume
    in seven at KDAX in August 2021). Here a sweep's radial headers (``msg_31_header``, one list per
    finished sweep) are paired with the finished sweeps (``data``) in order, and an unfinished sweep
    is left out.
    """
    radial_headers = level2.msg_31_header
    finished = sorted(level2.data)
    if len(finished) != len(radial_headers):
        raise ValueError(f"{len(finished)} finished sweeps for {len(radial_headers)} radial header lists")
    pattern = level2.msg_5 or {}
    pattern_angles = [cut["elevation_angle"] for cut in pattern.get("elevation_data", [])]
    cuts, volume_block = [], None
    for number, radials in zip(finished, radial_headers):
        if level2.data[number].get("msg_type") != 31:
            raise ValueError("legacy Level II messages (type 1, before 2008) are not read")
        level2.get_sweep(number)
        sweep = level2.data[number]
        constant = sweep["sweep_constant_data"]
        volume_block = volume_block or dict(constant["VOL"])
        names = [_LEVEL2_NAMES[name] for name in fields if _LEVEL2_NAMES[name] in sweep["sweep_data"]]
        if not names:
            continue
        level2.get_data(number, names)
        moments = {}
        for name in fields:
            block = sweep["sweep_data"].get(_LEVEL2_NAMES[name])
            if block is None:
                continue
            values = np.stack(block["data"])
            if len(values) != len(radials):
                raise ValueError(f"{len(values)} rays of {name} for {len(radials)} radials")
            moments[name] = (
                _RawMoment(
                    values,
                    {"scale_factor": 1.0 / block["scale"], "add_offset": -block["offset"] / block["scale"]},
                ),
                float(block["first_gate"]),
                float(block["gate_spacing"]),
            )
        # Azimuth of each radial in degrees; time from the Modified Julian day (1 is 1970-01-01).
        azimuth = np.array([radial["azimuth_angle"] for radial in radials], dtype=np.float64)
        stamps = np.array(
            [(radial["collect_date"] - 1) * 86_400_000 + radial["collect_ms"] for radial in radials],
            dtype=np.int64,
        )
        cut_number = radials[0]["elevation_number"]
        if 0 < cut_number <= len(pattern_angles):
            elevation = float(pattern_angles[cut_number - 1])
        else:
            elevation = float(np.median([radial["elevation_angle"] for radial in radials]))
        first_gates = {first for _, first, _ in moments.values()}
        spacings = {spacing for _, _, spacing in moments.values()}
        nyquist_raw = (constant.get("RAD") or {}).get("nyquist_vel")
        cuts.append(
            {
                "time": _datetime(np.datetime64(int(stamps.min()), "ms")),
                "time_end": _datetime(np.datetime64(int(stamps.max()), "ms")),
                "elevation": elevation,
                "azimuth": azimuth,
                "first_gate": min(first_gates),
                "gate_spacing": spacings.pop() if len(spacings) == 1 else float("nan"),
                "nyquist": float(nyquist_raw) / 100.0 if nyquist_raw else np.nan,
                "moments": {name: moment for name, (moment, _, _) in moments.items()},
                "first_gates": {name: first for name, (_, first, _) in moments.items()},
            }
        )
    if not cuts or volume_block is None:
        raise ValueError("the volume holds no finished sweep with the fields asked")
    volume = RadarVolume(
        site=_text(level2.volume_header.get("icao", b"")).strip(),
        latitude=float(volume_block["lat"]),
        longitude=float(volume_block["lon"]),
        # Height of the site above mean sea level plus the height of the feedhorn above the ground.
        altitude=float(volume_block["height"]) + float(volume_block["feedhorn_height"]),
        vcp=int(volume_block["vcp"]) if volume_block.get("vcp") else pattern.get("pattern_number"),
        time_start=min(cut["time"] for cut in cuts),
        time_end=max(cut["time_end"] for cut in cuts),
    )
    volume.sweeps = merge_cuts(cuts, fields)
    return volume


def merge_cuts(cuts: Sequence[dict], fields: Sequence[str] = DEFAULT_FIELDS) -> list[RadarSweep]:
    """
    The sweeps of a volume from its cuts, in time order, a split cut merged into one sweep.

    A cut is a dict with ``time``, ``elevation``, ``azimuth`` (one per ray), ``first_gate``,
    ``gate_spacing``, ``nyquist`` (m/s), and ``moments`` (Level II name -> raw values with the
    ``scale_factor`` and ``add_offset`` attributes, as xradar gives them unscaled). A cut with the
    dual-polarization fields and no velocity, followed by a cut at the same elevation with velocity
    and no dual-polarization field, is a split cut.
    """
    sweeps, index = [], 0
    while index < len(cuts):
        cut = cuts[index]
        following = cuts[index + 1] if index + 1 < len(cuts) else None
        merged = (
            following is not None
            and abs(following["elevation"] - cut["elevation"]) < 0.05
            and "VRADH" not in cut["moments"]
            and "RHOHV" in cut["moments"]
            and "VRADH" in following["moments"]
            and "RHOHV" not in following["moments"]
        )
        parts = {name: cut for name in fields if name in cut["moments"]}
        if merged:
            for name in fields:
                if name in _DOPPLER and name in following["moments"]:
                    parts[name] = following
        sweeps.append(_sweep(cut, following if merged else None, parts))
        index += 2 if merged else 1
    return sweeps


def _sweep(cut: dict, doppler: dict | None, parts: dict[str, dict]) -> RadarSweep:
    spacing = {round(part["gate_spacing"], 3) for part in parts.values()}
    if spacing and spacing != {GATE_SPACING}:
        raise ValueError(f"gate spacing of {sorted(spacing)} m; only {GATE_SPACING:.0f} m gates are read")
    starts = {
        name: part.get("first_gates", {}).get(name, part["first_gate"]) for name, part in parts.items()
    }
    first_gate = min(starts.values(), default=cut["first_gate"])
    reference = cut["azimuth"]
    data = {}
    for name, part in parts.items():
        values = _decode(part["moments"][name])
        offset = int(round((starts[name] - first_gate) / GATE_SPACING))
        if part is not cut:
            # The Doppler cut has rays of its own: take, for each ray of the surveillance cut, the
            # nearest one.
            values = values[_nearest_rays(part["azimuth"], reference)]
        if offset:
            values = np.pad(values, ((0, 0), (offset, 0)), constant_values=np.nan)
        data[name] = values
    resolution = 0.5 if len(reference) > 540 else 1.0
    return RadarSweep(
        time=cut["time"],
        elevation=cut["elevation"],
        azimuth_resolution=resolution,
        nyquist_velocity=(doppler or cut)["nyquist"] if "VRADH" in data else np.nan,
        first_gate=first_gate,
        data=data,
        azimuth=reference,
    )


def _decode(variable) -> np.ndarray:
    raw = np.asarray(variable.values)
    scale = float(variable.attrs.get("scale_factor", 1.0))
    offset = float(variable.attrs.get("add_offset", 0.0))
    values = (raw.astype(np.float64) * scale + offset).astype(np.float32)
    values[np.isin(raw, _NO_DATA_CODES)] = np.nan
    return values


def _nearest_rays(azimuth: np.ndarray, targets: np.ndarray) -> np.ndarray:
    order = np.argsort(azimuth)
    ordered = azimuth[order]
    extended = np.concatenate([ordered[-1:] - 360.0, ordered, ordered[:1] + 360.0])
    owners = np.concatenate([order[-1:], order, order[:1]])
    position = np.clip(np.searchsorted(extended, targets), 1, len(extended) - 1)
    left, right = position - 1, position
    pick = np.where(extended[right] - targets < targets - extended[left], right, left)
    return owners[pick]


def _on_azimuth_grid(sweep: RadarSweep, values: np.ndarray, bins: np.ndarray) -> np.ndarray:
    """Values of the rays nearest each kept bin centre, NaN where no ray is within reach."""
    centres = azimuth_bins()[bins]
    rays = _nearest_rays(sweep.azimuth, centres)
    gap = np.abs((sweep.azimuth[rays] - centres + 180.0) % 360.0 - 180.0)
    out = values[rays]
    out[gap > 0.75 * sweep.azimuth_resolution] = np.nan
    return out


# Writing -------------------------------------------------------------------------------------------


def standardize_nexrad_level2(
    volumes: Iterable[FetchedVolume],
    h5file: h5py.File,
    *,
    site: str,
    bbox,
    start: datetime,
    end: datetime,
    fields: Sequence[str] = DEFAULT_FIELDS,
    max_height: float = DEFAULT_MAX_HEIGHT,
    time_step_min: int = 0,
    overwrite: bool = False,
    compression_lvl: int = 6,
) -> h5py.Group:
    """
    Write one radar site, ``/spatial_3d/radar/<site>``, from NEXRAD Level II volumes.

    Volumes are read one at a time and their sweeps appended, so memory holds one volume. Each
    volume read is a row of ``volumes/`` with its S3 key and SHA-256; a volume that could not be
    fetched or read is no row and its key is in ``failed``. Volumes whose start is outside
    ``[start, end)`` are skipped. The iterable is consumed once, so it may delete each file after
    it is read (``fetch_volumes``).

    Parameters
    ----------
    volumes : Iterable[FetchedVolume]
        Volumes of one site, in time order.
    h5file : h5py.File
        The standard file to write to.
    site : str
        The ICAO identifier, e.g. ``KDAX``.
    bbox : sequence of float
        The frame, ``(west, south, east, north)`` in degrees.
    start, end : datetime
        The window, aware.
    fields : sequence of str
        Level II moments to keep: ``DBZH``, ``RHOHV``, ``ZDR``, ``VRADH``.
    max_height : float
        Ceiling of the crop, in m above mean sea level.
    time_step_min : int
        The selection step the caller used, recorded in the group (0: every volume).

    Raises
    ------
    ValueError
        If the volumes come from another site, none could be read, a field is unknown, or the group
        exists and ``overwrite`` is False.
    """
    check_std_version(h5file)
    start, end = _utc(start), _utc(end)
    frame = _bbox(bbox)
    fields = tuple(dict.fromkeys(fields))
    unknown = [name for name in fields if name not in FIELDS]
    if unknown or not fields:
        raise ValueError(
            f"unknown or missing radar fields {unknown or list(fields)}; known: {', '.join(FIELDS)}"
        )
    path = f"{GROUP}/{site}"
    if path in h5file and not overwrite:
        raise ValueError(f"group {path} already exists in {h5file.filename}. Set `overwrite` to True.")

    writer: _SiteWriter | None = None
    failed, rows = [], []
    bucket = BUCKET
    for fetched in volumes:
        volume_ref = fetched.volume
        bucket = volume_ref.bucket
        if volume_ref.site != site:
            raise ValueError(f"a volume of {volume_ref.site} cannot be written to the group of {site}")
        if not start <= volume_ref.time_start < end:
            continue
        if fetched.path is None:
            failed.append({"key": volume_ref.key, "reason": fetched.error or "not fetched"})
            continue
        try:
            volume = read_level2_volume(fetched.path, fields)
            if writer is None:
                writer = _SiteWriter(
                    h5file, path, volume, frame, fields, max_height, start, compression_lvl
                )
            sweeps = writer.append(volume, len(rows))
        except ValueError as error:
            failed.append({"key": volume_ref.key, "reason": f"unreadable: {error}"})
            continue
        rows.append((volume_ref, fetched.sha256, volume, sweeps))
    if writer is None or not rows:
        if writer is not None:
            del h5file[path]
        raise ValueError(f"no NEXRAD volume of {site} could be read")

    volumes_group = writer.group.create_group(VOLUMES)
    columns = {
        svn.TIME.value: (_seconds([row[2].time_start for row in rows], start), _time_attrs(start)),
        "time_end": (_seconds([row[2].time_end for row in rows], start), _time_attrs(start)),
        "vcp": (
            np.array([row[2].vcp if row[2].vcp is not None else -1 for row in rows], dtype=np.int16),
            {"_FillValue": np.int16(-1)},
        ),
        "n_sweeps": (np.array([row[3] for row in rows], dtype=np.int16), {"units": "1"}),
        # Fixed-length ASCII: the signing digest reads variable-length strings as object arrays, whose
        # bytes are pointers, so it would differ from one read to the next.
        "source_key": (np.array([row[0].key.encode("ascii") for row in rows]), {}),
        "source_sha256": (np.array([(row[1] or "").encode("ascii") for row in rows]), {}),
    }
    for name, (data, attrs) in columns.items():
        dtype = h5py.string_dtype() if data.dtype == object else data.dtype
        dataset = volumes_group.create_dataset(
            name,
            data=data,
            dtype=dtype,
            fillvalue=attrs.get("_FillValue"),
            **hdf5plugin.Zstd(clevel=compression_lvl),
        )
        for key, value in attrs.items():
            dataset.attrs[key] = value
    group = writer.group
    group.attrs["failed"] = json.dumps(failed)
    group.attrs["volumes_complete"] = not failed
    group.attrs["time_step"] = int(time_step_min)
    group.attrs["time_step_units"] = "min"
    group.attrs["data_source"] = f"s3://{bucket}"
    group.attrs["source_files"] = json.dumps({"bucket": bucket, "volumes": len(rows)})
    logger.info(
        "[radar] %s: %d sweeps in %d volumes, %d failed",
        site,
        writer.n_rows,
        len(rows),
        len(failed),
    )
    return group


class _SiteWriter:  # pylint: disable=too-many-instance-attributes
    """Creates the group of a site from its first volume, then appends the sweeps of each volume."""

    def __init__(
        self, h5file, path, volume: RadarVolume, frame, fields, max_height, origin, compression_lvl
    ):
        first_gate = min(sweep.first_gate for sweep in volume.sweeps)
        self.bins, self.gates = frame_axes(
            volume.latitude, volume.longitude, volume.altitude, frame, max_height, first_gate
        )
        site = path.rsplit("/", 1)[-1]
        self.fields = fields
        self.origin = origin
        self.n_rows = 0
        if path in h5file:
            del h5file[path]
        # The parent groups carry no attribute, so fragments that each hold a site merge without conflict.
        self.group = h5file.require_group(f"/{SPATIAL_3D}").require_group(RADAR).create_group(site)
        west, south, east, north = frame
        attrs = {
            "site": site,
            "instrument": "WSR-88D",
            "provider": "NOAA NEXRAD",
            "product": "NEXRAD Level II",
            "crs": CRS,
            "position_origin_lat": volume.latitude,
            "position_origin_lat_units": "degree",
            "position_origin_lon": volume.longitude,
            "position_origin_lon_units": "degree",
            "position_origin_alt": volume.altitude,
            "position_origin_alt_units": "m",
            "beam_width": BEAM_WIDTH,
            "beam_width_units": "degree",
            "azimuth_step": AZIMUTH_STEP,
            "azimuth_step_units": "degree",
            "gate_spacing": GATE_SPACING,
            "gate_spacing_units": "m",
            "max_height": float(max_height),
            "max_height_units": "m",
            "effective_earth_radius": EFFECTIVE_RADIUS,
            "effective_earth_radius_units": "m",
            "fields": json.dumps([FIELDS[name][0] for name in fields]),
            "time_start": origin.isoformat(),
            "time_end": "",
            "description": f"WSR-88D {site} polar sweeps over the frame, from NEXRAD Level II",
        }
        for name, value in (("west", west), ("south", south), ("east", east), ("north", north)):
            attrs[f"frame_{name}"] = float(value)
            attrs[f"frame_{name}_units"] = "degree"
        for key, value in attrs.items():
            self.group.attrs[key] = value
        compression = hdf5plugin.Zstd(clevel=compression_lvl)
        azimuth = self.group.create_dataset("azimuth", data=azimuth_bins()[self.bins].astype(np.float32))
        azimuth.attrs["units"] = "degree"
        azimuth.attrs["description"] = "Centre of the azimuth bin, clockwise from true north"
        slant = self.group.create_dataset("range", data=self.gates.astype(np.float32))
        slant.attrs["units"] = "m"
        slant.attrs["description"] = "Slant range of the gate centre"
        shape = (len(self.bins), len(self.gates))
        self.rows = {}
        for name, dtype, attrs in (
            (svn.TIME.value, np.float64, _time_attrs(origin)),
            ("elevation", np.float32, {"units": "degree"}),
            ("volume_index", np.int32, {"units": "1"}),
            ("azimuth_resolution", np.float32, {"units": "degree"}),
            ("nyquist_velocity", np.float32, {"units": "m/s"}),
        ):
            dataset = self.group.create_dataset(
                name, shape=(0,), maxshape=(None,), dtype=dtype, chunks=(1024,), **compression
            )
            for key, value in attrs.items():
                dataset.attrs[key] = value
            self.rows[name] = dataset
        self.data = {}
        for name in fields:
            standard, units = FIELDS[name]
            dataset = self.group.create_dataset(
                standard,
                shape=(0, *shape),
                maxshape=(None, *shape),
                dtype=np.float32,
                chunks=(1, *shape),
                fillvalue=np.float32(np.nan),
                **compression,
            )
            dataset.attrs["units"] = units
            dataset.attrs["source_moment"] = name
            self.data[name] = dataset
        self.end = origin

    def append(self, volume: RadarVolume, volume_index: int) -> int:
        """Append the sweeps of a volume; returns how many rows it gave."""
        first = self.gates[0]
        blocks = []
        for sweep in volume.sweeps:
            offset = (sweep.first_gate - first) / GATE_SPACING
            if abs(offset - round(offset)) > 1e-3:
                raise ValueError(f"first gate at {sweep.first_gate} m is off the 250 m grid of the file")
            offset = int(round(offset))
            block = {}
            for name in self.fields:
                values = sweep.data.get(name)
                out = np.full((len(self.bins), len(self.gates)), np.nan, dtype=np.float32)
                if values is not None:
                    grid = _on_azimuth_grid(sweep, values, self.bins)
                    # Gate k of the sweep is gate k + offset of the file.
                    lo, hi = max(0, -offset), min(grid.shape[1], len(self.gates) - offset)
                    if hi > lo:
                        out[:, lo + offset : hi + offset] = grid[:, lo:hi]
                block[name] = out
            blocks.append((sweep, block))
        count = len(blocks)
        size = self.n_rows + count
        for dataset in (*self.rows.values(), *self.data.values()):
            dataset.resize(size, axis=0)
        self.rows[svn.TIME.value][self.n_rows : size] = _seconds(
            [sweep.time for sweep, _ in blocks], self.origin
        )
        self.rows["elevation"][self.n_rows : size] = [sweep.elevation for sweep, _ in blocks]
        self.rows["volume_index"][self.n_rows : size] = volume_index
        self.rows["azimuth_resolution"][self.n_rows : size] = [
            sweep.azimuth_resolution for sweep, _ in blocks
        ]
        self.rows["nyquist_velocity"][self.n_rows : size] = [sweep.nyquist_velocity for sweep, _ in blocks]
        for position, (_, block) in enumerate(blocks):
            for name, values in block.items():
                self.data[name][self.n_rows + position] = values
        self.n_rows = size
        self.group.attrs["time_end"] = max(volume.time_end, self.end).isoformat()
        self.end = max(volume.time_end, self.end)
        return count


# Reading the standard file --------------------------------------------------------------------------


def list_radar_sites(h5file: h5py.File) -> list[str]:
    """The radar sites of a file, sorted. An empty list when the group is absent."""
    group = h5file.get(GROUP)
    if not isinstance(group, h5py.Group):
        return []
    return sorted(name for name, item in group.items() if isinstance(item, h5py.Group))


def radar_echo_top_series(
    h5file: h5py.File | Path | str,
    site: str,
    *,
    min_dbz: float = DEFAULT_MIN_DBZ,
    rhohv_range: tuple[float, float] | None = DEFAULT_RHOHV_RANGE,
    quantiles: Sequence[float] = (0.75, 0.9),
    corners=None,
) -> EchoTopSeries:
    """
    Height of the plume gates of each volume of a site, in m above mean sea level.

    A gate counts when its reflectivity is at least ``min_dbz``, its correlation coefficient is
    strictly between the bounds of ``rhohv_range`` (None: not tested), and the ground under it is
    inside ``corners``, ``((lat, lon), (lat, lon))``, or the site's frame when None. Heights are
    those of the beam centre. A volume with no gate counted has NaN heights and a count of 0.
    """
    if not isinstance(h5file, h5py.File):
        with h5py.File(h5file, "r") as opened:
            return radar_echo_top_series(
                opened, site, min_dbz=min_dbz, rhohv_range=rhohv_range, quantiles=quantiles, corners=corners
            )
    reader = _SiteReader(h5file, site, corners)
    n_volumes = reader.n_volumes
    height_max = np.full(n_volumes, np.nan)
    levels = {float(q): np.full(n_volumes, np.nan) for q in quantiles}
    counts = np.zeros(n_volumes, dtype=np.int64)
    for volume in range(n_volumes):
        heights = []
        for row in reader.rows_of(volume):
            mask = reader.plume_mask(row, min_dbz, rhohv_range)
            if mask.any():
                heights.append(reader.geometry(row)[0][mask])
        if heights:
            values = np.concatenate(heights)
            counts[volume] = len(values)
            height_max[volume] = float(values.max())
            for level, series in levels.items():
                series[volume] = float(np.quantile(values, level))
    return EchoTopSeries(
        site=site,
        time=reader.volume_times(),
        height_max=height_max,
        height_quantiles=levels,
        n_gates=counts,
    )


def radar_composite(
    h5file: h5py.File | Path | str,
    site: str,
    volume: int,
    *,
    field: str = svn.RADAR_REFLECTIVITY.value,
    min_dbz: float = DEFAULT_MIN_DBZ,
    rhohv_range: tuple[float, float] | None = DEFAULT_RHOHV_RANGE,
    resolution: float = 0.01,
    corners=None,
) -> RadarComposite:
    """
    The column maximum of ``field`` over the plume gates of one volume, on a lon/lat grid.

    The grid covers ``corners`` (or the site's frame) in cells of ``resolution`` degree; a gate is
    placed in the cell under its beam centre. The plume mask is the one of
    :func:`radar_echo_top_series`. Cells no counted gate falls in are NaN.
    """
    if not isinstance(h5file, h5py.File):
        with h5py.File(h5file, "r") as opened:
            return radar_composite(
                opened,
                site,
                volume,
                field=field,
                min_dbz=min_dbz,
                rhohv_range=rhohv_range,
                resolution=resolution,
                corners=corners,
            )
    reader = _SiteReader(h5file, site, corners)
    if not 0 <= volume < reader.n_volumes:
        raise ValueError(f"volume {volume} is not one of the {reader.n_volumes} volumes of {site}")
    if field not in reader.group:
        raise ValueError(f"{site} has no field {field!r}")
    west, south, east, north = reader.box
    n_lon = max(1, int(np.ceil((east - west) / resolution - 1e-9)))
    n_lat = max(1, int(np.ceil((north - south) / resolution - 1e-9)))
    grid = np.full(n_lat * n_lon, -np.inf, dtype=np.float64)
    for row in reader.rows_of(volume):
        mask = reader.plume_mask(row, min_dbz, rhohv_range)
        values = reader.group[field][row][mask].astype(np.float64)
        keep = np.isfinite(values)
        if not keep.any():
            continue
        _, lat, lon = reader.geometry(row)
        col = np.clip(((lon[mask][keep] - west) / resolution).astype(np.int64), 0, n_lon - 1)
        line = np.clip(((north - lat[mask][keep]) / resolution).astype(np.int64), 0, n_lat - 1)
        np.maximum.at(grid, line * n_lon + col, values[keep])
    grid[~np.isfinite(grid)] = np.nan
    return RadarComposite(
        site=site,
        time=reader.volume_times()[volume],
        field=field,
        bounds=(west, north - n_lat * resolution, west + n_lon * resolution, north),
        resolution=resolution,
        values=grid.reshape(n_lat, n_lon).astype(np.float32),
    )


class _SiteReader:
    """The geometry and masks of one site of a standard file, cached per elevation."""

    def __init__(self, h5file: h5py.File, site: str, corners):
        group = h5file.get(f"{GROUP}/{site}")
        if not isinstance(group, h5py.Group):
            raise ValueError(f"no radar site {site!r}; the file has {list_radar_sites(h5file)}")
        self.group = group
        attrs = group.attrs
        self.origin = (
            float(attrs["position_origin_lat"]),
            float(attrs["position_origin_lon"]),
            float(attrs["position_origin_alt"]),
        )
        if corners is None:
            self.box = tuple(float(attrs[f"frame_{name}"]) for name in ("west", "south", "east", "north"))
        else:
            (lat_a, lon_a), (lat_b, lon_b) = corners
            self.box = (min(lon_a, lon_b), min(lat_a, lat_b), max(lon_a, lon_b), max(lat_a, lat_b))
        self.azimuth = group["azimuth"][()].astype(np.float64)
        self.range = group["range"][()].astype(np.float64)
        self.elevation = group["elevation"][()].astype(np.float64)
        self.volume_index = group["volume_index"][()].astype(np.int64)
        self.n_volumes = len(group[VOLUMES][svn.TIME.value])
        self.fields = [name for name in json.loads(_text(attrs.get("fields", "[]"))) if name in group]
        self._geometry: dict[float, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}

    def volume_times(self) -> np.ndarray:
        """Start of each volume, as datetime64[ms] UTC."""
        dataset = self.group[VOLUMES][svn.TIME.value]
        origin = _utc(datetime.fromisoformat(_text(dataset.attrs["time_origin"])))
        seconds = dataset[()].astype(np.float64)
        return np.datetime64(origin.replace(tzinfo=None), "ms") + np.round(seconds * 1000).astype(
            "timedelta64[ms]"
        )

    def rows_of(self, volume: int) -> np.ndarray:
        """The sweep rows of a volume."""
        return np.nonzero(self.volume_index == volume)[0]

    def geometry(self, row: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Height above mean sea level, latitude, and longitude of the beam centre of each cell."""
        height, lat, lon, _ = self._cells(float(self.elevation[row]))
        return height, lat, lon

    def plume_mask(self, row: int, min_dbz: float, rhohv_range) -> np.ndarray:
        """The cells of a row over the box that pass the plume thresholds."""
        _, _, _, inside = self._cells(float(self.elevation[row]))
        reflectivity = svn.RADAR_REFLECTIVITY.value
        if reflectivity not in self.group:
            raise ValueError(f"{self.group.name} has no {reflectivity}")
        values = self.group[reflectivity][row]
        with np.errstate(invalid="ignore"):
            mask = inside & (values >= min_dbz)
            if rhohv_range is not None:
                rhohv = svn.RADAR_CORRELATION_COEFFICIENT.value
                if rhohv not in self.group:
                    raise ValueError(f"{self.group.name} has no {rhohv}; pass rhohv_range=None")
                low, high = rhohv_range
                correlation = self.group[rhohv][row]
                mask &= (correlation > low) & (correlation < high)
        return mask

    def _cells(self, elevation: float):
        key = round(elevation, 4)
        if key not in self._geometry:
            lat0, lon0, alt0 = self.origin
            height = beam_height(self.range, elevation, alt0)
            ground = beam_ground_distance(self.range, elevation)
            azimuth, distance = np.meshgrid(self.azimuth, ground, indexing="ij")
            lon, lat, _ = _GEOD.fwd(
                np.full(azimuth.size, lon0), np.full(azimuth.size, lat0), azimuth.ravel(), distance.ravel()
            )
            lat, lon = lat.reshape(azimuth.shape), lon.reshape(azimuth.shape)
            west, south, east, north = self.box
            inside = (lon >= west) & (lon <= east) & (lat >= south) & (lat <= north)
            self._geometry[key] = (np.broadcast_to(height, azimuth.shape), lat, lon, inside)
        return self._geometry[key]


# Points and cross sections -------------------------------------------------------------------------


@dataclass(frozen=True)
class RadarPoints:
    """The plume gates of one volume: where their beam centre is, and the values stored there."""

    site: str
    time: np.datetime64  # volume start
    longitude: np.ndarray  # degree
    latitude: np.ndarray  # degree
    height: np.ndarray  # m above mean sea level
    values: dict[str, np.ndarray]  # standard field name -> one value per point, NaN where none
    # Gates over the box with a reflectivity, before the plume mask.
    n_gates: int


def radar_points(
    h5file: h5py.File | Path | str,
    site: str,
    volume: int,
    *,
    min_dbz: float = DEFAULT_MIN_DBZ,
    rhohv_range: tuple[float, float] | None = DEFAULT_RHOHV_RANGE,
    corners=None,
) -> RadarPoints:
    """
    The gates of one volume that pass the plume mask of :func:`radar_echo_top_series`, as points.

    Each gate is placed at its beam centre, with the value of every field of the site there, sweep
    after sweep. ``corners`` is ``((lat, lon), (lat, lon))``, or None for the site's frame.
    """
    if not isinstance(h5file, h5py.File):
        with h5py.File(h5file, "r") as opened:
            return radar_points(
                opened, site, volume, min_dbz=min_dbz, rhohv_range=rhohv_range, corners=corners
            )
    reader = _SiteReader(h5file, site, corners)
    if not 0 <= volume < reader.n_volumes:
        raise ValueError(f"volume {volume} is not one of the {reader.n_volumes} volumes of {site}")
    fields = reader.fields
    parts: dict[str, list[np.ndarray]] = {name: [] for name in ("lon", "lat", "height", *fields)}
    n_gates = 0
    reflectivity = svn.RADAR_REFLECTIVITY.value
    for row in reader.rows_of(volume):
        mask = reader.plume_mask(row, min_dbz, rhohv_range)
        _, _, _, inside = reader._cells(float(reader.elevation[row]))  # pylint: disable=protected-access
        n_gates += int((inside & np.isfinite(reader.group[reflectivity][row])).sum())
        if not mask.any():
            continue
        height, lat, lon = reader.geometry(row)
        parts["lon"].append(lon[mask])
        parts["lat"].append(lat[mask])
        parts["height"].append(height[mask])
        for name in fields:
            parts[name].append(reader.group[name][row][mask].astype(np.float32))

    def joined(name: str, dtype) -> np.ndarray:
        return np.concatenate(parts[name]).astype(dtype) if parts[name] else np.zeros(0, dtype=dtype)

    return RadarPoints(
        site=site,
        time=reader.volume_times()[volume],
        longitude=joined("lon", np.float64),
        latitude=joined("lat", np.float64),
        height=joined("height", np.float64),
        values={name: joined(name, np.float32) for name in fields},
        n_gates=n_gates,
    )


@dataclass(frozen=True)
class RadarPlane:  # pylint: disable=too-many-instance-attributes
    """
    A rectangle of a plane, given by three points, and the nodes of its grid.

    The plane is flat in a local frame: east and north of an azimuthal equidistant projection
    centred on P1, and the altitude above mean sea level. ``u`` runs from P1 towards P2, ``v`` across
    towards P3, so the rectangle is ``u`` from 0 to the length of P1P2 and ``v`` from 0 to the
    distance of P3 from the line P1P2. A vertical section is P1 and P2 at its floor and P3 above P1
    at its top.
    """

    points: tuple[tuple[float, float, float], ...]  # P1, P2, P3: (lat, lon, alt m above mean sea level)
    spacing: float  # m between nodes, both axes
    u: np.ndarray  # (n_u,) m from P1 along P1P2
    v: np.ndarray  # (n_v,) m from P1 across, in the plane
    latitude: np.ndarray  # (n_v, n_u) degree
    longitude: np.ndarray  # (n_v, n_u) degree
    height: np.ndarray  # (n_v, n_u) m above mean sea level

    @classmethod
    def from_points(cls, p1, p2, p3, spacing: float = 250.0) -> "RadarPlane":
        """
        The plane through P1, P2, and P3, each ``(lat, lon, alt)``, with nodes every ``spacing``.

        Raises
        ------
        ValueError
            If the points are collinear (P3 within ``spacing`` of the line P1P2), the spacing is
            outside the bounds of ``radar.toml``, a side is longer than ``max_length``, the altitudes
            span more than ``max_span``, or the grid has more than ``max_cells`` nodes.
        """
        parameters = radar_parameters()
        spacing = float(spacing)
        if not parameters.min_spacing <= spacing <= parameters.max_spacing:
            raise ValueError(
                f"a section's spacing is {parameters.min_spacing:.0f} to {parameters.max_spacing:.0f} m, "
                f"not {spacing:g} m"
            )
        points = tuple(tuple(float(value) for value in point) for point in (p1, p2, p3))
        for lat, lon, _ in points:
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(f"({lat}, {lon}) is not a latitude and a longitude in degrees")
        proj = Proj(proj="aeqd", lat_0=points[0][0], lon_0=points[0][1], ellps="WGS84")
        local = np.array([(*proj(lon, lat), alt) for lat, lon, alt in points], dtype=np.float64)
        along = local[1] - local[0]
        length_u = float(np.linalg.norm(along))
        if length_u < spacing:
            raise ValueError("P1 and P2 of a section are closer than its spacing")
        unit_u = along / length_u
        across = local[2] - local[0]
        across = across - (across @ unit_u) * unit_u
        length_v = float(np.linalg.norm(across))
        if length_v < spacing:
            raise ValueError("the three points of a section are on one line: P3 must stand off P1P2")
        unit_v = across / length_v
        if max(length_u, length_v) > parameters.max_length:
            raise ValueError(
                f"a side of the section is {max(length_u, length_v) / 1000:.1f} km; "
                f"the longest allowed is {parameters.max_length / 1000:.0f} km"
            )
        u = spacing * np.arange(int(np.floor(length_u / spacing + 1e-9)) + 1)
        v = spacing * np.arange(int(np.floor(length_v / spacing + 1e-9)) + 1)
        if len(u) * len(v) > parameters.max_cells:
            raise ValueError(
                f"the section has {len(u) * len(v):,} cells; the most allowed is {parameters.max_cells:,}: "
                "make it smaller or its spacing larger"
            )
        corners = [local[0] + a * unit_u + b * unit_v for a in (0, u[-1]) for b in (0, v[-1])]
        span = max(corner[2] for corner in corners) - min(corner[2] for corner in corners)
        if span > parameters.max_span:
            raise ValueError(
                f"the section spans {span / 1000:.1f} km of altitude; "
                f"at most {parameters.max_span / 1000:.0f} km"
            )
        grid = local[0] + u[None, :, None] * unit_u + v[:, None, None] * unit_v
        lon, lat = proj(grid[..., 0], grid[..., 1], inverse=True)
        return cls(
            points=points,
            spacing=spacing,
            u=u,
            v=v,
            latitude=np.asarray(lat),
            longitude=np.asarray(lon),
            height=grid[..., 2],
        )


@dataclass(frozen=True)
class RadarSection:  # pylint: disable=too-many-instance-attributes
    """The volumes of a site cut on a plane: one grid of each field per volume."""

    site: str
    name: str
    plane: RadarPlane
    time: np.ndarray  # (n_volume,) datetime64[ms], volume start
    values: dict[str, np.ndarray]  # standard field name -> (n_volume, n_v, n_u) float32, NaN where none
    elevation: np.ndarray  # (n_volume, n_v, n_u) degree: the sweep radial velocity was read on
    nyquist_velocity: np.ndarray  # (n_volume, n_v, n_u) m/s, of that sweep
    azimuth: np.ndarray  # (n_v, n_u) degree, from the radar to the node, clockwise from true north
    beam_elevation: np.ndarray  # (n_v, n_u) degree, of the beam through the node


def beam_elevation_range(ground_distance, height_above_antenna) -> tuple[np.ndarray, np.ndarray]:
    """
    The elevation and slant range of the beam whose centre passes over a point, with the 4/3 Earth.

    The inverse of :func:`beam_height` and :func:`beam_ground_distance`: ``ground_distance`` is the
    distance along the ground from the radar, ``height_above_antenna`` the height of the point above
    the antenna, both in m. Returns degrees and metres.
    """
    s = np.asarray(ground_distance, dtype=np.float64)
    h = np.asarray(height_above_antenna, dtype=np.float64)
    radius = EFFECTIVE_RADIUS
    angle = s / radius
    elevation = np.degrees(np.arctan2((radius + h) * np.cos(angle) - radius, (radius + h) * np.sin(angle)))
    slant = np.sqrt(radius**2 + (radius + h) ** 2 - 2 * radius * (radius + h) * np.cos(angle))
    return elevation, slant


def radar_cross_section(
    h5file: h5py.File | Path | str,
    site: str,
    plane: RadarPlane,
    *,
    name: str,
    fields: Sequence[str] | None = None,
) -> RadarSection:
    """
    Every volume of a site cut on a plane.

    Each node of the plane is placed in the radar's beam geometry (:func:`beam_elevation_range`),
    then read from the nearest azimuth bin and range gate of the sweeps of each volume:

    - between the two sweeps whose elevations bracket the node's, the value is linear in elevation:
      reflectivity in linear units, the other fields as stored. It is NaN when either sweep has no
      value there, or the two are more than ``max_elevation_gap`` (``radar.toml``) apart;
    - below the lowest sweep or above the highest one, the value of that sweep within half a beam
      width, NaN beyond;
    - radial velocity is never interpolated, since it is aliased: it is the value of the nearest of
      those sweeps, whose elevation and Nyquist velocity the section records.

    A tilt scanned twice in a volume (SAILS) is read from its first scan. ``fields`` are standard
    names; None keeps every field of the site.
    """
    if not isinstance(h5file, h5py.File):
        with h5py.File(h5file, "r") as opened:
            return radar_cross_section(opened, site, plane, name=name, fields=fields)
    if not _SECTION_NAME.match(name):
        raise ValueError(
            f"a section's name is 1 to 40 lower-case letters, digits, and hyphens, not {name!r}"
        )
    reader = _SiteReader(h5file, site, None)
    fields = list(reader.fields if fields is None else fields)
    missing = [field for field in fields if field not in reader.fields]
    if missing:
        raise ValueError(f"{site} has no field {', '.join(missing)}; it has {', '.join(reader.fields)}")
    lat0, lon0, alt0 = reader.origin
    shape = plane.latitude.shape
    forward, _, distance = _GEOD.inv(
        np.full(plane.longitude.size, lon0),
        np.full(plane.longitude.size, lat0),
        plane.longitude.ravel(),
        plane.latitude.ravel(),
    )
    azimuth = np.mod(np.asarray(forward), 360.0)
    elevation, slant = beam_elevation_range(np.asarray(distance), plane.height.ravel() - alt0)
    # The bin and gate of each node; -1 off the site's axes.
    first_bin = int(round(float(reader.azimuth[0]) / AZIMUTH_STEP - 0.5))
    column = np.mod(np.floor(azimuth / AZIMUTH_STEP).astype(np.int64) - first_bin, N_AZIMUTH)
    column = np.where(column < len(reader.azimuth), column, -1)
    gate = np.rint((slant - reader.range[0]) / GATE_SPACING).astype(np.int64)
    gate = np.where((gate >= 0) & (gate < len(reader.range)), gate, -1)
    on_axes = (column >= 0) & (gate >= 0)

    parameters = radar_parameters()
    half_beam = float(reader.group.attrs.get("beam_width", BEAM_WIDTH)) / 2
    n_volumes = reader.n_volumes
    values = {field: np.full((n_volumes, elevation.size), np.nan, dtype=np.float32) for field in fields}
    used_elevation = np.full((n_volumes, elevation.size), np.nan, dtype=np.float32)
    nyquist = np.full((n_volumes, elevation.size), np.nan, dtype=np.float32)
    velocity = svn.RADAR_RADIAL_VELOCITY.value
    sweep_nyquist = reader.group["nyquist_velocity"][()]
    for volume in range(n_volumes):
        rows = _first_scans(reader, volume)
        if rows.size == 0:
            continue
        tilts = reader.elevation[rows]
        above = np.searchsorted(tilts, elevation)  # first tilt at or above each node
        low = np.clip(above - 1, 0, len(rows) - 1)
        high = np.clip(above, 0, len(rows) - 1)
        below_all, above_all = above == 0, above == len(rows)
        between = ~below_all & ~above_all
        gap = tilts[high] - tilts[low]
        weight = np.where(between & (gap > 0), (elevation - tilts[low]) / np.where(gap > 0, gap, 1.0), 0.0)
        covered = on_axes & (
            (below_all & (tilts[0] - elevation <= half_beam))
            | (above_all & (elevation - tilts[-1] <= half_beam))
            | (between & (gap <= parameters.max_elevation_gap))
        )
        # Outside the sweeps, both ends are the outermost sweep.
        low = np.where(above_all, len(rows) - 1, low)
        high = np.where(below_all, 0, high)
        nearest = np.where(weight <= 0.5, low, high)
        index = np.nonzero(covered)[0]
        if index.size == 0:
            continue
        cols, gates_ = column[index], gate[index]
        for field in fields:
            stack = np.stack([reader.group[field][row] for row in rows])
            if field == velocity:
                values[field][volume, index] = stack[nearest[index], cols, gates_]
                continue
            first, second = stack[low[index], cols, gates_], stack[high[index], cols, gates_]
            share = weight[index]
            if field == svn.RADAR_REFLECTIVITY.value:
                with np.errstate(invalid="ignore"):
                    linear = (1 - share) * 10 ** (first / 10.0) + share * 10 ** (second / 10.0)
                    values[field][volume, index] = 10.0 * np.log10(linear)
            else:
                values[field][volume, index] = (1 - share) * first + share * second
        used_elevation[volume, index] = tilts[nearest[index]]
        nyquist[volume, index] = sweep_nyquist[rows][nearest[index]]
    grid = (n_volumes, *shape)
    return RadarSection(
        site=site,
        name=name,
        plane=plane,
        time=reader.volume_times(),
        values={field: data.reshape(grid) for field, data in values.items()},
        elevation=used_elevation.reshape(grid),
        nyquist_velocity=nyquist.reshape(grid),
        azimuth=azimuth.reshape(shape).astype(np.float32),
        beam_elevation=elevation.reshape(shape).astype(np.float32),
    )


def _first_scans(reader: "_SiteReader", volume: int) -> np.ndarray:
    """The rows of a volume, one per tilt (the first scan of a tilt scanned twice), by elevation."""
    rows = reader.rows_of(volume)
    kept: dict[float, int] = {}
    for row in rows:
        kept.setdefault(round(float(reader.elevation[row]), 2), int(row))
    return np.array([kept[key] for key in sorted(kept)], dtype=np.int64)


def write_radar_sections(
    h5file: h5py.File, site: str, sections: Sequence[RadarSection], compression_lvl: int = 6
) -> None:
    """
    Store sections under ``/spatial_3d/radar/<site>/sections/<name>``, replacing one of the same name.

    ``sections/`` carries no attribute. Times are in s from the origin of the site's volumes.
    """
    check_std_version(h5file)
    path = f"{GROUP}/{site}"
    if path not in h5file:
        raise ValueError(f"no radar site {site!r}; the file has {list_radar_sites(h5file)}")
    site_group = h5file[path]
    origin = _text(site_group[VOLUMES][svn.TIME.value].attrs["time_origin"])
    parent = site_group.require_group(SECTIONS)
    compression = hdf5plugin.Zstd(clevel=compression_lvl)
    parameters = radar_parameters()
    for section in sections:
        if section.site != site:
            raise ValueError(f"a section of {section.site} cannot be written to the group of {site}")
        if section.name in parent:
            del parent[section.name]
        group = parent.create_group(section.name)
        plane = section.plane
        for index, point in enumerate(plane.points, start=1):
            group.attrs[f"point_{index}"] = np.array(point, dtype=np.float64)
            group.attrs[f"point_{index}_units"] = "degree, degree, m"
        group.attrs["spacing"] = plane.spacing
        group.attrs["spacing_units"] = "m"
        group.attrs["parameters"] = f"radar {parameters.version}"
        group.attrs["computed_by"] = "firebench.standardize.radar_cross_section"
        group.attrs["description"] = (
            f"{site} volumes cut on a plane through point_1, point_2, and point_3 (lat, lon, alt above "
            "mean sea level): u along point_1 to point_2, v across towards point_3"
        )
        start = _utc(datetime.fromisoformat(origin))
        seconds = (section.time - np.datetime64(start.replace(tzinfo=None), "ms")) / np.timedelta64(1, "s")
        datasets = {
            "u": (plane.u, {"units": "m", "description": "Distance from point_1 along point_1 to point_2"}),
            "v": (plane.v, {"units": "m", "description": "Distance from point_1 across, towards point_3"}),
            "position_lat": (plane.latitude, {"units": "degree"}),
            "position_lon": (plane.longitude, {"units": "degree"}),
            "position_alt": (plane.height, {"units": "m", "description": "Above mean sea level"}),
            "azimuth": (
                section.azimuth,
                {"units": "degree", "description": "From the radar, clockwise from north"},
            ),
            "beam_elevation": (section.beam_elevation, {"units": "degree"}),
            svn.TIME.value: (seconds.astype(np.float64), _time_attrs(start)),
            "elevation": (
                section.elevation,
                {"units": "degree", "description": "Elevation of the sweep radial velocity was read on"},
            ),
            "nyquist_velocity": (
                section.nyquist_velocity,
                {"units": "m/s", "description": "Of that sweep"},
            ),
        }
        for field, data in section.values.items():
            units = _text(site_group[field].attrs.get("units", ""))
            datasets[field] = (data, {"units": units})
        for name, (data, attrs) in datasets.items():
            data = np.asarray(data)
            options = compression if data.ndim and data.size > 1 else {}
            dataset = group.create_dataset(name, data=data, **options)
            for key, value in attrs.items():
                dataset.attrs[key] = value


def list_radar_sections(h5file: h5py.File, site: str) -> list[str]:
    """The sections of a site, sorted. An empty list when it has none."""
    group = h5file.get(f"{GROUP}/{site}/{SECTIONS}")
    if not isinstance(group, h5py.Group):
        return []
    return sorted(name for name, item in group.items() if isinstance(item, h5py.Group))


def read_radar_section(h5file: h5py.File | Path | str, site: str, name: str) -> RadarSection:
    """A section as :func:`write_radar_sections` stored it."""
    if not isinstance(h5file, h5py.File):
        with h5py.File(h5file, "r") as opened:
            return read_radar_section(opened, site, name)
    path = f"{GROUP}/{site}/{SECTIONS}/{name}"
    group = h5file.get(path)
    if not isinstance(group, h5py.Group):
        raise ValueError(f"no radar section {site}/{name}; {site} has {list_radar_sections(h5file, site)}")
    plane = RadarPlane(
        points=tuple(tuple(float(value) for value in group.attrs[f"point_{index}"]) for index in (1, 2, 3)),
        spacing=float(group.attrs["spacing"]),
        u=group["u"][()],
        v=group["v"][()],
        latitude=group["position_lat"][()],
        longitude=group["position_lon"][()],
        height=group["position_alt"][()],
    )
    time = group[svn.TIME.value]
    origin = _utc(datetime.fromisoformat(_text(time.attrs["time_origin"])))
    times = np.datetime64(origin.replace(tzinfo=None), "ms") + np.round(time[()] * 1000).astype(
        "timedelta64[ms]"
    )
    site_fields = json.loads(_text(h5file[f"{GROUP}/{site}"].attrs.get("fields", "[]")))
    return RadarSection(
        site=site,
        name=name,
        plane=plane,
        time=times,
        values={field: group[field][()] for field in site_fields if field in group},
        elevation=group["elevation"][()],
        nyquist_velocity=group["nyquist_velocity"][()],
        azimuth=group["azimuth"][()],
        beam_elevation=group["beam_elevation"][()],
    )


# Helpers -------------------------------------------------------------------------------------------


def _bbox(bbox) -> tuple[float, float, float, float]:
    west, south, east, north = (float(value) for value in bbox)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError(f"invalid box {bbox!r}: expected west < east and south < north, in degrees")
    return west, south, east, north


def _time_attrs(origin: datetime) -> dict:
    return {"units": "s", "time_origin": origin.isoformat(), "time_units": "s"}


def _seconds(times: Sequence[datetime], origin: datetime) -> np.ndarray:
    return np.array([(_utc(time) - origin).total_seconds() for time in times], dtype=np.float64)


def _datetime(value: np.datetime64) -> datetime:
    milliseconds = int(np.datetime64(value, "ms").astype(np.int64))
    return datetime.fromtimestamp(milliseconds / 1000.0, tz=timezone.utc)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{value!r} has no time zone")
    return value.astimezone(timezone.utc)


def _text(value) -> str:
    if isinstance(value, np.ndarray):
        value = value.reshape(-1)[0] if value.size else b""
    return value.decode() if isinstance(value, (bytes, np.bytes_)) else str(value)
