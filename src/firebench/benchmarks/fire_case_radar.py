"""
The radar plume family of the generic cases (``radar_plume``): a model's plume against the radar's
cross sections and echo tops.

The observations are the sections a standard file holds (``radar_cross_section``,
``/spatial_3d/radar/<SITE>/sections/<name>``) and the radar's sweeps. The model output gives its plume
at the radar's own times and places (``fire_case_radar_model``): its passive tracer and wind on the
nodes of each section at the start of each volume, and, for the sites of ``echo_top``, the count of
its plume cells over the site's frame in bins of height. Each volume of a period is paired with the
model time nearest its start, at most ``max_time_offset`` from it. Both sides of a section are then on
one grid, and compared as masks and ranks, never as amounts, since nothing relates a tracer to a
reflectivity:

- the observed plume is the radar plume mask (``resources/radar.toml``); the model's, where its
  tracer, a mass concentration, reaches ``tracer_threshold`` (``ug/m^3``). The threshold is the
  value that best matches the radar's mask for a model, found with ``radar_plume_threshold_sweep``;
- the plume top is the 90th percentile of the heights of a plume's cells, its centroid the mean of
  their position on the section weighted by linear reflectivity or by the tracer;
- the model's radial velocity is its wind along the beam through each node, folded into the Nyquist
  interval of the sweep the observation was read on, so the aliased observation needs no dealiasing;
- over the frame of a site, the plume top of a volume is the 90th percentile of the heights of the
  radar's plume gates (``radar_echo_top_series``) and of the model's plume cells (its counts, linear
  inside a bin), the model's plume being where its tracer reaches the same threshold over the cells
  of the frame the radar can see;
- on the radar's map grid over the frame, each side's plume top is the highest plume gate, or model
  plume cell, over each map cell (``radar_plume_top_maps``; the model's ``plume_top``). Where the
  radar sees (its beam band, ``radar_beam_bands``), the footprints are the cells with a top: their
  IoU, the error of the tops where both have one, and the distance between their centroids weighted
  by the top.

Every number is in ``fire_case.toml`` (``[radar_plume]``) or ``radar.toml``. A KPI no volume of its
period can give is not computed: its function returns None and it is left out of its group.

``radar_plume_values`` gives what these KPIs compare, for a figure.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

import numpy as np
from h5py import File
from scipy.stats import spearmanr

from .. import metrics as fm
from .. import standardize as fs
from .. import tools as ft
from .fire_case_parameters import CONCENTRATION_UNITS, RadarPlumeParameters, concentration_factor
from .fire_case_radar_model import (  # pylint: disable=unused-import
    MODEL_GROUP,
    POINTS,
    TRACER,
    WIND,
    _EARTH_RADIUS,
    ModelSection,
    _text,
    _times,
    histogram_quantile,
    model_frame,
    model_requirements,
    model_top_maps,
    top_requirements,
)

REFLECTIVITY = "radar_reflectivity"
CORRELATION = "radar_correlation_coefficient"
VELOCITY = "radar_radial_velocity"
TOP_LEVEL = 0.9


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
    volumes: list[int] = field(default_factory=list)  # index of each volume in the section
    model_times: list[np.datetime64] = field(default_factory=list)
    # The observed and model radial velocity and the Nyquist velocity on every node, NaN where none;
    # None when the radar kept no velocity.
    velocity: list[np.ndarray] | None = None
    radial: list[np.ndarray] | None = None
    nyquist: list[np.ndarray] | None = None
    # Why the model's plume cannot be told (a tracer that is no mass concentration), or None: the KPIs
    # that need it are then not computed.
    problem: str | None = None


def fold(difference: np.ndarray, nyquist: np.ndarray) -> np.ndarray:
    """A velocity difference folded into the Nyquist interval: ``((d + vN) mod 2vN) - vN``."""
    return np.mod(difference + nyquist, 2 * nyquist) - nyquist


def _utc64(moment: datetime) -> np.datetime64:
    return np.datetime64(moment.astimezone(timezone.utc).replace(tzinfo=None), "ms")


def plume_pairs(  # pylint: disable=too-many-locals,too-many-arguments
    model: File,
    obs: File,
    section: str,
    period: tuple[datetime, datetime],
    model_group: str,
    parameters: RadarPlumeParameters,
    min_dbz: float | None = None,
) -> PlumePairs:
    """
    Both sides of ``section`` (``SITE/name``) for the volumes of ``period``, on the section's nodes.
    ``min_dbz`` replaces the reflectivity of the radar's plume mask, for a calibration only.
    """
    site, name = section.split("/", 1)
    cut = fs.read_radar_section(obs, site, name)
    mask = fs.radar_parameters()
    lowest_dbz = mask.min_dbz if min_dbz is None else float(min_dbz)
    plane = cut.plane
    sampler = ModelSection(model, model_group, section, plane.height.shape)
    start, end = (_utc64(moment) for moment in period)
    azimuth = np.radians(cut.azimuth.astype(np.float64))
    with_velocity = VELOCITY in cut.values
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
        velocity_differences=[] if with_velocity else None,
        velocity=[] if with_velocity else None,
        radial=[] if with_velocity else None,
        nyquist=[] if with_velocity else None,
        problem=sampler.tracer_problem,
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
        sampled = sampler.values(index)
        tracer = sampled[TRACER]
        if not np.isfinite(tracer).any():
            ft.logger.warning("Radar plume %s: the model gives no tracer at %s.", section, time)
            continue
        reflectivity = cut.values[REFLECTIVITY][volume].astype(np.float64)
        scored = np.isfinite(reflectivity) & np.isfinite(tracer)
        low, high = mask.rhohv_range
        with np.errstate(invalid="ignore"):
            observed = scored & (reflectivity >= lowest_dbz)
            if CORRELATION in cut.values:
                correlation = cut.values[CORRELATION][volume]
                observed &= (correlation > low) & (correlation < high)
            modelled = scored & (tracer >= parameters.tracer_threshold) & (pairs.problem is None)
        pairs.times.append(time)
        pairs.volumes.append(volume)
        pairs.model_times.append(sampler.time[index])
        pairs.reflectivity.append(np.where(scored, reflectivity, np.nan))
        pairs.tracer.append(np.where(scored, tracer, np.nan))
        pairs.observed.append(observed)
        pairs.modelled.append(modelled)
        if with_velocity:
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
            pairs.velocity.append(observed_velocity)
            pairs.radial.append(radial)
            pairs.nyquist.append(nyquist)
    return pairs


@dataclass
class TopPairs:
    """The plume top of the radar and of the model over the frame of a site, per volume of a period."""

    site: str
    times: list[np.datetime64]
    model_times: list[np.datetime64]
    observed: list[float]  # 90th percentile of the heights of the radar's plume gates, NaN when none
    modelled: list[float]  # of the model's plume cells, NaN when none
    n_gates: list[int]
    n_cells: list[int]
    problem: str | None = None  # why nothing can be compared


def _nearest(times: np.ndarray, time: np.datetime64, max_offset_s: float) -> int | None:
    if len(times) == 0:
        return None
    offset = np.abs((times - time) / np.timedelta64(1, "s"))
    index = int(np.argmin(offset))
    return index if offset[index] <= max_offset_s else None


def _echo_tops(obs: File, site: str, ctx: dict | None) -> fs.EchoTopSeries:
    cache = {} if ctx is None else ctx.setdefault("radar_echo_tops", {})
    if site not in cache:
        cache[site] = fs.radar_echo_top_series(obs, site, quantiles=(TOP_LEVEL,))
    return cache[site]


def top_pairs(  # pylint: disable=too-many-arguments
    model: File,
    obs: File,
    site: str,
    period: tuple[datetime, datetime],
    model_group: str,
    parameters: RadarPlumeParameters,
    ctx: dict | None = None,
) -> TopPairs:
    """The plume top of both sides over the frame of ``site``, for the volumes of ``period``."""
    pairs = TopPairs(site=site, times=[], model_times=[], observed=[], modelled=[], n_gates=[], n_cells=[])
    model_times, edges, counts, threshold = model_frame(model, model_group, site)
    pairs.problem = _threshold_problem(threshold, parameters)
    if pairs.problem is not None:
        return pairs
    series = _echo_tops(obs, site, ctx)
    start, end = (_utc64(moment) for moment in period)
    for volume, time in enumerate(series.time):
        if not start <= time <= end:
            continue
        index = _nearest(model_times, time, parameters.max_time_offset)
        if index is None or not np.all(np.isfinite(counts[index])):
            ft.logger.warning("Radar plume top %s: no model output near %s.", site, time)
            continue
        pairs.times.append(time)
        pairs.model_times.append(model_times[index])
        pairs.observed.append(float(series.height_quantiles[TOP_LEVEL][volume]))
        pairs.modelled.append(histogram_quantile(edges, counts[index], TOP_LEVEL))
        pairs.n_gates.append(int(series.n_gates[volume]))
        pairs.n_cells.append(int(np.sum(counts[index])))
    return pairs


def _threshold_problem(threshold: float | None, parameters: RadarPlumeParameters) -> str | None:
    """Why a frame the model counted at ``threshold`` cannot be scored with ``parameters``, or None."""
    if threshold is None:
        return (
            "the model counted its plume cells at a share of its largest tracer: prepare it again with "
            "a new kit"
        )
    if not np.isclose(threshold, parameters.tracer_threshold):
        return (
            f"the model counted its plume cells at a tracer of {threshold:g} {CONCENTRATION_UNITS}, "
            f"not at {parameters.tracer_threshold:g}"
        )
    return None


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
    return float(np.quantile(height[mask], TOP_LEVEL))


def _iou(observed: np.ndarray, modelled: np.ndarray) -> float | None:
    """The IoU of two masks; None when both are empty."""
    union = int((observed | modelled).sum())
    return float((observed & modelled).sum() / union) if union else None


def _centroid(pairs: PlumePairs, mask: np.ndarray, weights: np.ndarray) -> np.ndarray:
    weight = weights[mask]
    return np.array([np.sum(weight * pairs.u[mask]), np.sum(weight * pairs.v[mask])]) / np.sum(weight)


def _observed_centroid(pairs: PlumePairs, reflectivity: np.ndarray, observed: np.ndarray) -> np.ndarray:
    return _centroid(pairs, observed, 10.0 ** (np.nan_to_num(reflectivity) / 10.0))


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
    if pairs.problem is not None and kpi not in ("velocity_rmse", "velocity_bias"):
        return _skipped(label, pairs.problem)
    values = []
    if kpi == "mask_iou":
        values = [value for value in map(_iou, pairs.observed, pairs.modelled) if value is not None]
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
                distance = _observed_centroid(pairs, reflectivity, observed) - _centroid(
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


@dataclass
class MapPairs:  # pylint: disable=too-many-instance-attributes
    """Both sides' plume top on the radar's map grid over a site's frame, per volume of a period."""

    site: str
    latitude: np.ndarray  # (n_lat,) from north to south
    longitude: np.ndarray
    times: list[np.datetime64]
    model_times: list[np.datetime64]
    observed: list[np.ndarray]  # (n_lat, n_lon) m above mean sea level, NaN where no plume
    modelled: list[np.ndarray]
    visible: list[np.ndarray]  # (n_lat, n_lon) the cells the radar sees
    problem: str | None = None


