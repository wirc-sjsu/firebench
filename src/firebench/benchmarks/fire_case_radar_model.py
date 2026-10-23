"""
What a model output gives the radar plume family (``radar_plume``), and the helpers an adapter writes
it with.

A model is scored at the radar's own times and places, so its output holds no 3D cube: the adapter
reads its targets from the case (``fire_case_template.plume_targets``: from a model-output template
or an observation file), interpolates its run onto them, and writes, under the entry's ``model_group``
(``/spatial_3d/plume`` by default):

- ``sections/<SITE>/<name>/``: ``time`` (the start of each volume of the section in the entry's
  periods) and ``passive_tracer`` (a mass concentration, ``ug/m^3`` or other Pint units of mass per
  volume), ``wind_u``, ``wind_v``, ``wind_w`` (earth-relative, m/s), each ``(n_volume, n_v, n_u)`` on
  the nodes of the section. ``ColumnSampler`` puts one model output time on
  the nodes: the nearest model column, then linear in height. The adapter interpolates between output
  times and records how.
- ``frame/<SITE>/``: only when the entry lists the site in ``echo_top``. The model's plume there is its
  cells over the site's frame that the radar can see (between the lowest and the highest beam over
  their map cell, ``visible_cells``) where the tracer reaches ``tracer_threshold`` (``ug/m^3``, of
  ``[radar_plume]`` in ``fire_case.toml``). It holds ``time`` (the start of each volume of the site in the
  periods), ``height_bins`` (edges, m above mean sea level), ``plume_cells`` ``(n_time, n_bins)``, the
  count of plume cells in each bin of height (``plume_cell_counts``; a model on grids of several
  resolutions weights each cell by its area), and ``plume_top`` ``(n_time, n_lat, n_lon)``, the
  highest plume cell of the columns under each cell of the radar's map grid (``position_lat`` from
  north to south, ``position_lon``; ``column_tops``, ``tops_on_map``), NaN where there is none. The
  template adds ``lowest_beam`` and ``highest_beam`` over each map cell at each time, which the model
  output does not repeat. A time the model cannot give is NaN in ``plume_cells``.
- ``points/`` (optional, never scored): the model's plume cells at some times, for a figure
  (``write_plume_points``).

A value the model cannot give is NaN; a time the adapter could not interpolate is NaN everywhere.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone

import h5py
import hdf5plugin
import numpy as np
from scipy.spatial import cKDTree

from .. import standardize as fs
from ..tools.units import ureg
from .fire_case_parameters import CONCENTRATION_UNITS, concentration_factor

MODEL_GROUP = f"/{fs.SPATIAL_3D}/plume"
TRACER = "passive_tracer"
WIND = ("wind_u", "wind_v", "wind_w")
FIELDS = (TRACER, *WIND)
SECTIONS = "sections"
FRAME = "frame"
POINTS = "points"
HEIGHT_BINS = "height_bins"
PLUME_CELLS = "plume_cells"
PLUME_TOP = "plume_top"
LOWEST_BEAM = "lowest_beam"
HIGHEST_BEAM = "highest_beam"
OLD_TEMPLATE = (
    "The template was made by a FireBench before the radar plume maps of the frames: download the kit "
    "again."
)
OLD_THRESHOLD = (
    "The template was made by a FireBench whose model plume was a share of the tracer's largest value: "
    "download the kit again."
)
# The model's plume over a frame: its tracer at or above this, in CONCENTRATION_UNITS.
THRESHOLD_ATTRIBUTE = "tracer_threshold"
_EARTH_RADIUS = 6_371_000.0
_RADAR = f"/{fs.SPATIAL_3D}/radar"


def _text(value) -> str:
    """An attribute or a dataset item as text."""
    if isinstance(value, np.ndarray):
        value = value.reshape(-1)[0] if value.size else b""
    return value.decode() if isinstance(value, (bytes, np.bytes_)) else str(value)


def _times(dataset) -> np.ndarray:
    """A ``time`` dataset as datetime64[ms] UTC: numbers from ``time_origin`` in ``time_units``, or text."""
    attrs = dataset.attrs
    if "time_origin" in attrs:
        origin = datetime.fromisoformat(_text(attrs["time_origin"]).replace("Z", "+00:00"))
        if origin.tzinfo is None:
            raise ValueError(f"the time origin of {dataset.name} has no UTC offset")
        units = _text(attrs.get("time_units", attrs.get("units", "s")))
        seconds = ureg.Quantity(np.asarray(dataset[()], dtype=np.float64), units).to("s").magnitude
        base = np.datetime64(origin.astimezone(timezone.utc).replace(tzinfo=None), "ms")
        return base + np.round(seconds * 1000).astype("timedelta64[ms]")
    values = []
    for item in dataset[()]:
        moment = datetime.fromisoformat(_text(item).replace("Z", "+00:00"))
        if moment.tzinfo is None:
            raise ValueError(f"a time of {dataset.name} has no UTC offset")
        values.append(np.datetime64(moment.astimezone(timezone.utc).replace(tzinfo=None), "ms"))
    return np.array(values, dtype="datetime64[ms]")


def section_path(group: str, section: str) -> str:
    """Where the model gives a section (``SITE/name``)."""
    site, name = section.split("/", 1)
    return f"{group}/{SECTIONS}/{site}/{name}"


def frame_path(group: str, site: str) -> str:
    """Where the model gives its plume cells over the frame of a site."""
    return f"{group}/{FRAME}/{site}"


def model_requirements(group: str, entry: dict) -> dict[str, list[str]]:
    """The datasets of the model output the section KPIs read, and the attributes each must have."""
    required = {}
    for section in entry["sections"]:
        path = section_path(group, section)
        required[f"{path}/time"] = []
        for name in FIELDS:
            required[f"{path}/{name}"] = ["units"]
    return required


def top_requirements(group: str, entry: dict) -> dict[str, list[str]]:
    """The datasets of the model output the plume top KPIs read, and the attributes each must have."""
    required = {}
    for site in entry.get("echo_top", []):
        path = frame_path(group, site)
        required[f"{path}/time"] = []
        required[f"{path}/{HEIGHT_BINS}"] = ["units"]
        required[f"{path}/{PLUME_CELLS}"] = [THRESHOLD_ATTRIBUTE]
        for name in ("position_lat", "position_lon", PLUME_TOP):
            required[f"{path}/{name}"] = ["units"]
    return required


# ---------------------------
# Sampling a model output time on the nodes of a section
# ---------------------------
class ColumnSampler:
    """
    The nearest column of a model grid to each node of a section, found once for every output time.

    ``latitude`` and ``longitude`` are the columns' (both 2D, or both 1D axes); the nodes are any
    shape. A node farther from its column than the median spacing of the columns is outside the grid.
    """

    def __init__(self, latitude, longitude, node_latitude, node_longitude):
        lat = np.asarray(latitude, dtype=np.float64)
        lon = np.asarray(longitude, dtype=np.float64)
        if lat.ndim == 1 and lon.ndim == 1:
            lon, lat = np.meshgrid(lon, lat)
        if lat.shape != lon.shape or lat.ndim != 2:
            raise ValueError("the latitude and longitude of the columns must be one grid")
        node_latitude = np.asarray(node_latitude, dtype=np.float64)
        node_longitude = np.asarray(node_longitude, dtype=np.float64)
        self.grid_shape = lat.shape
        self.shape = node_latitude.shape
        reference = np.radians(float(np.mean(node_latitude)))

        def plane(lon_, lat_):
            return (
                np.column_stack([np.radians(lon_.ravel()) * np.cos(reference), np.radians(lat_.ravel())])
                * _EARTH_RADIUS
            )

        xy = plane(lon, lat)
        tree = cKDTree(xy)
        distance, self.column = tree.query(plane(node_longitude, node_latitude))
        spacing = (
            float(np.median(tree.query(xy[:: max(1, len(xy) // 2000)], k=2)[0][:, 1]))
            if len(xy) > 1
            else 0.0
        )
        self.inside = distance <= max(spacing, 1.0)

    def sample(self, heights, fields: dict, node_height) -> dict[str, np.ndarray]:
        """
        ``fields`` (name: ``(n_z, n_y, n_x)``) at the nodes, linear in height in each node's column.

        ``heights`` are those of the levels, ``(n_z, n_y, n_x)``, in m above mean sea level, increasing
        upwards. A node outside the grid, below the lowest level, or above the highest is NaN.
        """
        heights = np.asarray(heights, dtype=np.float64)
        if heights.ndim != 3 or heights.shape[1:] != self.grid_shape:
            raise ValueError(f"the heights must be (n_z, {self.grid_shape[0]}, {self.grid_shape[1]})")
        levels = heights.reshape(heights.shape[0], -1)[:, self.column].T  # (nodes, n_z)
        target = np.asarray(node_height, dtype=np.float64).ravel()
        below = (levels <= target[:, None]).sum(axis=1)
        low = np.clip(below - 1, 0, max(levels.shape[1] - 2, 0))
        high = np.minimum(low + 1, levels.shape[1] - 1)
        rows = np.arange(len(target))
        z_low, z_high = levels[rows, low], levels[rows, high]
        with np.errstate(invalid="ignore", divide="ignore"):
            share = np.where(z_high > z_low, np.clip((target - z_low) / (z_high - z_low), 0.0, 1.0), 0.0)
        valid = self.inside.ravel() & (target >= levels[:, 0]) & (target <= levels[:, -1])
        sampled = {}
        for name, values in fields.items():
            values = np.asarray(values, dtype=np.float64)
            if values.shape != heights.shape:
                raise ValueError(f"{name} has the shape {values.shape}; the heights have {heights.shape}")
            column = values.reshape(values.shape[0], -1)[:, self.column].T
            result = (1 - share) * column[rows, low] + share * column[rows, high]
            result[~valid] = np.nan
            sampled[name] = result.reshape(self.shape)
        return sampled


def sample_columns(latitude, longitude, heights, fields: dict, node_latitude, node_longitude, node_height):
    """One model output time on the nodes of a section: see ``ColumnSampler``."""
    return ColumnSampler(latitude, longitude, node_latitude, node_longitude).sample(
        heights, fields, node_height
    )


# ---------------------------
# Plume cells over a frame
# ---------------------------
def plume_cell_mask(tracer, inside, threshold: float) -> np.ndarray:
    """
    The model's plume cells: ``inside`` the frame and with a tracer at least ``threshold``, both in
    the same units (``CONCENTRATION_UNITS`` for a case).
    """
    tracer = np.asarray(tracer, dtype=np.float64)
    inside = np.broadcast_to(np.asarray(inside, dtype=bool), tracer.shape)
    with np.errstate(invalid="ignore"):
        return inside & np.isfinite(tracer) & (tracer >= threshold)


def plume_cell_counts(heights, tracer, inside, bins, threshold: float, weights=None) -> np.ndarray:
    """
    The count of the plume cells (``plume_cell_mask``) in each bin of height (``bins``, edges).

    ``weights``, the shape of ``tracer`` or broadcast to it, counts each cell for that much: a model
    on grids of several resolutions weights a cell by its area, so a nest does not outweigh the grid
    around it. Without them each cell counts 1 and the counts are whole numbers.
    """
    mask = plume_cell_mask(tracer, inside, threshold)
    heights = np.asarray(heights, dtype=np.float64)
    if weights is None:
        counts, _ = np.histogram(heights[mask], bins=np.asarray(bins))
        return counts.astype(np.int64)
    weights = np.broadcast_to(np.asarray(weights, dtype=np.float64), mask.shape)
    counts, _ = np.histogram(heights[mask], bins=np.asarray(bins), weights=weights[mask])
    return counts


def visible_cells(heights, lowest, highest) -> np.ndarray:
    """The cells the radar can see: at or above the lowest beam and at or below the highest over their
    column (``lowest`` and ``highest`` broadcast to ``heights``); none where the band is NaN."""
    heights = np.asarray(heights, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        return (heights >= lowest) & (heights <= highest)


def column_tops(heights, mask, column, n_columns: int) -> np.ndarray:
    """
    The highest cell of ``mask`` in each column: ``heights``, ``mask``, and ``column`` (the index of
    each cell's column) are flat arrays of the same length, so columns of grids with different
    numbers of levels go through one call. NaN for a column with no cell of the mask.
    """
    heights = np.ravel(np.asarray(heights, dtype=np.float64))
    mask = np.ravel(np.asarray(mask, dtype=bool))
    column = np.ravel(np.asarray(column, dtype=np.int64))
    tops = np.full(n_columns, -np.inf)
    np.maximum.at(tops, column[mask], heights[mask])
    tops[~np.isfinite(tops)] = np.nan
    return tops


def _map_cell(latitude, longitude, lat, lon) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The row and column of the map cell under each point, and whether the point is on the map: inside
    its outer edges, which belong to the cells along them, as the radar's gates do."""
    latitude, longitude = np.asarray(latitude, dtype=np.float64), np.asarray(longitude, dtype=np.float64)
    step_lat = abs(latitude[0] - latitude[1]) if len(latitude) > 1 else 1.0
    step_lon = abs(longitude[1] - longitude[0]) if len(longitude) > 1 else 1.0
    north, west = latitude[0] + step_lat / 2, longitude[0] - step_lon / 2
    lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
    tolerance = 1e-9
    on_map = (
        (lat <= north + tolerance)
        & (lat >= north - len(latitude) * step_lat - tolerance)
        & (lon >= west - tolerance)
        & (lon <= west + len(longitude) * step_lon + tolerance)
    )
    row = np.clip(np.floor((north - lat) / step_lat).astype(np.int64), 0, len(latitude) - 1)
    col = np.clip(np.floor((lon - west) / step_lon).astype(np.int64), 0, len(longitude) - 1)
    return np.where(on_map, row, 0), np.where(on_map, col, 0), on_map


def beam_band_at(target: "FrameTarget", index: int, lat, lon) -> tuple[np.ndarray, np.ndarray]:
    """The lowest and highest beam over points at the target's time ``index``, from the map cell under
    each; NaN off the map or where the radar sees nothing."""
    row, col, on_map = _map_cell(target.latitude, target.longitude, lat, lon)
    lowest = np.where(on_map, np.asarray(target.lowest_beam[index], dtype=np.float64)[row, col], np.nan)
    highest = np.where(on_map, np.asarray(target.highest_beam[index], dtype=np.float64)[row, col], np.nan)
    return lowest, highest


def tops_on_map(  # pylint: disable=too-many-arguments
    column_lat, column_lon, column_top, column_size, latitude, longitude
) -> np.ndarray:
    """
    The plume top over each cell of a map (``latitude`` from north to south, ``longitude``, the cell
    centres): a cell holding the centres of model columns takes the highest of their tops; a cell
    holding none takes the top of the nearest column, when that column is less than 0.75 of its size
    (``column_size``, m) away, so a column larger than a cell fills every cell it covers. NaN where
    no column gives a top. Columns of several grids go through one call.
    """
    latitude, longitude = np.asarray(latitude, dtype=np.float64), np.asarray(longitude, dtype=np.float64)
    column_lat = np.ravel(np.asarray(column_lat, dtype=np.float64))
    column_lon = np.ravel(np.asarray(column_lon, dtype=np.float64))
    column_top = np.ravel(np.asarray(column_top, dtype=np.float64))
    column_size = np.broadcast_to(np.asarray(column_size, dtype=np.float64), column_top.shape).ravel()
    n_lat, n_lon = len(latitude), len(longitude)
    tops = np.full(n_lat * n_lon, -np.inf)
    row, col, on_map = _map_cell(latitude, longitude, column_lat, column_lon)
    flat = row * n_lon + col
    held = np.zeros(n_lat * n_lon, dtype=bool)
    held[flat[on_map]] = True
    given = on_map & np.isfinite(column_top)
    np.maximum.at(tops, flat[given], column_top[given])
    tops[held & ~np.isfinite(tops)] = np.nan
    empty = np.flatnonzero(~held)
    if empty.size and column_top.size:
        reference = np.radians(float(np.mean(latitude)))

        def plane(lon_, lat_):
            return np.column_stack([np.radians(lon_) * np.cos(reference), np.radians(lat_)]) * _EARTH_RADIUS

        grid_lon, grid_lat = np.meshgrid(longitude, latitude)
        distance, nearest = cKDTree(plane(column_lon, column_lat)).query(
            plane(grid_lon.ravel()[empty], grid_lat.ravel()[empty])
        )
        near = distance <= 0.75 * column_size[nearest]
        tops[empty[near]] = column_top[nearest[near]]
    tops[~np.isfinite(tops)] = np.nan
    return tops.reshape(n_lat, n_lon)


def histogram_quantile(edges, counts, level: float) -> float:
    """The ``level`` quantile of values counted in bins, linear inside its bin; NaN when none is counted."""
    counts = np.asarray(counts, dtype=np.float64)
    edges = np.asarray(edges, dtype=np.float64)
    total = float(counts.sum())
    if not np.isfinite(total) or total <= 0:
        return float("nan")
    wanted = level * total
    cumulative = np.cumsum(counts)
    index = int(np.searchsorted(cumulative, wanted, side="left"))
    index = min(index, len(counts) - 1)
    before = cumulative[index] - counts[index]
    share = (wanted - before) / counts[index] if counts[index] > 0 else 0.0
    return float(edges[index] + share * (edges[index + 1] - edges[index]))


# ---------------------------
# Targets
# ---------------------------
@dataclass(frozen=True)
class SectionTarget:  # pylint: disable=too-many-instance-attributes
    """A section the model is sampled on, and the volume times it is scored at."""

    section: str  # SITE/name
    path: str  # the group of the model output
    time: np.ndarray  # (n_volume,) datetime64[ms] UTC, volume start
    time_origin: str
    latitude: np.ndarray  # (n_v, n_u) degree
    longitude: np.ndarray
    height: np.ndarray  # (n_v, n_u) m above mean sea level


@dataclass(frozen=True)
class FrameTarget:  # pylint: disable=too-many-instance-attributes
    """The frame of a site the model counts its plume cells over, at the volume times of the site, the
    radar's map grid over it, and what the radar can see over each map cell at each time."""

    site: str
    path: str
    time: np.ndarray  # (n_volume,) datetime64[ms] UTC
    time_origin: str
    frame: tuple[float, float, float, float]  # west, south, east, north, degree
    height_bins: np.ndarray  # edges, m above mean sea level
    threshold: float  # tracer_threshold, CONCENTRATION_UNITS
    latitude: np.ndarray  # (n_lat,) degree, cell centres from north to south
    longitude: np.ndarray  # (n_lon,) degree, cell centres from west to east
    lowest_beam: np.ndarray  # (n_volume, n_lat, n_lon) m above mean sea level, NaN where unseen
    highest_beam: np.ndarray


@dataclass(frozen=True)
class PlumeTargets:
    """Everything an adapter writes for the radar plume family of a case."""

    model_group: str
    sections: list[SectionTarget]
    frames: list[FrameTarget]

    @property
    def times(self) -> np.ndarray:
        """Every target time, sorted, once."""
        parts = [target.time for target in (*self.sections, *self.frames)]
        return np.unique(np.concatenate(parts)) if parts else np.array([], dtype="datetime64[ms]")


def _in_periods(times: np.ndarray, periods) -> np.ndarray:
    keep = np.zeros(len(times), dtype=bool)
    for start, end in periods:
        low, high = (
            np.datetime64(moment.astimezone(timezone.utc).replace(tzinfo=None), "ms")
            for moment in (start, end)
        )
        keep |= (times >= low) & (times <= high)
    return keep


def _site_times(obs: h5py.File, site: str) -> tuple[np.ndarray, str]:
    dataset = obs[f"{_RADAR}/{site}/volumes/time"]
    return _times(dataset), _text(dataset.attrs["time_origin"])


def targets_from_observations(  # pylint: disable=too-many-arguments
    obs: h5py.File, entry: dict, periods, height_bin: float, threshold: float, map_resolution: float = 0.01
) -> PlumeTargets:
    """
    The targets of an entry of the family on the observation file: every section, at the starts of its
    volumes in ``periods`` (``(start, end)`` pairs), and the frame of each site of ``echo_top``, with
    bins of ``height_bin`` m from 0 to the site's ``max_height``, its map grid of ``map_resolution``
    degree, and the radar's beam band over each map cell at each of those volumes.
    """
    group = entry["model_group"]
    sections = []
    for section in entry["sections"]:
        site, name = section.split("/", 1)
        cut = fs.read_radar_section(obs, site, name)
        _, origin = _site_times(obs, site)
        keep = _in_periods(cut.time, periods)
        sections.append(
            SectionTarget(
                section=section,
                path=section_path(group, section),
                time=cut.time[keep],
                time_origin=origin,
                latitude=cut.plane.latitude,
                longitude=cut.plane.longitude,
                height=cut.plane.height,
            )
        )
    frames = []
    for site in entry.get("echo_top", []):
        attrs = obs[f"{_RADAR}/{site}"].attrs
        times, origin = _site_times(obs, site)
        top = float(attrs["max_height"])
        volumes = np.flatnonzero(_in_periods(times, periods))
        latitude, longitude = fs.radar_map_axes(obs, site, resolution=map_resolution)
        lowest, highest = fs.radar_beam_bands(obs, site, resolution=map_resolution, volumes=volumes)
        frames.append(
            FrameTarget(
                site=site,
                path=frame_path(group, site),
                time=times[volumes],
                time_origin=origin,
                frame=tuple(float(attrs[f"frame_{key}"]) for key in ("west", "south", "east", "north")),
                height_bins=np.arange(0.0, top + height_bin, height_bin),
                threshold=float(threshold),
                latitude=latitude,
                longitude=longitude,
                lowest_beam=lowest,
                highest_beam=highest,
            )
        )
    return PlumeTargets(model_group=group, sections=sections, frames=frames)


def targets_from_template(template: h5py.File, model_group: str) -> PlumeTargets:
    """The targets a model-output template holds (``write_target_groups``)."""
    sections, frames = [], []
    base = template.get(f"{model_group}/{SECTIONS}")
    for site, site_group in (base.items() if isinstance(base, h5py.Group) else []):
        for name, group in site_group.items():
            sections.append(
                SectionTarget(
                    section=f"{site}/{name}",
                    path=group.name,
                    time=_times(group["time"]),
                    time_origin=_text(group["time"].attrs["time_origin"]),
                    latitude=group["position_lat"][()],
                    longitude=group["position_lon"][()],
                    height=group["position_alt"][()],
                )
            )
    base = template.get(f"{model_group}/{FRAME}")
    for site, group in (base.items() if isinstance(base, h5py.Group) else []):
        if LOWEST_BEAM not in group:
            raise ValueError(OLD_TEMPLATE)
        if THRESHOLD_ATTRIBUTE not in group[PLUME_CELLS].attrs:
            raise ValueError(OLD_THRESHOLD)
        frames.append(
            FrameTarget(
                site=site,
                path=group.name,
                time=_times(group["time"]),
                time_origin=_text(group["time"].attrs["time_origin"]),
                frame=tuple(
                    float(group.attrs[f"frame_{key}"]) for key in ("west", "south", "east", "north")
                ),
                height_bins=group[HEIGHT_BINS][()],
                threshold=_threshold(group[PLUME_CELLS]),
                latitude=group["position_lat"][()],
                longitude=group["position_lon"][()],
                lowest_beam=group[LOWEST_BEAM][()],
                highest_beam=group[HIGHEST_BEAM][()],
            )
        )
    return PlumeTargets(model_group=model_group, sections=sections, frames=frames)


# ---------------------------
# Writing
# ---------------------------
def _seconds(times: np.ndarray, origin: str) -> np.ndarray:
    start = datetime.fromisoformat(origin.replace("Z", "+00:00")).astimezone(timezone.utc)
    return (np.asarray(times, dtype="datetime64[ms]") - np.datetime64(start.replace(tzinfo=None), "ms")) / (
        np.timedelta64(1, "s")
    )


def _time(group: h5py.Group, times: np.ndarray, origin: str) -> None:
    dataset = group.create_dataset("time", data=_seconds(times, origin).astype(np.float64))
    dataset.attrs.update({"units": "s", "time_units": "s", "time_origin": origin})


def _create(group: h5py.Group, name: str, data, attrs: dict, compression_lvl: int) -> h5py.Dataset:
    data = np.asarray(data)
    options = hdf5plugin.Zstd(clevel=compression_lvl) if data.ndim and data.size > 1 else {}
    dataset = group.create_dataset(name, data=data, **options)
    for key, value in attrs.items():
        dataset.attrs[key] = value
    return dataset


def _fresh_group(h5: h5py.File, path: str) -> h5py.Group:
    if path in h5:
        del h5[path]
    return h5.require_group(path)


def write_plume_section(
    h5: h5py.File,
    target: SectionTarget,
    fields: dict,
    *,
    tracer_units: str = CONCENTRATION_UNITS,
    attrs: dict | None = None,
    compression_lvl: int = 3,
) -> None:
    """
    The model on the nodes of a section, at the target's times: ``fields`` names ``passive_tracer``,
    ``wind_u``, ``wind_v``, ``wind_w`` (earth-relative, m/s), each ``(n_time, n_v, n_u)``.
    ``attrs`` go on the group (how the adapter interpolated, for example).
    """
    shape = (len(target.time), *target.latitude.shape)
    group = _fresh_group(h5, target.path)
    group.attrs["description"] = (
        f"The model on the nodes of the radar cross section {target.section}, at the start of its volumes"
    )
    for key, value in (attrs or {}).items():
        group.attrs[key] = value
    _time(group, target.time, target.time_origin)
    for name, data, units in (
        ("position_lat", target.latitude, "degree"),
        ("position_lon", target.longitude, "degree"),
        ("position_alt", target.height, "m"),
    ):
        _create(group, name, data, {"units": units}, compression_lvl)
    for name in FIELDS:
        values = np.asarray(fields[name], dtype=np.float32)
        if values.shape != shape:
            raise ValueError(f"{name} has the shape {values.shape}; the section needs {shape}")
        _create(
            group,
            name,
            values,
            {"units": tracer_units if name == TRACER else "m/s"},
            compression_lvl,
        )


def write_plume_frame(  # pylint: disable=too-many-arguments
    h5: h5py.File,
    target: FrameTarget,
    counts,
    tops,
    *,
    beams: bool = False,
    attrs: dict | None = None,
    compression_lvl: int = 3,
) -> None:
    """
    The model's plume over the frame of a site: its cells by height, ``(n_time, n_bins)``, NaN at a
    time it has none, and its plume top on the radar's map grid, ``(n_time, n_lat, n_lon)``, NaN where
    it has none. ``beams`` also writes the radar's beam band over the map, as a template does.
    """
    counts = np.asarray(counts, dtype=np.float64)
    shape = (len(target.time), len(target.height_bins) - 1)
    if counts.shape != shape:
        raise ValueError(f"the counts have the shape {counts.shape}; the frame needs {shape}")
    tops = np.asarray(tops, dtype=np.float32)
    map_shape = (len(target.time), len(target.latitude), len(target.longitude))
    if tops.shape != map_shape:
        raise ValueError(f"the plume tops have the shape {tops.shape}; the map needs {map_shape}")
    group = _fresh_group(h5, target.path)
    group.attrs["description"] = (
        f"The count of the model's plume cells over the frame of {target.site} in each bin of height, "
        "at the start of its volumes"
    )
    for key, value in zip(("west", "south", "east", "north"), target.frame):
        group.attrs[f"frame_{key}"] = float(value)
        group.attrs[f"frame_{key}_units"] = "degree"
    for key, value in (attrs or {}).items():
        group.attrs[key] = value
    _time(group, target.time, target.time_origin)
    _create(
        group,
        HEIGHT_BINS,
        np.asarray(target.height_bins, dtype=np.float64),
        {"units": "m", "description": "Edges, above mean sea level"},
        compression_lvl,
    )
    _create(
        group,
        PLUME_CELLS,
        counts,
        {
            "units": "1",
            THRESHOLD_ATTRIBUTE: float(target.threshold),
            f"{THRESHOLD_ATTRIBUTE}_units": CONCENTRATION_UNITS,
            "description": "Cells the radar can see whose tracer reaches tracer_threshold",
        },
        compression_lvl,
    )
    _create(
        group,
        "position_lat",
        np.asarray(target.latitude, dtype=np.float64),
        {"units": "degree"},
        compression_lvl,
    )
    _create(
        group,
        "position_lon",
        np.asarray(target.longitude, dtype=np.float64),
        {"units": "degree"},
        compression_lvl,
    )
    _create(
        group,
        PLUME_TOP,
        tops,
        {
            "units": "m",
            "description": "Highest plume cell of the columns under each map cell, above mean sea level",
        },
        compression_lvl,
    )
    if beams:
        for name, values in ((LOWEST_BEAM, target.lowest_beam), (HIGHEST_BEAM, target.highest_beam)):
            _create(
                group,
                name,
                np.asarray(values, dtype=np.float32),
                {
                    "units": "m",
                    "description": "Beam-centre height over each map cell, above mean sea level",
                },
                compression_lvl,
            )


def write_plume_points(  # pylint: disable=too-many-arguments
    h5: h5py.File,
    group_path: str,
    times: np.ndarray,
    time_origin: str,
    clouds: list[dict],
    *,
    tracer_units: str = CONCENTRATION_UNITS,
    compression_lvl: int = 3,
) -> None:
    """
    The model's plume cells at some times, for a figure: ``clouds`` holds one dict per time with
    ``position_lon``, ``position_lat``, ``position_z`` (m above mean sea level), and ``passive_tracer``.
    No KPI reads them.
    """
    if len(clouds) != len(times):
        raise ValueError("one cloud of points per time")
    group = _fresh_group(h5, f"{group_path}/{POINTS}")
    group.attrs["description"] = "The model's plume cells at some times, for figures; never scored"
    _time(group, times, time_origin)
    counts = np.array([len(cloud[TRACER]) for cloud in clouds], dtype=np.int64)
    _create(
        group, "offset", np.concatenate([[0], np.cumsum(counts)[:-1]]).astype(np.int64), {}, compression_lvl
    )
    _create(group, "count", counts, {}, compression_lvl)
    for name, units in (
        ("position_lon", "degree"),
        ("position_lat", "degree"),
        ("position_z", "m"),
        (TRACER, tracer_units),
    ):
        values = (
            np.concatenate([np.asarray(cloud[name], dtype=np.float32) for cloud in clouds])
            if clouds
            else np.array([], dtype=np.float32)
        )
        _create(group, name, values, {"units": units}, compression_lvl)


def write_target_groups(out: h5py.File, targets: PlumeTargets, description: str) -> None:
    """The groups of a model-output template: each target with its times and positions, NaN values."""
    group = out.require_group(targets.model_group)
    group.attrs["description"] = description
    required = {}
    for target in targets.sections:
        shape = (len(target.time), *target.latitude.shape)
        write_plume_section(
            out, target, {name: np.full(shape, np.nan, dtype=np.float32) for name in FIELDS}
        )
        required[target.section] = sorted(("time", *FIELDS))
    for target in targets.frames:
        write_plume_frame(
            out,
            target,
            np.full((len(target.time), len(target.height_bins) - 1), np.nan),
            np.full((len(target.time), len(target.latitude), len(target.longitude)), np.nan),
            beams=True,
        )
    group.attrs["required_datasets"] = json.dumps(
        {
            SECTIONS: required,
            FRAME: {
                target.site: ["time", HEIGHT_BINS, PLUME_CELLS, "position_lat", "position_lon", PLUME_TOP]
                for target in targets.frames
            },
        }
    )


# ---------------------------
# Reading
# ---------------------------
def _threshold(dataset) -> float:
    """The tracer threshold a frame's ``plume_cells`` were counted at, in ``CONCENTRATION_UNITS``."""
    value = float(dataset.attrs[THRESHOLD_ATTRIBUTE])
    units = _text(dataset.attrs.get(f"{THRESHOLD_ATTRIBUTE}_units", CONCENTRATION_UNITS))
    return value * concentration_factor(units)


class ModelSection:
    """The model's values on a section, as ``write_plume_section`` wrote them."""

    def __init__(self, model: h5py.File, group: str, section: str, shape: tuple[int, int]):
        path = section_path(group, section)
        self.group = model[path]
        self.time = _times(self.group["time"])
        for name in FIELDS:
            expected = (len(self.time), *shape)
            if self.group[name].shape != expected:
                raise ValueError(f"{path}/{name} has the shape {self.group[name].shape}, not {expected}")
        # Why the tracer cannot be compared with a threshold, or None; it is then kept as given.
        self.tracer_problem: str | None = None
        self._tracer_factor = 1.0
        units = _text(self.group[TRACER].attrs.get("units", ""))
        try:
            self._tracer_factor = concentration_factor(units)
        except ValueError as error:
            self.tracer_problem = f"the model's tracer: {error}"

    def nearest(self, time: np.datetime64, max_offset_s: float) -> int | None:
        """The model time nearest ``time``, within ``max_offset_s`` seconds."""
        if len(self.time) == 0:
            return None
        offset = np.abs((self.time - time) / np.timedelta64(1, "s"))
        index = int(np.argmin(offset))
        return index if offset[index] <= max_offset_s else None

    def values(self, index: int) -> dict[str, np.ndarray]:
        """The tracer in ``CONCENTRATION_UNITS`` (as given when it is no concentration) and the wind in
        m/s at one time."""
        values = {}
        for name in FIELDS:
            dataset = self.group[name]
            data = np.asarray(dataset[index], dtype=np.float64)
            if name == TRACER:
                data = data * self._tracer_factor
            else:
                stored = _text(dataset.attrs.get("units", "m/s"))
                if stored != "m/s":
                    data = ureg.Quantity(data, stored).to("m/s").magnitude
            values[name] = data
        return values


def model_frame(
    model: h5py.File, group: str, site: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float | None]:
    """
    ``time``, the bin edges in m, the counts, and the threshold of the model's frame of a site, in
    ``CONCENTRATION_UNITS``; None when the frame was counted at a share of the tracer's largest value.
    """
    frame = model[frame_path(group, site)]
    bins = frame[HEIGHT_BINS]
    edges = np.asarray(bins[()], dtype=np.float64)
    stored = _text(bins.attrs.get("units", "m"))
    if stored != "m":
        edges = ureg.Quantity(edges, stored).to("m").magnitude
    counts = np.asarray(frame[PLUME_CELLS][()], dtype=np.float64)
    if counts.ndim != 2 or counts.shape[1] != len(edges) - 1:
        raise ValueError(f"{frame.name}/{PLUME_CELLS} must be (time, {len(edges) - 1} bins)")
    attrs = frame[PLUME_CELLS].attrs
    threshold = _threshold(frame[PLUME_CELLS]) if THRESHOLD_ATTRIBUTE in attrs else None
    return _times(frame["time"]), edges, counts, threshold


def model_top_maps(
    model: h5py.File, group: str, site: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """``time``, the map axes (latitude, longitude), and the plume tops (m) of a site in the model."""
    frame = model[frame_path(group, site)]
    tops = frame[PLUME_TOP]
    values = np.asarray(tops[()], dtype=np.float64)
    stored = _text(tops.attrs.get("units", "m"))
    if stored != "m":
        values = ureg.Quantity(values, stored).to("m").magnitude
    latitude = np.asarray(frame["position_lat"][()], dtype=np.float64)
    longitude = np.asarray(frame["position_lon"][()], dtype=np.float64)
    if values.ndim != 3 or values.shape[1:] != (len(latitude), len(longitude)):
        raise ValueError(f"{frame.name}/{PLUME_TOP} must be (time, {len(latitude)}, {len(longitude)})")
    return _times(frame["time"]), latitude, longitude, values
