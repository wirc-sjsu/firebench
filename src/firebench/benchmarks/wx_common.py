"""
Weather-station benchmark machinery shared by benchmark cases.

Station selection by sensor-height trust tier, model/observation sensor-height compatibility, time
masks, weather requirement checks, the requirement run loop and score aggregation. The functions
take the case registries (``benchmark_functions``, ``requirements``, aggregation schemes) as
arguments, so every case can reuse them with its own registry; Caldor (``c001_caldor``) keeps thin
wrappers bound to its module-level registries.
"""

from datetime import datetime

import numpy as np
from h5py import File

from firebench import standardize as fs
from firebench import tools as ft
from firebench.tools.units import ureg


# ---------------------------
# Requirement checks and run loop
# ---------------------------
def run_weather_requirement(
    model_dataset: File,
    obs_dataset: File,
    list_benchmarks: list,
    required_datasets: dict,
    ctx: dict,
    req_name: str,
    benchmark_functions: dict,
):
    """Check a weather-station requirement, then run its benchmarks; empty station sets are ignored."""
    ft.logger.info("Check Requirement %s", req_name)
    bench_output = {}
    if not list_benchmarks:
        ft.logger.info("No benchmark to run for Requirement %s", req_name)
        return bench_output

    # Check requirement
    periods = weather_requirement_periods(benchmark_functions, list_benchmarks)
    selected_stations = weather_requirement_selected_stations(
        obs_dataset,
        benchmark_functions,
        list_benchmarks,
        ctx,
    )
    req_ok, miss = fs.validate_h5_weather_stations_structure(
        model_dataset,
        obs_dataset,
        required_datasets["variable"],
        required_datasets["station_pattern"],
        periods=periods,
        selected_stations=selected_stations,
    )

    # run benchmarks
    if req_ok:
        ft.logger.info("Requirement %s valid", req_name)
        validate_selected_tso_model_heights(
            model_dataset,
            obs_dataset,
            benchmark_functions,
            list_benchmarks,
            ctx,
        )
        for bench_id in list_benchmarks:
            ft.logger.info("Run Benchmark %s", bench_id)
            benchmark_result = benchmark_functions[bench_id](model_dataset, obs_dataset, ctx)
            if benchmark_result is None:
                ctx.setdefault("ignored_benchmarks", set()).add(bench_id)
                ft.logger.warning(
                    "Benchmark %s ignored because its weather station set is empty.", bench_id
                )
            else:
                bench_output[bench_id] = benchmark_result
    else:
        ft.logger.warning(
            "Requirement %s not satisfied. All related benchmarks ignored. Missing item(s): %s",
            req_name,
            miss,
        )
        log_missing_wx_station_requirements(req_name, required_datasets["variable"], miss)

    return bench_output


def weather_requirement_periods(
    benchmark_functions: dict, list_benchmarks: list[str]
) -> list[tuple[datetime, datetime]]:
    """Distinct ``period`` keywords of the selected weather benchmarks."""
    periods = []
    for bench_id in list_benchmarks:
        period = getattr(benchmark_functions[bench_id], "keywords", {}).get("period")
        if period is not None and period not in periods:
            periods.append(period)
    return periods


def selected_weather_specs(
    benchmark_functions: dict,
    selected_benchmarks: list[str],
) -> set[tuple[str, tuple[datetime, datetime], fs.WeatherStationSet]]:
    """``(variable, period, station_set)`` of the selected weather benchmarks."""
    selections = set()
    for bench_id in selected_benchmarks:
        benchmark = benchmark_functions.get(bench_id)
        keywords = getattr(benchmark, "keywords", {}) or {}
        if "wx_variable_name" not in keywords or "station_set" not in keywords:
            continue
        selections.add(
            (
                keywords["wx_variable_name"],
                keywords["period"],
                keywords["station_set"],
            )
        )
    return selections


def validate_selected_weather_confidence(
    obs_dataset: File,
    benchmark_functions: dict,
    selected_benchmarks: list[str],
    ctx: dict,
) -> None:
    """Resolve (and cache in ``ctx``) the station selections of the selected weather benchmarks."""
    selections = selected_weather_specs(benchmark_functions, selected_benchmarks)

    for variable, period, station_set in selections:
        select_weather_stations(obs_dataset, variable, period, station_set, ctx)

    if selections:
        ft.logger.info(
            "Validated observational sensor-height confidence for %d weather selection(s).",
            len(selections),
        )