def _observed_maps(obs: File, site: str, volumes, resolution: float, ctx: dict | None) -> dict:
    """The radar's plume top and visible cells of each volume, read once per site and volume."""
    cache = {} if ctx is None else ctx.setdefault("radar_plume_maps", {})
    known = cache.setdefault(site, {})
    missing = [int(volume) for volume in volumes if int(volume) not in known]
    if missing:
        tops = fs.radar_plume_top_maps(obs, site, resolution=resolution, volumes=missing)
        lowest, _ = fs.radar_beam_bands(obs, site, resolution=resolution, volumes=missing)
        for position, volume in enumerate(missing):
            known[volume] = (tops[position].astype(np.float64), np.isfinite(lowest[position]))
    return known


def map_pairs(  # pylint: disable=too-many-arguments,too-many-locals
    model: File,
    obs: File,
    site: str,
    period: tuple[datetime, datetime],
    model_group: str,
    parameters: RadarPlumeParameters,
    ctx: dict | None = None,
) -> MapPairs:
    """Both sides' plume top over the map of ``site`` for the volumes of ``period``."""
    latitude, longitude = fs.radar_map_axes(obs, site, resolution=parameters.map_resolution)
    pairs = MapPairs(site, latitude, longitude, [], [], [], [], [])
    frame_times, _, counts, threshold = model_frame(model, model_group, site)
    pairs.problem = _threshold_problem(threshold, parameters)
    if pairs.problem is not None:
        return pairs
    model_times, model_lat, model_lon, model_tops = model_top_maps(model, model_group, site)
    if model_tops.shape[1:] != (len(latitude), len(longitude)) or not (
        np.allclose(model_lat, latitude) and np.allclose(model_lon, longitude)
    ):
        pairs.problem = "the model's plume top map is not on the radar's map grid of this case"
        return pairs
    volume_times = _observed_volume_times(obs, site)
    start, end = (_utc64(moment) for moment in period)
    chosen = [volume for volume, time in enumerate(volume_times) if start <= time <= end]
    maps = _observed_maps(obs, site, chosen, parameters.map_resolution, ctx)
    for volume in chosen:
        time = volume_times[volume]
        index = _nearest(model_times, time, parameters.max_time_offset)
        given = _nearest(frame_times, time, parameters.max_time_offset)
        if index is None or given is None or not np.all(np.isfinite(counts[given])):
            continue
        observed, visible = maps[volume]
        pairs.times.append(time)
        pairs.model_times.append(model_times[index])
        pairs.observed.append(np.where(visible, observed, np.nan))
        pairs.modelled.append(np.where(visible, model_tops[index], np.nan))
        pairs.visible.append(visible)
    return pairs


