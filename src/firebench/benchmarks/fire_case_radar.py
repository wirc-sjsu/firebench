"""
The radar plume family of the generic cases (``radar_plume``): a model's plume against the radar's
cross sections.

The observations are the sections a standard file holds (``radar_cross_section``,
``/spatial_3d/radar/<SITE>/sections/<name>``). The model output gives a passive tracer and the wind
in 3D, ``/spatial_3d/plume`` by default. For each volume of a period, the model output time nearest
the volume's start is sampled on the nodes of the section: the nearest model column, then linear in
height. Both sides are then on one grid, and compared as masks and ranks, never as amounts, since
nothing relates a tracer to a reflectivity:

- the observed plume is the radar plume mask (``resources/radar.toml``); the model's, where its
  tracer reaches ``tracer_relative_threshold`` of its largest value on the section at that time;
- the plume top is the 90th percentile of the heights of a plume's cells, its centroid the mean of
  their position on the section weighted by linear reflectivity or by the tracer;
- the model's radial velocity is its wind along the beam through each node, folded into the Nyquist
  interval of the sweep the observation was read on, so the aliased observation needs no dealiasing.

Every number is in ``fire_case.toml`` (``[radar_plume]``) or ``radar.toml``. A KPI no volume of its
period can give is not computed: its function returns None and it is left out of its group.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
from h5py import File
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

from .. import metrics as fm
from .. import standardize as fs
from .. import tools as ft
from ..tools.units import ureg
from .fire_case_parameters import RadarPlumeParameters

MODEL_GROUP = f"/{fs.SPATIAL_3D}/plume"
TRACER = "passive_tracer"
WIND = ("wind_u", "wind_v", "wind_w")
REFLECTIVITY = "radar_reflectivity"
CORRELATION = "radar_correlation_coefficient"
VELOCITY = "radar_radial_velocity"
_EARTH_RADIUS = 6_371_000.0


def model_requirements(group: str) -> dict[str, list[str]]:
    """The datasets of the model output the family reads, and the attributes each must have."""
    required = {f"{group}/time": []}
    for name in ("position_lat", "position_lon", "position_z", TRACER, *WIND):
        required[f"{group}/{name}"] = ["units"]
    return required


@dataclass
class PlumePairs:  # pylint: disable=too-many-instance-attributes
    """Both sides of one section, on its nodes, for the volumes of a period the model has a time for."""

    section: str
    times: list[np.datetime64]
    u: np.ndarray  # (n_v, n_u) m along the section
    v: np.ndarray  # (n_v, n_u) m across
    height: np.ndarray  # (n_v, n_u) m above mean sea level
    reflectivity: list[np.ndarray]
    observed: list[np.ndarray]  # observed plume mask
    tracer: list[np.ndarray]
    modelled: list[np.ndarray]  # model plume mask
    # Folded differences of radial velocity, model minus observation, on the observed plume; None when
    # the radar kept no velocity.
    velocity_differences: list[np.ndarray] | None


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


def _text(value) -> str:
    """An attribute or a dataset item as text."""
    if isinstance(value, np.ndarray):
        value = value.reshape(-1)[0] if value.size else b""
    return value.decode() if isinstance(value, (bytes, np.bytes_)) else str(value)


class _ModelPlume:
    """The model's tracer and wind, sampled on the nodes of a section."""

    def __init__(self, model: File, group: str, latitude: np.ndarray, longitude: np.ndarray):
        self.group = model[group]
        self.time = _times(self.group["time"])
        lat = self._quantity("position_lat", "degree")
        lon = self._quantity("position_lon", "degree")
        if lat.ndim == 1 and lon.ndim == 1:
            lon, lat = np.meshgrid(lon, lat)
        if lat.shape != lon.shape or lat.ndim != 2:
            raise ValueError(f"{group}: position_lat and position_lon must be the grid of the columns")
        self.columns = lat.size
        reference = np.radians(float(np.mean(latitude)))
        xy = (
            np.column_stack([np.radians(lon.ravel()) * np.cos(reference), np.radians(lat.ravel())])
            * _EARTH_RADIUS
        )
        tree = cKDTree(xy)
        nodes = (
            np.column_stack(
                [np.radians(longitude.ravel()) * np.cos(reference), np.radians(latitude.ravel())]
            )
            * _EARTH_RADIUS
        )
        distance, self.column = tree.query(nodes)
        # A node farther from its column than the spacing of the columns is outside the model's grid.
        spacing = float(np.median(tree.query(xy[:: max(1, len(xy) // 2000)], k=2)[0][:, 1]))
        self.inside = distance <= max(spacing, 1.0)
        self.shape = latitude.shape

    def _quantity(self, name: str, units: str) -> np.ndarray:
        dataset = self.group[name]
        values = np.asarray(dataset[()], dtype=np.float64)
        stored = _text(dataset.attrs.get("units", units))
        return values if stored == units else ureg.Quantity(values, stored).to(units).magnitude

    def nearest(self, time: np.datetime64, max_offset_s: float) -> int | None:
        """The model time nearest ``time``, within ``max_offset_s`` seconds."""
        offset = np.abs((self.time - time) / np.timedelta64(1, "s"))
        index = int(np.argmin(offset))
        return index if offset[index] <= max_offset_s else None

    def sample(self, index: int, height: np.ndarray) -> dict[str, np.ndarray]:
        """The tracer and the wind at the nodes, linear in height in each node's column; NaN outside."""
        z = self.group["position_z"]
        heights = np.asarray(z[index] if z.ndim == 4 else z[()], dtype=np.float64)
        stored = _text(z.attrs.get("units", "m"))
        if stored != "m":
            heights = ureg.Quantity(heights, stored).to("m").magnitude
        levels = heights.reshape(heights.shape[0], -1)[:, self.column].T  # (nodes, n_z)
        target = height.ravel()
        below = (levels <= target[:, None]).sum(axis=1)
        low = np.clip(below - 1, 0, levels.shape[1] - 2)
        rows = np.arange(len(target))
        z_low, z_high = levels[rows, low], levels[rows, low + 1]
        with np.errstate(invalid="ignore", divide="ignore"):
            share = np.clip((target - z_low) / (z_high - z_low), 0.0, 1.0)
        valid = self.inside & (target >= levels[:, 0]) & (target <= levels[:, -1])
        sampled = {}
        for name, units in ((TRACER, None), *((wind, "m/s") for wind in WIND)):
            dataset = self.group[name]
            values = np.asarray(dataset[index], dtype=np.float64)
            stored = _text(dataset.attrs.get("units", ""))
            if units is not None and stored != units:
                values = ureg.Quantity(values, stored).to(units).magnitude
            column = values.reshape(values.shape[0], -1)[:, self.column].T
            result = (1 - share) * column[rows, low] + share * column[rows, low + 1]
            result[~valid] = np.nan
            sampled[name] = result.reshape(self.shape)
        return sampled


def fold(difference: np.ndarray, nyquist: np.ndarray) -> np.ndarray:
    """A velocity difference folded into the Nyquist interval: ``((d + vN) mod 2vN) - vN``."""
    return np.mod(difference + nyquist, 2 * nyquist) - nyquist


def plume_pairs(  # pylint: disable=too-many-locals
    model: File,
    obs: File,
    section: str,
    period: tuple[datetime, datetime],
    model_group: str,
    parameters: RadarPlumeParameters,
) -> PlumePairs:
    """Both sides of ``section`` (``SITE/name``) for the volumes of ``period``, on the section's nodes."""
    site, name = section.split("/", 1)
    cut = fs.read_radar_section(obs, site, name)
    mask = fs.radar_parameters()
    plane = cut.plane
    sampler = _ModelPlume(model, model_group, plane.latitude, plane.longitude)
    start, end = (
        np.datetime64(moment.astimezone(timezone.utc).replace(tzinfo=None), "ms") for moment in period
    )
    azimuth = np.radians(cut.azimuth.astype(np.float64))
    pairs = PlumePairs(
        section=section,
        times=[],
        u=np.broadcast_to(plane.u[None, :], plane.height.shape),
        v=np.broadcast_to(plane.v[:, None], plane.height.shape),
        height=plane.height,
        reflectivity=[],
        observed=[],
        tracer=[],
        modelled=[],
        velocity_differences=[] if VELOCITY in cut.values else None,
    )
    for volume, time in enumerate(cut.time):
        if not start <= time <= end:
            continue
        index = sampler.nearest(time, parameters.max_time_offset)
        if index is None:
            ft.logger.warning(
                "Radar plume %s: no model output within %s s of %s.",
                section,
                parameters.max_time_offset,
                time,
            )
            continue
        sampled = sampler.sample(index, plane.height)
        reflectivity = cut.values[REFLECTIVITY][volume].astype(np.float64)
        tracer = sampled[TRACER]
        scored = np.isfinite(reflectivity) & np.isfinite(tracer)
        low, high = mask.rhohv_range
        with np.errstate(invalid="ignore"):
            observed = scored & (reflectivity >= mask.min_dbz)
            if CORRELATION in cut.values:
                correlation = cut.values[CORRELATION][volume]
                observed &= (correlation > low) & (correlation < high)
            largest = float(np.max(tracer[scored])) if scored.any() else 0.0
            modelled = (
                scored & (tracer >= parameters.tracer_relative_threshold * largest)
                if largest > 0
                else scored & False
            )
        pairs.times.append(time)
        pairs.reflectivity.append(np.where(scored, reflectivity, np.nan))
        pairs.tracer.append(np.where(scored, tracer, np.nan))
        pairs.observed.append(observed)
        pairs.modelled.append(modelled)
        if pairs.velocity_differences is not None:
            elevation = np.radians(cut.elevation[volume].astype(np.float64))
            wind_u, wind_v, wind_w = (sampled[name] for name in WIND)
            radial = (wind_u * np.sin(azimuth) + wind_v * np.cos(azimuth)) * np.cos(elevation) + (
                wind_w - parameters.fall_speed
            ) * np.sin(elevation)
            nyquist = cut.nyquist_velocity[volume].astype(np.float64)
            observed_velocity = cut.values[VELOCITY][volume].astype(np.float64)
            with np.errstate(invalid="ignore"):
                kept = observed & np.isfinite(observed_velocity) & np.isfinite(radial) & (nyquist > 0)
            pairs.velocity_differences.append(fold(radial[kept] - observed_velocity[kept], nyquist[kept]))
    return pairs


def _pairs(
    model: File, obs: File, ctx: dict, section: str, period_name: str, period, model_group, parameters
):
    """The pairs of a section and a period, computed once for every KPI of their group."""
    cache = ctx.setdefault("radar_plume", {})
    key = (section, period_name)
    if key not in cache:
        cache[key] = plume_pairs(model, obs, section, period, model_group, parameters)
    return cache[key]


def _skipped(kpi_name: str, reason: str) -> None:
    """Say why a KPI is not computed; its function then returns None."""
    ft.logger.warning("Ignoring radar plume KPI %s: %s.", kpi_name, reason)


def _p90(height: np.ndarray, mask: np.ndarray) -> float:
    return float(np.quantile(height[mask], 0.9))


def _centroid(pairs: PlumePairs, mask: np.ndarray, weights: np.ndarray) -> np.ndarray:
    weight = weights[mask]
    return np.array([np.sum(weight * pairs.u[mask]), np.sum(weight * pairs.v[mask])]) / np.sum(weight)


def bench_radar_plume(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-return-statements
    model_dataset: File,
    obs_dataset: File,
    ctx: dict,
    kpi_name_custom: str,
    kpi: str,
    section: str,
    period_name: str,
    period: tuple[datetime, datetime],
    model_group: str,
    parameters: RadarPlumeParameters,
):
    """One KPI of the radar plume family on one section and period, scored from 0 to 100."""
    pairs = _pairs(model_dataset, obs_dataset, ctx, section, period_name, period, model_group, parameters)
    label = f"{kpi_name_custom} {section} {period_name}"
    if not pairs.times:
        return _skipped(label, "no volume of the period has a model output time near it")
    values = []
    if kpi == "mask_iou":
        for observed, modelled in zip(pairs.observed, pairs.modelled):
            union = int((observed | modelled).sum())
            if union:
                values.append((observed & modelled).sum() / union)
        if not values:
            return _skipped(label, "neither side has a plume in any volume")
        value = float(np.mean(values))
        score = fm.kpi_norm_bounded_linear(value, 0, 1)
    elif kpi in ("top_error", "centroid_error"):
        for reflectivity, tracer, observed, modelled in zip(
            pairs.reflectivity, pairs.tracer, pairs.observed, pairs.modelled
        ):
            if not observed.any() or not modelled.any():
                continue
            if kpi == "top_error":
                values.append(abs(_p90(pairs.height, observed) - _p90(pairs.height, modelled)))
            else:
                linear = 10.0 ** (np.nan_to_num(reflectivity) / 10.0)
                distance = _centroid(pairs, observed, linear) - _centroid(
                    pairs, modelled, np.nan_to_num(tracer)
                )
                values.append(float(np.hypot(*distance)))
        if not values:
            return _skipped(label, "no volume has a plume on both sides")
        value = float(np.mean(values))
        scale = (
            parameters.top_error_at_score_50
            if kpi == "top_error"
            else parameters.centroid_error_at_score_50
        )
        score = fm.kpi_norm_half_open_exponential(value, 0, scale)
    elif kpi == "rank_correlation":
        for reflectivity, tracer, observed, modelled in zip(
            pairs.reflectivity, pairs.tracer, pairs.observed, pairs.modelled
        ):
            with np.errstate(invalid="ignore"):
                cells = (observed | modelled) & (tracer > 0)
            if cells.sum() < parameters.min_cells:
                continue
            rho = spearmanr(reflectivity[cells], np.log10(tracer[cells])).statistic
            if np.isfinite(rho):
                values.append(float(rho))
        if not values:
            return _skipped(
                label, f"no volume has {parameters.min_cells} plume cells with a tracer above 0"
            )
        value = float(np.mean(values))
        score = fm.kpi_norm_bounded_linear(max(value, 0.0), 0, 1)
    elif kpi in ("velocity_rmse", "velocity_bias"):
        if pairs.velocity_differences is None:
            return _skipped(label, "the radar kept no radial velocity")
        differences = (
            np.concatenate(pairs.velocity_differences) if pairs.velocity_differences else np.array([])
        )
        if differences.size == 0:
            return _skipped(label, "no cell of the observed plume has a radial velocity and a model wind")
        if kpi == "velocity_rmse":
            value = float(np.sqrt(np.mean(differences**2)))
            score = fm.kpi_norm_half_open_exponential(value, 0, parameters.velocity_rmse_at_score_50)
        else:
            value = float(np.mean(differences))
            score = fm.kpi_norm_symmetric_open_exponential(value, parameters.velocity_bias_at_score_50)
    else:
        raise ValueError(f"unknown radar plume KPI {kpi!r}")
    ft.logger.info("%s: %f", label, value)
    return {label: value, "Score": score}


# The KPIs of the family: name, the key of `bench_radar_plume`, and the key of its weight.
RADAR_KPIS = (
    ("Plume Mask IoU", "mask_iou", "mask_iou_weight"),
    ("Plume Top Error", "top_error", "top_error_weight"),
    ("Plume Centroid Error", "centroid_error", "centroid_error_weight"),
    ("Concentration Rank Correlation", "rank_correlation", "rank_correlation_weight"),
    ("Radial Velocity RMSE", "velocity_rmse", "velocity_rmse_weight"),
    ("Radial Velocity Bias", "velocity_bias", "velocity_bias_weight"),
)


def radar_span(h5: File) -> tuple[datetime, datetime] | None:
    """First start and last end of the radar volumes of a file, or None when it has none."""
    starts, ends = [], []
    for site in fs.list_radar_sites(h5):
        volumes = h5[f"/{fs.SPATIAL_3D}/radar/{site}/volumes"]
        if len(volumes["time"]) == 0:
            continue
        origin = datetime.fromisoformat(_text(volumes["time"].attrs["time_origin"]))
        starts.append(origin + timedelta(seconds=float(np.min(volumes["time"][()]))))
        ends.append(origin + timedelta(seconds=float(np.max(volumes["time_end"][()]))))
    if not starts:
        return None
    return min(starts).astimezone(timezone.utc), max(ends).astimezone(timezone.utc)


def radar_sections(h5: File) -> list[str]:
    """Every cross section of the file, as ``SITE/name``."""
    if not hasattr(fs, "list_radar_sections"):
        return []
    return [
        f"{site}/{name}" for site in fs.list_radar_sites(h5) for name in fs.list_radar_sections(h5, site)
    ]