def weather_requirement_selected_stations(
    obs_dataset: File,
    benchmark_functions: dict,
    selected_benchmarks: list[str],
    ctx: dict,
) -> set[str] | None:
    """Stations included by any selected weather benchmark, or ``None`` without weather benchmarks."""
    selections = selected_weather_specs(benchmark_functions, selected_benchmarks)
    if not selections:
        return None

    selected_stations = set()
    for variable, period, station_set in selections:
        selection = select_weather_stations(
            obs_dataset,
            variable,
            period,
            station_set,
            ctx,
        )
        selected_stations.update(item["station"] for item in selection["included"])
    return selected_stations


def validate_selected_tso_model_heights(
    model_dataset: File,
    obs_dataset: File,
    benchmark_functions: dict,
    selected_benchmarks: list[str],
    ctx: dict,
) -> None:
    """Resolve (and cache in ``ctx``) the TSO model-height compatibility of the selected benchmarks."""
    for variable, period, station_set in selected_weather_specs(benchmark_functions, selected_benchmarks):
        if station_set is fs.WeatherStationSet.TSO:
            model_height_compatible_selection(
                model_dataset,
                obs_dataset,
                variable,
                period,
                station_set,
                ctx,
            )


def validate_benchmark_inputs(obs_dataset: File, model_dataset: File) -> None:
    """Check both inputs follow the standard format and their referenced files are intact."""
    fs.validate_h5_std(obs_dataset)
    fs.validate_h5_std(model_dataset)
    for input_name, dataset in (
        ("observational", obs_dataset),
        ("model", model_dataset),
    ):
        valid, issue = fs.validate_h5_referenced_files(dataset)
        if not valid:
            raise ValueError(f"Invalid {input_name} referenced asset: {issue}")


def run_requirements(
    model_dataset: File,
    obs_dataset: File,
    requirements: dict,
    list_bench: list[str],
    ctx: dict,
) -> dict:
    """Run every requirement on the selected benchmarks and merge their results."""
    results = {}
    for req_name, req_dict in requirements.items():
        # filter list benchmarks
        list_filtered = [bench for bench in req_dict["benchmarks"] if bench in list_bench]
        ft.logger.debug("Filtered list of benchmarks to run with current requirement: %s", list_filtered)
        results = ft.merge_dictionaries(
            results,
            req_dict["main"](model_dataset, obs_dataset, list_filtered, req_dict["required_datasets"], ctx),
        )
    return results


def benchmark_requirements(requirements: dict) -> dict[str, list[str]]:
    """Map each benchmark ID to the requirements that run it."""
    requirements_by_benchmark = {}
    for req_name, req_dict in requirements.items():
        for bench_id in req_dict["benchmarks"]:
            requirements_by_benchmark.setdefault(bench_id, []).append(req_name)
    return requirements_by_benchmark


def raise_if_selected_benchmarks_missing(
    benchmark_results: dict,
    list_bench: list[str],
    ignored_benchmarks: set[str] | None,
    requirements: dict,
) -> None:
    """Raise if a selected benchmark neither produced a result nor was deliberately ignored."""
    ignored = ignored_benchmarks or set()
    missing_benchmarks = [
        bench_id for bench_id in list_bench if bench_id not in benchmark_results and bench_id not in ignored
    ]
    if not missing_benchmarks:
        return

    requirements_by_benchmark = benchmark_requirements(requirements)
    missing_details = [
        f"{bench_id} ({'/'.join(requirements_by_benchmark.get(bench_id, ['unknown requirement']))})"
        for bench_id in missing_benchmarks
    ]
    visible_details = ", ".join(missing_details[:10])
    if len(missing_details) > 10:
        visible_details = f"{visible_details}, ... {len(missing_details) - 10} more"

    ft.logger.error(
        "Selected benchmarks did not run, probably because their input requirement was not satisfied: %s",
        visible_details,
    )
    raise KeyError(
        "Selected benchmark results missing before aggregation: "
        f"{visible_details}. Check the requirement warning above for the missing HDF5 input."
    )