def _observed_volume_times(obs: File, site: str) -> np.ndarray:
    return _times(obs[f"/{fs.SPATIAL_3D}/radar/{site}/volumes/time"])


def map_metrics(observed: np.ndarray, modelled: np.ndarray, latitude, longitude) -> dict[str, float | None]:
    """
    The values the map KPIs average, for one volume: the IoU of the footprints (cells with a top; None
    when neither has one), the error and bias of the tops where both have one, and the distance in m
    between the footprints' centroids weighted by the top (None unless both have a footprint).
    """
    seen, given = np.isfinite(observed), np.isfinite(modelled)
    union = int((seen | given).sum())
    both = seen & given
    differences = modelled[both] - observed[both]
    values: dict[str, float | None] = {
        "iou": float((seen & given).sum() / union) if union else None,
        "mae": float(np.mean(np.abs(differences))) if differences.size else None,
        "bias": float(np.mean(differences)) if differences.size else None,
        "centroid_distance": None,
    }
    if seen.any() and given.any():
        lat, lon = np.meshgrid(
            np.asarray(latitude, dtype=np.float64), np.asarray(longitude, dtype=np.float64), indexing="ij"
        )
        reference = np.radians(float(np.mean(latitude)))
        x = np.radians(lon) * np.cos(reference) * _EARTH_RADIUS
        y = np.radians(lat) * _EARTH_RADIUS

        def centroid(mask, tops):
            weight = tops[mask]
            return np.array([np.sum(weight * x[mask]), np.sum(weight * y[mask])]) / np.sum(weight)

        values["centroid_distance"] = float(
            np.hypot(*(centroid(given, modelled) - centroid(seen, observed)))
        )
    return values


