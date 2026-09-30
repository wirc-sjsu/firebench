"""
Cadence-tier weather benchmarks: score forecasts on a fixed hourly (or 3-hourly) UTC grid.

Operational weather models write hourly output, while stations report on their own irregular
clocks. Instead of forcing the model onto each station's timestamps, a cadence tier defines
*mandatory* timestamps (UTC top-of-hour marks with ``hour % cadence == 0``) and joins model and
observation on them:

- the observation of a mark is the nearest *finite* sample within ``±obs_tolerance`` (a missing
  observation is never manufactured by interpolation);
- the model must provide the mark itself (within ``model_tolerance``, for float time encodings);
  a missing or NaN model value is penalized, as in the native tier;
- a station whose observations cover fewer than ``min_coverage`` of the marks is excluded from the
  KPI rather than scored on a near-empty sample.

The tolerance must stay below half the cadence, so one observation can never serve two marks.
"""

from datetime import datetime, timedelta, timezone

import hdf5plugin  # pylint: disable=unused-import  # registers the Zstd filter of station datasets
import numpy as np
from h5py import File

from firebench import metrics as fm
from firebench import standardize as fs
from firebench import tools as ft
from firebench.tools.units import ureg

from . import wx_common as wxc

DEFAULT_OBS_TOLERANCE_S = 600.0
DEFAULT_MODEL_TOLERANCE_S = 60.0
DEFAULT_MIN_COVERAGE = 0.5
PENALTY_VALUE = -1e6
CIRCULAR_PENALTY_OFFSET_DEG = 180.0


def check_tolerance(tolerance_s: float, cadence_hours: int) -> None:
    """A matching tolerance must be non-negative and below half the cadence."""
    if cadence_hours < 1:
        raise ValueError(f"cadence must be at least one hour, got {cadence_hours}")
    if not 0 <= tolerance_s < cadence_hours * 1800.0:
        raise ValueError(
            f"matching tolerance {tolerance_s:g} s must be below half the {cadence_hours} h cadence "
            f"({cadence_hours * 1800:g} s), otherwise one sample could serve two timestamps"
        )


def expand_window(window: tuple[datetime, datetime], tolerance_s: float) -> tuple[datetime, datetime]:
    """Widen a window by ``±tolerance_s`` so selection sees the samples matched to its edge marks."""
    delta = timedelta(seconds=tolerance_s)
    return window[0] - delta, window[1] + delta


def mandatory_timestamps(lead_window: tuple[datetime, datetime], cadence_hours: int) -> np.ndarray:
    """UTC top-of-hour marks inside the closed ``lead_window`` with ``hour % cadence_hours == 0``."""
    start, end = (_aware_utc(value) for value in lead_window)
    if end < start:
        raise ValueError("lead window end must not precede its start")
    mark = start.replace(minute=0, second=0, microsecond=0)
    if mark < start:
        mark += timedelta(hours=1)
    marks = []
    while mark <= end:
        if mark.hour % cadence_hours == 0:
            marks.append(np.datetime64(mark.replace(tzinfo=None), "s"))
        mark += timedelta(hours=1)
    return np.array(marks, dtype="datetime64[s]")


def station_times_utc(dataset: File, station_path: str) -> np.ndarray:
    """Timestamps of a station group as UTC ``datetime64[s]`` (relative or absolute encoding)."""
    time_ds = dataset[station_path]["time"]
    if "time_origin" in time_ds.attrs and "time_units" in time_ds.attrs:
        origin = _aware_utc(datetime.fromisoformat(_as_str(time_ds.attrs["time_origin"])))
        seconds = ureg.Quantity(
            np.asarray(time_ds[:], dtype=np.float64), _as_str(time_ds.attrs["time_units"])
        )
        offsets = np.rint(seconds.to("s").magnitude).astype("timedelta64[s]")
        return np.datetime64(origin.replace(tzinfo=None), "s") + offsets
    return np.array(
        [
            np.datetime64(_aware_utc(datetime.fromisoformat(_as_str(value))).replace(tzinfo=None), "s")
            for value in time_ds[:]
        ],
        dtype="datetime64[s]",
    )


def match_nearest(
    times: np.ndarray, targets: np.ndarray, tolerance_s: float, values: np.ndarray | None = None
) -> np.ndarray:
    """
    Index of the sample nearest to each target within ``±tolerance_s``, or -1.

    When ``values`` is given, only finite samples qualify, so a NaN at the closest timestamp falls
    back to the next closest finite sample. Ties go to the earlier sample.
    """
    times = np.asarray(times, dtype="datetime64[s]")
    targets = np.asarray(targets, dtype="datetime64[s]")
    candidates = np.arange(times.size)
    if values is not None:
        candidates = candidates[np.isfinite(np.asarray(values, dtype=np.float64))]
    result = np.full(targets.size, -1, dtype=np.int64)
    if candidates.size == 0 or targets.size == 0:
        return result

    order = candidates[np.argsort(times[candidates], kind="stable")]
    sorted_times = times[order].astype(np.int64)
    target_seconds = targets.astype(np.int64)
    right = np.searchsorted(sorted_times, target_seconds, side="left")
    left = right - 1
    has_left = left >= 0
    has_right = right < sorted_times.size
    left_gap = np.where(has_left, target_seconds - sorted_times[np.clip(left, 0, None)], np.inf)
    right_gap = np.where(
        has_right, sorted_times[np.clip(right, None, sorted_times.size - 1)] - target_seconds, np.inf
    )
    use_left = left_gap <= right_gap
    gap = np.where(use_left, left_gap, right_gap)
    chosen = np.where(use_left, left, right)
    within = gap <= tolerance_s
    result[within] = order[chosen[within]]
    return result