def aggregate_scheme_scores(
    benchmark_results: dict,
    scheme_name: str,
    scheme: dict,
    ignored_benchmarks: set[str] | None = None,
    display_names: dict[str, str] | None = None,
) -> dict:
    """
    Aggregate KPI scores into group scores and a total score with the weights of ``scheme``.

    A group whose weight is 0 is scored and displayed but moves neither the numerator nor the
    denominator of the total (informational group).
    """
    ignored = ignored_benchmarks or set()

    benchmark_results["score_card"] = {
        "Scheme": scheme,
    }
    # Get Score per group
    for group in scheme.keys():
        group_score = 0
        group_sum_weight = 0
        group_bench = scheme[group]["benchmarks"]
        for bench_id in group_bench.keys():
            if bench_id in ignored:
                ft.logger.info(
                    "Benchmark ID %s is ignored and does not contribute to group %s.",
                    bench_id,
                    group,
                )
                continue
            if bench_id not in benchmark_results["benchmarks"].keys():
                ft.logger.error("Benchmark ID: %s required for aggregation scheme not found.", bench_id)
                raise KeyError(f"Benchmark result missing for aggregation: {bench_id}. Check log")
            group_score += benchmark_results["benchmarks"][bench_id]["Score"] * group_bench[bench_id]
            group_sum_weight += group_bench[bench_id]
        if group_sum_weight == 0:
            ft.logger.warning("Group %s ignored because it has no eligible weighted KPI.", group)
            continue
        benchmark_results["score_card"][f"Score {group}"] = group_score / group_sum_weight
        ft.logger.info(
            "Score for group: %s = %.2f", group, benchmark_results["score_card"][f"Score {group}"]
        )

    # Get Total Score
    total_score = 0
    total_sum_weight = 0
    for group in scheme.keys():
        score_key = f"Score {group}"
        if score_key not in benchmark_results["score_card"]:
            continue
        total_score += benchmark_results["score_card"][score_key] * scheme[group]["weight"]
        total_sum_weight += scheme[group]["weight"]
    if total_sum_weight:
        benchmark_results["score_card"]["Score Total"] = total_score / total_sum_weight
        ft.logger.info("Total Score = %.2f", benchmark_results["score_card"]["Score Total"])
    else:
        ft.logger.warning("Total score ignored because no eligible weighted group remains.")

    benchmark_results["score_card"]["aggregation_scheme_name"] = scheme_name
    benchmark_results["score_card"]["benchmark_target_name"] = scheme_name
    if display_names:
        benchmark_results["score_card"]["group_display_names"] = display_names

    return benchmark_results


# ---------------------------
# Station selection and time masks
# ---------------------------
def log_missing_wx_station_requirements(req_name: str, variable_name: str, miss) -> None:
    """Log the stations and datasets a failed weather requirement is missing."""
    if not isinstance(miss, list):
        ft.logger.warning(
            "Weather station requirement %s missing variable %s: %s",
            req_name,
            variable_name,
            miss,
        )
        return

    ft.logger.warning(
        "Weather station requirement %s missing %s for %d station(s).",
        req_name,
        variable_name,
        len(miss),
    )
    for missing_station in miss:
        ft.logger.warning(
            "Weather station requirement %s missing for %s variable %s: %s",
            req_name,
            missing_station.get("station", "<unknown station>"),
            missing_station.get("variable", variable_name),
            ", ".join(missing_station.get("missing", [])),
        )