def _maps(model: File, obs: File, ctx: dict, site: str, period_name: str, period, model_group, parameters):
    """The map pairs of a site and a period, computed once for every KPI of their group."""
    cache = ctx.setdefault("radar_plume_map_pairs", {})
    key = (site, period_name)
    if key not in cache:
        cache[key] = map_pairs(model, obs, site, period, model_group, parameters, ctx)
    return cache[key]


def _tops(model: File, obs: File, ctx: dict, site: str, period_name: str, period, model_group, parameters):
    """The plume tops of a site and a period, computed once for every KPI of their group."""
    cache = ctx.setdefault("radar_plume_top", {})
    key = (site, period_name)
    if key not in cache:
        cache[key] = top_pairs(model, obs, site, period, model_group, parameters, ctx)
    return cache[key]


def bench_radar_top(  # pylint: disable=too-many-arguments
    model_dataset: File,
    obs_dataset: File,
    ctx: dict,
    kpi_name_custom: str,
    kpi: str,
    site: str,
    period_name: str,
    period: tuple[datetime, datetime],
    model_group: str,
    parameters: RadarPlumeParameters,
):
    """One KPI of the plume over the frame of a site, on one period, scored from 0 to 100."""
    label = f"{kpi_name_custom} {site} {period_name}"
    if kpi in MAP_KPIS:
        maps = _maps(model_dataset, obs_dataset, ctx, site, period_name, period, model_group, parameters)
        return _map_kpi(maps, kpi, label, parameters)
    pairs = _tops(model_dataset, obs_dataset, ctx, site, period_name, period, model_group, parameters)
    if pairs.problem is not None:
        return _skipped(label, pairs.problem)
    differences = [
        modelled - observed
        for observed, modelled in zip(pairs.observed, pairs.modelled)
        if np.isfinite(observed) and np.isfinite(modelled)
    ]
    if not differences:
        return _skipped(label, "no volume of the period has a plume on both sides")
    if kpi == "top_series_error":
        value = float(np.mean(np.abs(differences)))
        score = fm.kpi_norm_half_open_exponential(value, 0, parameters.top_error_at_score_50)
    elif kpi == "top_series_bias":
        value = float(np.mean(differences))
        score = fm.kpi_norm_symmetric_open_exponential(value, parameters.top_error_at_score_50)
    else:
        raise ValueError(f"unknown radar plume top KPI {kpi!r}")
    ft.logger.info("%s: %f", label, value)
    return {label: value, "Score": score}