def bench_wx_cadence_index(
    model_dataset: File,
    obs_dataset: File,
    ctx: dict,
    kpi_name_custom: str,
    lead_window: tuple[datetime, datetime],
    period: tuple[datetime, datetime],
    wx_variable_name: str,
    common_unit: str,
    metric_func,
    stat_func,
    value_norm_param_m: float,
    station_set: fs.WeatherStationSet,
    cadence_hours: int,
    obs_tolerance_s: float = DEFAULT_OBS_TOLERANCE_S,
    model_tolerance_s: float = DEFAULT_MODEL_TOLERANCE_S,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
):
    """
    Weather KPI joined on the mandatory timestamps of ``lead_window`` at ``cadence_hours``.

    ``period`` is ``lead_window`` widened by the observation tolerance; it only drives station
    selection and requirement checks (the keyword names ``period``, ``wx_variable_name`` and
    ``station_set`` are read by the shared weather helpers). Returns ``None`` when no station can be
    scored, so the KPI is reported as ignored.
    """
    check_tolerance(obs_tolerance_s, cadence_hours)
    check_tolerance(model_tolerance_s, cadence_hours)
    selection = wxc.model_height_compatible_selection(
        model_dataset, obs_dataset, wx_variable_name, period, station_set, ctx
    )
    if not selection["included"]:
        ft.logger.warning(
            "Ignoring weather KPI %s: no stations are eligible for %s.", kpi_name_custom, station_set.value
        )
        return None
    targets = mandatory_timestamps(lead_window, cadence_hours)
    if targets.size == 0:
        ft.logger.warning(
            "Ignoring weather KPI %s: no %d-hourly timestamp in its window.", kpi_name_custom, cadence_hours
        )
        return None

    metric_rslt = []
    for station_info in selection["included"]:
        station = station_info["station"]
        pairs = _station_pairs(
            model_dataset,
            obs_dataset,
            station,
            wx_variable_name,
            common_unit,
            targets,
            obs_tolerance_s,
            model_tolerance_s,
        )
        coverage = pairs["obs_matched"] / targets.size
        if coverage < min_coverage:
            _record_exclusion(
                ctx, station, wx_variable_name, lead_window, cadence_hours, pairs, targets.size
            )
            continue
        var_obs = pairs["obs"]
        var_model = pairs["model"]
        missing_model = ~np.isfinite(var_model)
        if missing_model.any():
            ft.logger.warning(
                "Model misses %d of %d %d-hourly values for station %s and variable %s. "
                "Missing values replaced by a penalty.",
                int(missing_model.sum()),
                var_model.size,
                cadence_hours,
                station,
                wx_variable_name,
            )
            if wx_variable_name == "wind_direction":
                var_model[missing_model] = (var_obs[missing_model] + CIRCULAR_PENALTY_OFFSET_DEG) % 360.0
            else:
                var_model[missing_model] = PENALTY_VALUE
        metric_rslt.append(metric_func(var_model, var_obs))

    if not metric_rslt:
        ft.logger.warning(
            "Ignoring weather KPI %s: no station reaches %.0f%% observation coverage.",
            kpi_name_custom,
            100 * min_coverage,
        )
        return None
    ft.logger.info("Nb processed stations: %s", len(metric_rslt))
    rslt = stat_func(metric_rslt)
    ft.logger.info("%s: %f", kpi_name_custom, rslt)
    return {
        f"{kpi_name_custom}": rslt,
        "Score": fm.kpi_norm_symmetric_open_exponential(rslt, value_norm_param_m),
    }


def _station_pairs(
    model_dataset: File,
    obs_dataset: File,
    station: str,
    variable: str,
    common_unit: str,
    targets: np.ndarray,
    obs_tolerance_s: float,
    model_tolerance_s: float,
) -> dict:
    """Observation/model value pairs on the marks that have an observation."""
    station_path = f"{fs.TIME_SERIES}/{station}"
    data_path = f"{station_path}/{variable}"
    obs_values = fs.read_quantity_from_fb_dataset(data_path, obs_dataset).to(common_unit).magnitude
    obs_index = match_nearest(
        station_times_utc(obs_dataset, station_path), targets, obs_tolerance_s, obs_values
    )
    matched = obs_index >= 0

    model_values = fs.read_quantity_from_fb_dataset(data_path, model_dataset).to(common_unit).magnitude
    model_index = match_nearest(station_times_utc(model_dataset, station_path), targets, model_tolerance_s)[
        matched
    ]
    model_pairs = np.full(model_index.size, np.nan)
    has_model = model_index >= 0
    model_pairs[has_model] = np.asarray(model_values, dtype=np.float64)[model_index[has_model]]
    return {
        "obs": np.asarray(obs_values, dtype=np.float64)[obs_index[matched]],
        "model": model_pairs,
        "obs_matched": int(matched.sum()),
    }


def _record_exclusion(ctx, station, variable, lead_window, cadence_hours, pairs, n_marks) -> None:
    key = (station, variable, lead_window[0].isoformat(), lead_window[1].isoformat(), cadence_hours)
    exclusions = ctx.setdefault("cadence_exclusions", {})
    if key in exclusions:
        return
    exclusions[key] = {
        "station": station,
        "variable": variable,
        "lead_window": [lead_window[0].isoformat(), lead_window[1].isoformat()],
        "cadence_hours": cadence_hours,
        "matched_timestamps": pairs["obs_matched"],
        "mandatory_timestamps": n_marks,
        "reason": "observation coverage below the minimum",
    }
    ft.logger.info(
        "Station %s excluded from %s %d-hourly scoring: %d of %d timestamps observed.",
        station,
        variable,
        cadence_hours,
        pairs["obs_matched"],
        n_marks,
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"datetime {value!r} has no time zone")
    return value.astimezone(timezone.utc)


def _as_str(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)