def select_weather_stations(
    obs_dataset: File,
    variable: str,
    period: tuple[datetime, datetime],
    station_set: fs.WeatherStationSet,
    ctx: dict | None = None,
) -> dict[str, list[dict]]:
    """Stations eligible for ``station_set`` with ``variable`` samples in ``period`` (cached in ``ctx``)."""
    context = ctx if ctx is not None else {}
    selection_cache = context.setdefault("weather_station_selections", {})
    cache_key = (variable, period, station_set)
    if cache_key in selection_cache:
        return selection_cache[cache_key]

    warning_cache = context.setdefault("weather_confidence_warnings", set())
    selection = {"included": [], "excluded": []}
    if fs.TIME_SERIES not in obs_dataset:
        selection_cache[cache_key] = selection
        return selection

    for station in obs_dataset[fs.TIME_SERIES].keys():
        if not station.startswith("station"):
            continue

        station_path = f"{fs.TIME_SERIES}/{station}"
        data_path = f"{station_path}/{variable}"
        if data_path not in obs_dataset:
            continue
        if not np.any(get_mask_from_period(obs_dataset, station_path, period)):
            selection["excluded"].append(
                {
                    "station": station,
                    "confidence": None,
                    "reason": "no samples in selected period",
                }
            )
            continue

        confidence = fs.parse_sensor_height_confidence(
            obs_dataset[data_path].attrs.get(fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE),
            station=station,
            variable=variable,
            warning_cache=warning_cache,
        )
        station_info = {
            "station": station,
            "confidence": int(confidence),
        }
        if fs.station_set_includes(station_set, confidence, variable):
            selection["included"].append(station_info)
        else:
            selection["excluded"].append(
                {
                    **station_info,
                    "reason": f"confidence level {int(confidence)} is not eligible for TSO",
                }
            )

    selection_cache[cache_key] = selection
    ft.logger.info(
        "Weather station selection: variable=%s period=%s/%s station_set=%s included=%d excluded=%d",
        variable,
        period[0].isoformat(),
        period[1].isoformat(),
        station_set.value,
        len(selection["included"]),
        len(selection["excluded"]),
    )
    for station_info in selection["included"]:
        ft.logger.debug(
            "Weather station included: station=%s variable=%s period=%s/%s station_set=%s confidence=%d",
            station_info["station"],
            variable,
            period[0].isoformat(),
            period[1].isoformat(),
            station_set.value,
            station_info["confidence"],
        )
    for station_info in selection["excluded"]:
        ft.logger.debug(
            "Weather station excluded: station=%s variable=%s period=%s/%s station_set=%s "
            "confidence=%s reason=%s",
            station_info["station"],
            variable,
            period[0].isoformat(),
            period[1].isoformat(),
            station_set.value,
            station_info["confidence"],
            station_info["reason"],
        )
    return selection


def model_height_compatible_selection(
    model_dataset: File,
    obs_dataset: File,
    variable: str,
    period: tuple[datetime, datetime],
    station_set: fs.WeatherStationSet,
    ctx: dict,
) -> dict[str, list[dict]]:
    """Station selection restricted, for height-dependent TSO, to matching model/obs sensor heights."""
    observation_selection = select_weather_stations(
        obs_dataset,
        variable,
        period,
        station_set,
        ctx,
    )
    if station_set is not fs.WeatherStationSet.TSO or not fs.tso_requires_sensor_height(variable):
        return observation_selection

    validation_cache = ctx.setdefault("weather_model_height_selections", {})
    cache_key = (variable, period, station_set)
    if cache_key in validation_cache:
        return validation_cache[cache_key]

    selection = {
        "included": [],
        "excluded": list(observation_selection["excluded"]),
    }
    warning_cache = ctx.setdefault("weather_confidence_warnings", set())
    for station_info in observation_selection["included"]:
        validation = fs.validate_weather_sensor_heights(
            obs_dataset,
            model_dataset,
            station=station_info["station"],
            variable=variable,
            warning_cache=warning_cache,
        )
        if validation.valid:
            selection["included"].append(
                {
                    **station_info,
                    "observation_height_m": validation.observation_height_m,
                    "model_height_m": validation.model_height_m,
                }
            )
            continue

        excluded = {
            **station_info,
            "reason": validation.reason,
        }
        selection["excluded"].append(excluded)
        ft.logger.warning(
            "TSO station excluded: station=%s variable=%s period=%s/%s reason=%s",
            station_info["station"],
            variable,
            period[0].isoformat(),
            period[1].isoformat(),
            validation.reason,
        )

    validation_cache[cache_key] = selection
    validation_log_message = " ".join(
        (
            "TSO model-height validation: variable=%s period=%s/%s included=%d excluded=%d",
            "tolerance=%g m",
        )
    )
    ft.logger.info(
        validation_log_message,
        variable,
        period[0].isoformat(),
        period[1].isoformat(),
        len(selection["included"]),
        len(selection["excluded"]),
        fs.SENSOR_HEIGHT_MATCH_TOLERANCE_METERS,
    )
    return selection