def _map_kpi(maps: MapPairs, kpi: str, label: str, parameters: RadarPlumeParameters):
    if maps.problem is not None:
        return _skipped(label, maps.problem)
    if not maps.times:
        return _skipped(label, "no volume of the period has a model output time near it")
    key = MAP_KPIS[kpi]
    values = [
        value
        for value in (
            map_metrics(observed, modelled, maps.latitude, maps.longitude)[key]
            for observed, modelled in zip(maps.observed, maps.modelled)
        )
        if value is not None
    ]
    if not values:
        reason = (
            "neither side has a plume the radar sees in any volume"
            if key == "iou"
            else ("no volume has a plume on both sides")
        )
        return _skipped(label, reason)
    value = float(np.mean(values))
    if kpi == "footprint_iou":
        score = fm.kpi_norm_bounded_linear(value, 0, 1)
    elif kpi == "top_map_mae":
        score = fm.kpi_norm_half_open_exponential(value, 0, parameters.top_error_at_score_50)
    elif kpi == "top_map_bias":
        score = fm.kpi_norm_symmetric_open_exponential(value, parameters.top_error_at_score_50)
    else:
        score = fm.kpi_norm_half_open_exponential(value, 0, parameters.footprint_centroid_at_score_50)
    ft.logger.info("%s: %f", label, value)
    return {label: value, "Score": score}


# The map KPIs of `bench_radar_top`, and the value of `map_metrics` each averages.
MAP_KPIS = {
    "footprint_iou": "iou",
    "top_map_mae": "mae",
    "top_map_bias": "bias",
    "footprint_centroid": "centroid_distance",
}

# The KPIs of the plume over the frame of a site: name, the key of `bench_radar_top`, and the key of
# its weight.
RADAR_TOP_KPIS = (
    ("Plume Top Series Error", "top_series_error", "top_series_error_weight"),
    ("Plume Top Series Bias", "top_series_bias", "top_series_bias_weight"),
    ("Plume Footprint IoU", "footprint_iou", "footprint_iou_weight"),
    ("Plume Top Map MAE", "top_map_mae", "top_map_mae_weight"),
    ("Plume Top Map Bias", "top_map_bias", "top_map_bias_weight"),
    ("Footprint Centroid Distance", "footprint_centroid", "footprint_centroid_weight"),
)


