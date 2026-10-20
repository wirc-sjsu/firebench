"""
What a model output gives the radar plume family (``radar_plume``), and the helpers an adapter writes
it with.

A model is scored at the radar's own times and places, so its output holds no 3D cube: the adapter
reads its targets from the case (``fire_case_template.plume_targets``: from a model-output template
or an observation file), interpolates its run onto them, and writes, under the entry's ``model_group``
(``/spatial_3d/plume`` by default):

- ``sections/<SITE>/<name>/``: ``time`` (the start of each volume of the section in the entry's
  periods) and ``passive_tracer``, ``wind_u``, ``wind_v``, ``wind_w`` (earth-relative, m/s), each
  ``(n_volume, n_v, n_u)`` on the nodes of the section. ``ColumnSampler`` puts one model output time on
  the nodes: the nearest model column, then linear in height. The adapter interpolates between output
  times and records how.
- ``frame/<SITE>/``: ``time`` (the start of each volume of the site in the periods), ``height_bins``
  (edges, m above mean sea level), and ``plume_cells`` ``(n_time, n_bins)``, the count of model cells
  over the site's frame in each bin of height where the tracer reaches ``tracer_relative_threshold`` of
  its largest value over the frame (``plume_cell_counts``; a model on grids of several resolutions
  weights each cell by its area). Only when the entry lists the site in ``echo_top``.
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

MODEL_GROUP = f"/{fs.SPATIAL_3D}/plume"
TRACER = "passive_tracer"
WIND = ("wind_u", "wind_v", "wind_w")
FIELDS = (TRACER, *WIND)
SECTIONS = "sections"
FRAME = "frame"
POINTS = "points"
HEIGHT_BINS = "height_bins"
PLUME_CELLS = "plume_cells"
THRESHOLD_ATTRIBUTE = "tracer_relative_threshold"
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
    The model's plume cells: ``inside`` the frame and with a tracer at least ``threshold`` of its
    largest value over the frame. Empty when that value is not above 0.
    """
    tracer = np.asarray(tracer, dtype=np.float64)
    inside = np.broadcast_to(np.asarray(inside, dtype=bool), tracer.shape)
    kept = inside & np.isfinite(tracer)
    largest = float(np.max(tracer[kept])) if kept.any() else 0.0
    if largest <= 0:
        return np.zeros(tracer.shape, dtype=bool)
    return kept & (tracer >= threshold * largest)


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
class FrameTarget:
    """The frame of a site the model counts its plume cells over, at the volume times of the site."""

    site: str
    path: str
    time: np.ndarray  # (n_volume,) datetime64[ms] UTC
    time_origin: str
    frame: tuple[float, float, float, float]  # west, south, east, north, degree
    height_bins: np.ndarray  # edges, m above mean sea level
    threshold: float  # tracer_relative_threshold


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


def targets_from_observations(
    obs: h5py.File, entry: dict, periods, height_bin: float, threshold: float
) -> PlumeTargets:
    """
    The targets of an entry of the family on the observation file: every section, at the starts of its
    volumes in ``periods`` (``(start, end)`` pairs), and the frame of each site of ``echo_top``, with
    bins of ``height_bin`` m from 0 to the site's ``max_height``.
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
        frames.append(
            FrameTarget(
                site=site,
                path=frame_path(group, site),
                time=times[_in_periods(times, periods)],
                time_origin=origin,
                frame=tuple(float(attrs[f"frame_{key}"]) for key in ("west", "south", "east", "north")),
                height_bins=np.arange(0.0, top + height_bin, height_bin),
                threshold=float(threshold),
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
                threshold=float(group[PLUME_CELLS].attrs[THRESHOLD_ATTRIBUTE]),
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
    tracer_units: str = "1",
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


def write_plume_frame(
    h5: h5py.File, target: FrameTarget, counts, *, attrs: dict | None = None, compression_lvl: int = 3
) -> None:
    """The model's plume cells over the frame of a site, ``(n_time, n_bins)``, NaN at a time it has none."""
    counts = np.asarray(counts, dtype=np.float64)
    shape = (len(target.time), len(target.height_bins) - 1)
    if counts.shape != shape:
        raise ValueError(f"the counts have the shape {counts.shape}; the frame needs {shape}")
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
            "description": "Cells whose tracer reaches tracer_relative_threshold of its largest value "
            "over the frame",
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
    tracer_units: str = "1",
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
        write_plume_frame(out, target, np.full((len(target.time), len(target.height_bins) - 1), np.nan))
    group.attrs["required_datasets"] = json.dumps(
        {
            SECTIONS: required,
            FRAME: {target.site: ["time", HEIGHT_BINS, PLUME_CELLS] for target in targets.frames},
        }
    )


# ---------------------------
# Reading
# ---------------------------
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

    def nearest(self, time: np.datetime64, max_offset_s: float) -> int | None:
        """The model time nearest ``time``, within ``max_offset_s`` seconds."""
        if len(self.time) == 0:
            return None
        offset = np.abs((self.time - time) / np.timedelta64(1, "s"))
        index = int(np.argmin(offset))
        return index if offset[index] <= max_offset_s else None

    def values(self, index: int) -> dict[str, np.ndarray]:
        """The tracer as given and the wind in m/s at one time."""
        values = {}
        for name in FIELDS:
            dataset = self.group[name]
            data = np.asarray(dataset[index], dtype=np.float64)
            if name != TRACER:
                stored = _text(dataset.attrs.get("units", "m/s"))
                if stored != "m/s":
                    data = ureg.Quantity(data, stored).to("m/s").magnitude
            values[name] = data
        return values


def model_frame(
    model: h5py.File, group: str, site: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """``time``, the bin edges in m, the counts, and the threshold of the model's frame of a site."""
    frame = model[frame_path(group, site)]
    bins = frame[HEIGHT_BINS]
    edges = np.asarray(bins[()], dtype=np.float64)
    stored = _text(bins.attrs.get("units", "m"))
    if stored != "m":
        edges = ureg.Quantity(edges, stored).to("m").magnitude
    counts = np.asarray(frame[PLUME_CELLS][()], dtype=np.float64)
    if counts.ndim != 2 or counts.shape[1] != len(edges) - 1:
        raise ValueError(f"{frame.name}/{PLUME_CELLS} must be (time, {len(edges) - 1} bins)")
    threshold = float(frame[PLUME_CELLS].attrs[THRESHOLD_ATTRIBUTE])
    return _times(frame["time"]), edges, counts, threshold