def get_mask_from_period(dataset: File, group_path: str, period: tuple[datetime, datetime]):
    """Boolean mask of the samples of ``group_path/time`` inside the closed ``period``."""
    time_ds = dataset[group_path]["time"]
    if "time_origin" in time_ds.attrs.keys() and "time_units" in time_ds.attrs.keys():
        # relative time definition
        time = time_ds[:]
        time_origin = datetime.fromisoformat(time_ds.attrs["time_origin"])
        time_units = time_ds.attrs["time_units"]
    else:
        # absolute time definition
        time_origin = period[0]
        time_units = "s"
        time = np.array(
            [
                (
                    datetime.fromisoformat(t.decode() if isinstance(t, bytes) else t) - time_origin
                ).total_seconds()
                for t in time_ds[:]
            ]
        )

    return mask_time_window_rel(time, time_origin, time_units, window=period, interval="closed")


def mask_time_window_rel(
    time_rel: np.ndarray,
    time_origin: datetime,
    time_units: str,
    window: tuple[datetime, datetime],
    interval: str = "closed",
) -> np.ndarray:
    """
    Create a boolean mask selecting samples whose time is within a datetime window.

    Parameters
    ----------
    time_rel : np.ndarray
        1D array of relative times from time_origin, dtype float (or float-like).
    time_origin : datetime
        Origin timestamp for time_rel.
    time_units : str
        Pint-compliant unit string for time_rel (e.g., "s", "min", "hour").
    window : (datetime, datetime)
        (start_dt, end_dt) datetimes defining the selection window.
    interval : {"closed","left_closed","right_closed","open"}, default "closed"
        Inclusivity of the endpoints:
        - "closed":        start <= t <= end
        - "left_closed":   start <= t <  end
        - "right_closed":  start <  t <= end
        - "open":          start <  t <  end

    Returns
    -------
    np.ndarray
        Boolean mask of shape (N,) where True indicates time within the window.
    """
    if time_rel.ndim != 1:
        raise ValueError(f"time_rel must be 1D, got shape {time_rel.shape}")
    if len(window) != 2:
        raise ValueError("window must be a tuple (start_dt, end_dt)")

    start_dt, end_dt = window
    if end_dt < start_dt:
        raise ValueError("window end_dt must be >= start_dt")

    # Basic tz-consistency check: either all naive or all aware
    origin_aware = time_origin.tzinfo is not None and time_origin.tzinfo.utcoffset(time_origin) is not None
    start_aware = start_dt.tzinfo is not None and start_dt.tzinfo.utcoffset(start_dt) is not None
    end_aware = end_dt.tzinfo is not None and end_dt.tzinfo.utcoffset(end_dt) is not None
    if not origin_aware == start_aware == end_aware:
        raise ValueError("time_origin, start_dt, and end_dt must all be naive or all be timezone-aware")

    # Convert datetime window to relative time in `time_units`
    start_seconds = (start_dt - time_origin).total_seconds()
    end_seconds = (end_dt - time_origin).total_seconds()

    start_rel = ureg.Quantity(start_seconds, "s").to(time_units).magnitude
    end_rel = ureg.Quantity(end_seconds, "s").to(time_units).magnitude

    # Ensure float arrays for safe comparisons
    t = np.asarray(time_rel, dtype=np.float64)

    return mask_time_window(interval, t, start_rel, end_rel)


def mask_time_window(
    interval: str, t: np.ndarray[np.float64], start_t: np.ndarray[np.float64], end_t: np.ndarray[np.float64]
):
    """Boolean mask of ``t`` within ``[start_t, end_t]`` with the requested endpoint inclusivity."""
    if interval == "closed":
        return (t >= start_t) & (t <= end_t)
    if interval == "left_closed":
        return (t >= start_t) & (t < end_t)
    if interval == "right_closed":
        return (t > start_t) & (t <= end_t)
    if interval == "open":
        return (t > start_t) & (t < end_t)

    raise ValueError(f"Unknown interval={interval}")