def _iso(time: np.datetime64) -> str:
    return f"{np.datetime_as_string(np.datetime64(time, 'ms'), unit='ms')}Z"


def _in_periods(times, periods: dict[str, tuple[datetime, datetime]]) -> dict[str, list[int]]:
    found = {}
    for name, (start, end) in periods.items():
        low, high = _utc64(start), _utc64(end)
        found[name] = [index for index, time in enumerate(times) if low <= time <= high]
    return found


def _stack(arrays: list[np.ndarray] | None, shape: tuple, dtype) -> np.ndarray | None:
    if arrays is None:
        return None
    return np.stack(arrays).astype(dtype) if arrays else np.zeros((0, *shape), dtype=dtype)


def _section_values(model: File, obs: File, section: str, span, periods, model_group, parameters) -> dict:
    try:
        pairs = plume_pairs(model, obs, section, span, model_group, parameters)
    except (KeyError, ValueError) as error:
        return {"section": section, "problem": str(error)}
    site, name = section.split("/", 1)
    plane = fs.read_radar_section(obs, site, name).plane
    shape = plane.height.shape
    iou, top_observed, top_modelled, centroid_observed, centroid_modelled = [], [], [], [], []
    for reflectivity, tracer, observed, modelled in zip(
        pairs.reflectivity, pairs.tracer, pairs.observed, pairs.modelled
    ):
        value = _iou(observed, modelled)
        iou.append(np.nan if value is None else value)
        top_observed.append(_p90(pairs.height, observed) if observed.any() else np.nan)
        top_modelled.append(_p90(pairs.height, modelled) if modelled.any() else np.nan)
        centroid_observed.append(
            _observed_centroid(pairs, reflectivity, observed) if observed.any() else np.full(2, np.nan)
        )
        centroid_modelled.append(
            _centroid(pairs, modelled, np.nan_to_num(tracer)) if modelled.any() else np.full(2, np.nan)
        )
    return {
        "section": section,
        "problem": pairs.problem,
        "u": np.asarray(plane.u),
        "v": np.asarray(plane.v),
        "position_lat": np.asarray(plane.latitude),
        "position_lon": np.asarray(plane.longitude),
        "position_alt": np.asarray(plane.height),
        "points": [list(point) for point in plane.points],
        "time": [_iso(time) for time in pairs.times],
        "model_time": [_iso(time) for time in pairs.model_times],
        "volume": np.asarray(pairs.volumes, dtype=np.int64),
        "periods": _in_periods(pairs.times, periods),
        "reflectivity": _stack(pairs.reflectivity, shape, np.float32),
        "observed": _stack(pairs.observed, shape, bool),
        "tracer": _stack(pairs.tracer, shape, np.float32),
        "modelled": _stack(pairs.modelled, shape, bool),
        "velocity": _stack(pairs.velocity, shape, np.float32),
        "radial": _stack(pairs.radial, shape, np.float32),
        "nyquist": _stack(pairs.nyquist, shape, np.float32),
        "iou": np.asarray(iou, dtype=np.float64),
        "top_observed": np.asarray(top_observed, dtype=np.float64),
        "top_modelled": np.asarray(top_modelled, dtype=np.float64),
        "centroid_observed": np.asarray(centroid_observed, dtype=np.float64).reshape(-1, 2),
        "centroid_modelled": np.asarray(centroid_modelled, dtype=np.float64).reshape(-1, 2),
    }


def _map_values(model: File, obs: File, site: str, span, periods, model_group, parameters) -> dict:
    try:
        maps = map_pairs(model, obs, site, span, model_group, parameters)
    except (KeyError, ValueError) as error:
        return {"problem": str(error)}
    if maps.problem is not None:
        return {"problem": maps.problem}
    shape = (len(maps.latitude), len(maps.longitude))
    metrics = [
        map_metrics(observed, modelled, maps.latitude, maps.longitude)
        for observed, modelled in zip(maps.observed, maps.modelled)
    ]
    return {
        "problem": None,
        "latitude": maps.latitude,
        "longitude": maps.longitude,
        "time": [_iso(time) for time in maps.times],
        "model_time": [_iso(time) for time in maps.model_times],
        "periods": _in_periods(maps.times, periods),
        "observed": _stack(maps.observed, shape, np.float32),
        "modelled": _stack(maps.modelled, shape, np.float32),
        "visible": _stack(maps.visible, shape, bool),
        **{
            name: np.array(
                [np.nan if item[name] is None else item[name] for item in metrics], dtype=np.float64
            )
            for name in ("iou", "mae", "bias", "centroid_distance")
        },
    }


def _top_values(model: File, obs: File, site: str, span, periods, model_group, parameters) -> dict:
    try:
        pairs = top_pairs(model, obs, site, span, model_group, parameters)
    except (KeyError, ValueError) as error:
        return {"site": site, "problem": str(error)}
    return {
        "map": _map_values(model, obs, site, span, periods, model_group, parameters),
        "site": site,
        "problem": pairs.problem,
        "time": [_iso(time) for time in pairs.times],
        "model_time": [_iso(time) for time in pairs.model_times],
        "periods": _in_periods(pairs.times, periods),
        "observed": np.asarray(pairs.observed, dtype=np.float64),
        "modelled": np.asarray(pairs.modelled, dtype=np.float64),
        "n_gates": np.asarray(pairs.n_gates, dtype=np.int64),
        "n_cells": np.asarray(pairs.n_cells, dtype=np.int64),
    }


def model_points(model: File, model_group: str) -> dict | None:
    """The model's plume cells kept for figures (``write_plume_points``), or None when it gave none; the
    tracer in ``CONCENTRATION_UNITS``, or as given (and its units) when it is no mass concentration."""
    group = model.get(f"{model_group}/{POINTS}")
    if group is None:
        return None
    points = {
        "time": [_iso(time) for time in _times(group["time"])],
        **{
            name: np.asarray(group[name][()])
            for name in ("offset", "count", "position_lon", "position_lat", "position_z", TRACER)
        },
        "tracer_units": _text(group[TRACER].attrs.get("units", "")),
    }
    try:
        factor = concentration_factor(points["tracer_units"])
    except ValueError:
        return points
    return {**points, TRACER: points[TRACER] * factor, "tracer_units": CONCENTRATION_UNITS}


def radar_plume_values(  # pylint: disable=too-many-arguments
    model: File,
    obs: File,
    entry: dict,
    periods: dict[str, tuple[datetime, datetime]],
    parameters: RadarPlumeParameters,
) -> dict:
    """
    What the KPIs of the family compare, for a figure, over the span of the entry's periods.

    ``sections`` holds one item per section of the entry: its nodes, and for each volume the model
    has a time for (``time``, the volume's start, and ``model_time``), both sides on the nodes
    (``reflectivity``, the observed mask ``observed``, ``tracer``, the model mask ``modelled``, the
    observed and model radial velocity ``velocity`` and ``radial`` with the ``nyquist`` velocity, or
    None when the radar kept no velocity), and the values the KPIs average: ``iou`` (NaN when neither
    side has a plume), ``top_observed`` and ``top_modelled``, ``centroid_observed`` and
    ``centroid_modelled`` (u, v in m; NaN when a side has none). ``tops`` holds one item per site of
    ``echo_top``, the plume top of both sides over its frame per volume, and ``map``, both sides' plume
    top on the radar's map grid per volume (``observed``, ``modelled``, the cells the radar sees
    ``visible``) with the values the map KPIs average (``iou``, ``mae``, ``bias``,
    ``centroid_distance``; NaN where a volume gives none). ``periods`` gives, in each,
    the indices of the volumes each period scores. An item that cannot be read has its reason in
    ``problem``. ``points`` is the model's plume cells kept for figures, or None.
    """
    names = list(entry["periods"])
    span = (min(periods[name][0] for name in names), max(periods[name][1] for name in names))
    chosen = {name: periods[name] for name in names}
    group = entry["model_group"]
    return {
        "model_group": group,
        "tracer_threshold": parameters.tracer_threshold,
        "tracer_threshold_units": CONCENTRATION_UNITS,
        "top_level": TOP_LEVEL,
        "sections": [
            _section_values(model, obs, section, span, chosen, group, parameters)
            for section in entry["sections"]
        ],
        "tops": [
            _top_values(model, obs, site, span, chosen, group, parameters)
            for site in entry.get("echo_top", [])
        ],
        "points": model_points(model, group),
    }


def radar_plume_threshold_sweep(  # pylint: disable=too-many-arguments,too-many-locals
    model: File,
    obs: File,
    entry: dict,
    periods: dict[str, tuple[datetime, datetime]],
    parameters: RadarPlumeParameters,
    thresholds,
    min_dbz: float | None = None,
) -> dict:
    """
    The section KPIs of the family at each tracer threshold of ``thresholds`` (``ug/m^3``), to find
    the threshold whose plume best matches the radar's for a model: the value ``tracer_threshold`` of
    ``fire_case.toml`` is then set to.

    Each section and period is read once; only the model's mask changes between thresholds. The
    frames are left out: a model counts its plume cells over a frame at one threshold.
    ``min_dbz`` replaces the reflectivity of the radar's plume mask (``radar.toml``) for the sweep.

    Returns ``thresholds``; ``min_dbz``, the mask's reflectivity used; ``items``, one per section and
    period, with ``values`` and ``scores``, KPI name to a list over the thresholds (None where the KPI
    is not computed), and ``intersection`` and ``union``, the node counts of both masks summed over
    its volumes; ``pooled_iou``, over every item; and ``best``, the threshold of the largest pooled
    IoU (the lowest of a tie), or None when no mask has a node.
    """
    chosen = sorted({float(value) for value in thresholds})
    if not chosen or chosen[0] <= 0:
        raise ValueError("the thresholds must be values above 0")
    group = entry["model_group"]
    lowest_dbz = fs.radar_parameters().min_dbz if min_dbz is None else float(min_dbz)
    items, intersection, union = [], np.zeros(len(chosen)), np.zeros(len(chosen))
    for section in entry["sections"]:
        for period_name in entry["periods"]:
            period = periods[period_name]
            base = plume_pairs(model, obs, section, period, group, parameters, min_dbz=lowest_dbz)
            item = {
                "section": section,
                "period": period_name,
                "problem": base.problem,
                "n_volumes": len(base.times),
                "values": {name: [] for name, _, _ in RADAR_KPIS},
                "scores": {name: [] for name, _, _ in RADAR_KPIS},
                "intersection": [],
                "union": [],
            }
            for threshold in chosen:
                with np.errstate(invalid="ignore"):
                    modelled = [
                        np.isfinite(tracer) & (tracer >= threshold) & (base.problem is None)
                        for tracer in base.tracer
                    ]
                pairs = replace(base, modelled=modelled)
                swept = replace(parameters, tracer_threshold=threshold)
                ctx = {"radar_plume": {(section, period_name): pairs}}
                for kpi_name, kpi, _ in RADAR_KPIS:
                    result = bench_radar_plume(
                        model, obs, ctx, kpi_name, kpi, section, period_name, period, group, swept
                    )
                    label = f"{kpi_name} {section} {period_name}"
                    item["values"][kpi_name].append(None if result is None else result[label])
                    item["scores"][kpi_name].append(None if result is None else result["Score"])
                item["intersection"].append(
                    int(sum((o & m).sum() for o, m in zip(base.observed, modelled)))
                )
                item["union"].append(int(sum((o | m).sum() for o, m in zip(base.observed, modelled))))
            intersection += item["intersection"]
            union += item["union"]
            items.append(item)
    with np.errstate(invalid="ignore", divide="ignore"):
        pooled = np.where(union > 0, intersection / union, np.nan)
    best = None if not np.isfinite(pooled).any() else chosen[int(np.nanargmax(pooled))]
    return {
        "thresholds": chosen,
        "units": CONCENTRATION_UNITS,
        "min_dbz": lowest_dbz,
        "items": items,
        "pooled_iou": [None if np.isnan(value) else float(value) for value in pooled],
        "best": best,
    }


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
