import argparse
import copy
import json
import re
from h5py import File
import geopandas as gpd
from functools import partial
from scipy.interpolate import NearestNDInterpolator
from pathlib import Path
from datetime import datetime, timedelta
from firebench import tools as ft
from firebench import standardize as fs
from firebench import metrics as fm
from firebench import signing as fsi
from firebench.benchmarks import c001_caldor_config as cfg
from firebench.plotting import plot_perimeter_contours
import numpy as np
from firebench import __version__ as fb_version
from firebench import Quantity

CASE_NAME = cfg.CASE_NAME
CASE_SHORT_NAME = cfg.CASE_SHORT_NAME
BENCHMARK_SHORT_NAME = cfg.BENCHMARK_SHORT_NAME
CASE_ID = cfg.CASE_ID
DEFAULT_OBS_DATA_PATH = cfg.DEFAULT_OBS_DATA_PATH
OBS_DATA_PATH = DEFAULT_OBS_DATA_PATH
LOG_FILENAME = cfg.LOG_FILENAME
DEFAULT_LOGGING_LEVEL = cfg.DEFAULT_LOGGING_LEVEL
DEFAULT_VERBOSITY = cfg.DEFAULT_VERBOSITY
DEFAULT_AGGREGATION_SCHEME = cfg.DEFAULT_AGGREGATION_SCHEME
AREA_RELATIVE_ERROR_AT_SCORE_50 = cfg.AREA_RELATIVE_ERROR_AT_SCORE_50

DEFAULT_OUTPUT_PATH_JSON = cfg.DEFAULT_OUTPUT_PATH_JSON
DEFAULT_SCORE_CARD_REPORT_PATH = cfg.DEFAULT_SCORE_CARD_REPORT_PATH
output_path_json = DEFAULT_OUTPUT_PATH_JSON
score_card_report_path = DEFAULT_SCORE_CARD_REPORT_PATH

PERIOD_TARGET_PATTERN = re.compile(r"^(H\d{3}|P\d{2})_([BPW]+)$")
KPI_GROUP_CATEGORIES = (
    ("B", "Building Damage"),
    ("S", "Burn Severity"),
    ("CC", "Canopy Cover Loss"),
    ("P", "Fire Perimeters"),
    ("W", "Weather Stations"),
)
STANDALONE_TARGETS = (
    ("B", "Building Damage"),
    ("S", "Burn Severity"),
    ("CC", "Canopy Cover Loss"),
    ("FP", "Fire Perimeters (all curated periods)"),
)
BINARY_KPI_SUFFIXES = (
    "Accuracy",
    "Precision",
    "Recall",
    "Specificity",
    "Negative Predictive Value",
    "F1 Score",
)
STATIC_KPI_NAMES = {
    **{
        f"FB001_BD{index:02d}": f"Binary Structure Loss {suffix}"
        for index, suffix in enumerate(BINARY_KPI_SUFFIXES, start=1)
    },
    **{
        f"FB001_SV{index:02d}": f"Binary High Severity {suffix}"
        for index, suffix in enumerate(BINARY_KPI_SUFFIXES, start=1)
    },
    **{
        f"FB001_CC{index:02d}": f"Binary High Canopy Cover Loss {suffix}"
        for index, suffix in enumerate(BINARY_KPI_SUFFIXES, start=1)
    },
    **{
        f"FB001_FP{index:02d}": name
        for index, name in enumerate(
            (
                *("Average Jaccard Index",) * 4,
                *("Minimum Jaccard Index",) * 4,
                *("Maximum Jaccard Index",) * 4,
                *("Average Dice-Sorensen Index",) * 4,
                *("Minimum Dice-Sorensen Index",) * 4,
                *("Maximum Dice-Sorensen Index",) * 4,
                *("Final Burn Area Bias",) * 4,
                *("Burn Area RMSE",) * 4,
            ),
            start=1,
        )
    },
}


# ---------------------------
# Requirement checks and run associated benchmarks
# ---------------------------
def req_generic(
    model_dataset: File,
    obs_dataset: File,
    list_benchmarks: list,
    required_datasets: dict,
    ctx: dict,
    req_name: str,
):
    ft.logger.info("Check Requirement %s", req_name)
    bench_output = {}
    if not list_benchmarks:
        ft.logger.info("Empty list of benchmarks for this requirement. Skip Requirement")
        return bench_output

    # Check requirement
    req_ok, miss = fs.validate_h5_requirement(model_dataset, required_datasets)

    # run benchmarks
    if req_ok:
        ft.logger.info("Requirement %s valid", req_name)
        for bench_id in list_benchmarks:
            ft.logger.info(f"Run Benchmark {bench_id}")
            bench_output[bench_id] = BENCHMARK_FUNCTIONS[bench_id](model_dataset, obs_dataset, ctx)
    else:
        ft.logger.warning(
            "Requirement %s not satisfied. All related benchmarks ignored. Missing item(s): %s",
            req_name,
            miss,
        )

    return bench_output


def req_wx_station(
    model_dataset: File,
    obs_dataset: File,
    list_benchmarks: list,
    required_datasets: dict,
    ctx: dict,
    req_name: str,
):
    ft.logger.info("Check Requirement %s", req_name)
    bench_output = {}
    if not list_benchmarks:
        ft.logger.info("No benchmark to run for Requirement %s", req_name)
        return bench_output

    # Check requirement
    periods = _wx_requirement_periods(list_benchmarks)
    selected_stations = _weather_requirement_selected_stations(
        obs_dataset,
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
        _validate_selected_tso_model_heights(
            model_dataset,
            obs_dataset,
            list_benchmarks,
            ctx,
        )
        for bench_id in list_benchmarks:
            ft.logger.info(f"Run Benchmark {bench_id}")
            benchmark_result = BENCHMARK_FUNCTIONS[bench_id](model_dataset, obs_dataset, ctx)
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
        _log_missing_wx_station_requirements(req_name, required_datasets["variable"], miss)

    return bench_output


def _wx_requirement_periods(list_benchmarks: list[str]) -> list[tuple[datetime, datetime]]:
    periods = []
    for bench_id in list_benchmarks:
        period = getattr(BENCHMARK_FUNCTIONS[bench_id], "keywords", {}).get("period")
        if period is not None and period not in periods:
            periods.append(period)
    return periods


def _log_missing_wx_station_requirements(req_name: str, variable_name: str, miss) -> None:
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


def _select_weather_stations(
    obs_dataset: File,
    variable: str,
    period: tuple[datetime, datetime],
    station_set: fs.WeatherStationSet,
    ctx: dict | None = None,
) -> dict[str, list[dict]]:
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
        if fs.station_set_includes(station_set, confidence):
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
            "Weather station included: station=%s variable=%s period=%s/%s station_set=%s " "confidence=%d",
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


def _validate_selected_weather_confidence(
    obs_dataset: File,
    selected_benchmarks: list[str],
    ctx: dict,
) -> None:
    selections = _selected_weather_specs(selected_benchmarks)

    for variable, period, station_set in selections:
        _select_weather_stations(obs_dataset, variable, period, station_set, ctx)

    if selections:
        ft.logger.info(
            "Validated observational sensor-height confidence for %d weather selection(s).",
            len(selections),
        )


def _selected_weather_specs(
    selected_benchmarks: list[str],
) -> set[tuple[str, tuple[datetime, datetime], fs.WeatherStationSet]]:
    selections = set()
    for bench_id in selected_benchmarks:
        benchmark = BENCHMARK_FUNCTIONS.get(bench_id)
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


def _weather_requirement_selected_stations(
    obs_dataset: File,
    selected_benchmarks: list[str],
    ctx: dict,
) -> set[str] | None:
    selections = _selected_weather_specs(selected_benchmarks)
    if not selections:
        return None

    selected_stations = set()
    for variable, period, station_set in selections:
        selection = _select_weather_stations(
            obs_dataset,
            variable,
            period,
            station_set,
            ctx,
        )
        selected_stations.update(item["station"] for item in selection["included"])
    return selected_stations


def _validate_selected_tso_model_heights(
    model_dataset: File,
    obs_dataset: File,
    selected_benchmarks: list[str],
    ctx: dict,
) -> None:
    for variable, period, station_set in _selected_weather_specs(selected_benchmarks):
        if station_set is fs.WeatherStationSet.TSO:
            _model_height_compatible_selection(
                model_dataset,
                obs_dataset,
                variable,
                period,
                station_set,
                ctx,
            )


def _model_height_compatible_selection(
    model_dataset: File,
    obs_dataset: File,
    variable: str,
    period: tuple[datetime, datetime],
    station_set: fs.WeatherStationSet,
    ctx: dict,
) -> dict[str, list[dict]]:
    observation_selection = _select_weather_stations(
        obs_dataset,
        variable,
        period,
        station_set,
        ctx,
    )
    if station_set is not fs.WeatherStationSet.TSO:
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


# ---------------------------
# Benchmarks
# ---------------------------
def _require_positive_norm_param_m(value_norm_param_m: float) -> float:
    if not np.isfinite(value_norm_param_m) or value_norm_param_m <= 0:
        raise ValueError(
            "Fire-area normalization parameter m must be positive; check the observed perimeter areas."
        )
    return value_norm_param_m


def fire_area_final_bias_norm_param_m(observed_areas) -> float:
    observed_areas = np.asarray(observed_areas, dtype=float)
    if observed_areas.size == 0:
        raise ValueError("Cannot calculate fire-area normalization parameter m without observed areas.")
    return _require_positive_norm_param_m(AREA_RELATIVE_ERROR_AT_SCORE_50 * float(observed_areas[-1]))


def fire_area_rmse_norm_param_m(observed_areas) -> float:
    observed_areas = np.asarray(observed_areas, dtype=float)
    if observed_areas.size == 0:
        raise ValueError("Cannot calculate fire-area normalization parameter m without observed areas.")
    observed_area_rms = float(np.sqrt(np.mean(np.square(observed_areas))))
    return _require_positive_norm_param_m(AREA_RELATIVE_ERROR_AT_SCORE_50 * observed_area_rms)


def bench_bd_generic(
    model_dataset: File,
    obs_dataset: File,
    ctx: dict,
    kpi_name_custom: str,
    func_cm_index: any,
):
    KPI_NAME = f"{kpi_name_custom}"
    KPI_NORM_PARAM_A = 0
    KPI_NORM_PARAM_B = 1
    CTX_KEY_OBS = ("agg_bin", "building_damage", "obs")
    CTX_KEY_MODEL = ("agg_bin", "building_damage", "model")

    binary_bd_obs = fm.ctx_get_or_compute(
        CTX_SPEC, ctx, CTX_KEY_OBS, aggregate_building_damage_binary, obs_dataset
    )
    binary_bd_model = fm.ctx_get_or_compute(
        CTX_SPEC, ctx, CTX_KEY_MODEL, aggregate_building_damage_binary, model_dataset
    )

    # binary_bd_obs = aggregate_building_damage_binary(obs_dataset)
    # binary_bd_model = aggregate_building_damage_binary(model_dataset)

    rslt = func_cm_index(fm.confusion_matrix.binary_cm(binary_bd_obs, binary_bd_model))
    ft.logger.info("%s: %f", KPI_NAME, rslt)
    return {
        f"{KPI_NAME}": rslt,
        "Score": fm.kpi_norm_bounded_linear(rslt, KPI_NORM_PARAM_A, KPI_NORM_PARAM_B),
    }


def bench_sv_generic(
    model_dataset: File,
    obs_dataset: File,
    ctx: dict,
    kpi_name_custom: str,
    func_cm_index: any,
):
    KPI_NAME = f"{kpi_name_custom}"
    KPI_NORM_PARAM_A = 0
    KPI_NORM_PARAM_B = 1
    CTX_KEY_OBS = ("agg_bin", "mtbs_severity", "obs")
    CTX_KEY_MODEL = ("agg_bin", "mtbs_severity", "model")

    binary_sv_obs = fm.ctx_get_or_compute(
        CTX_SPEC, ctx, CTX_KEY_OBS, aggregate_high_severity_binary, obs_dataset
    )
    binary_sv_model = fm.ctx_get_or_compute(
        CTX_SPEC, ctx, CTX_KEY_MODEL, aggregate_high_severity_binary, model_dataset
    )

    rslt = func_cm_index(fm.confusion_matrix.binary_cm(binary_sv_obs, binary_sv_model))
    ft.logger.info("%s: %f", KPI_NAME, rslt)
    return {
        f"{KPI_NAME}": rslt,
        "Score": fm.kpi_norm_bounded_linear(rslt, KPI_NORM_PARAM_A, KPI_NORM_PARAM_B),
    }


def bench_fp_generic_area_final_bias(
    model_dataset: File,
    obs_dataset: File,
    ctx: dict,
    period_name: str,
    list_perims: list[str],
):
    KPI_NAME = f"Final Burn Area Bias"
    EPSG_PROJ = 3310

    area_obs = area_from_list(obs_dataset, [list_perims[-1]], EPSG_PROJ).to("acre")
    area_model = area_from_list(model_dataset, [list_perims[-1]], EPSG_PROJ).to("acre")
    rslt = fm.stats.bias(area_model.magnitude, area_obs.magnitude)
    value_norm_param_m = fire_area_final_bias_norm_param_m(area_obs.magnitude)

    ft.logger.info("%s: %f", KPI_NAME, rslt)
    ft.logger.info("%s normalization parameter m: %f acres", KPI_NAME, value_norm_param_m)
    return {
        f"{KPI_NAME} {period_name}": rslt,
        "Score": fm.kpi_norm_symmetric_open_exponential(rslt, value_norm_param_m),
    }


def bench_fp_generic_area(
    model_dataset: File,
    obs_dataset: File,
    ctx: dict,
    kpi_name_custom: str,
    period_name: str,
    list_perims: list[str],
    func: any,
):
    EPSG_PROJ = 3310

    area_obs = area_from_list(obs_dataset, list_perims, EPSG_PROJ).to("acre")
    area_model = area_from_list(model_dataset, list_perims, EPSG_PROJ).to("acre")
    rslt = func(area_model.magnitude, area_obs.magnitude)
    value_norm_param_m = fire_area_rmse_norm_param_m(area_obs.magnitude)

    ft.logger.info("%s: %f", kpi_name_custom, rslt)
    ft.logger.info("%s normalization parameter m: %f acres", kpi_name_custom, value_norm_param_m)
    return {
        f"{kpi_name_custom} {period_name}": rslt,
        "Score": fm.kpi_norm_symmetric_open_exponential(rslt, value_norm_param_m),
    }


def bench_fp_generic_index(
    model_dataset: File,
    obs_dataset: File,
    ctx: dict,
    kpi_name_custom: str,
    period_name: str,
    list_perims: list[str],
    func_index: any,
    func_index_rslt_agg: any,
):
    KPI_NAME = f"{kpi_name_custom} Index"
    KPI_NORM_PARAM_A = 0
    KPI_NORM_PARAM_B = 1

    rslt = float(
        func_index_rslt_agg(
            func_index(
                model_dataset,
                obs_dataset,
                list_perims,
                projection="EPSG:5070",
            )
        )
    )
    ft.logger.info("%s: %f", KPI_NAME, rslt)
    return {
        f"{KPI_NAME} {period_name}": rslt,
        "Score": fm.kpi_norm_bounded_linear(rslt, KPI_NORM_PARAM_A, KPI_NORM_PARAM_B),
    }


def bench_cc_generic_index(
    model_dataset: File,
    obs_dataset: File,
    ctx: dict,
    kpi_name_custom: str,
    func_cm_index: any,
):
    KPI_NAME = f"{kpi_name_custom}"
    KPI_NORM_PARAM_A = 0
    KPI_NORM_PARAM_B = 1

    ctx_key_mask = ("mask", "landfire_canopy", "all")

    landfire_mask_valid = fm.ctx_get_or_compute(
        CTX_SPEC,
        ctx,
        ctx_key_mask,
        mask_landfire_canopy,
        obs_dataset,
        f"/{fs.SPATIAL_2D}/ravg_cc",
        [
            f"/{fs.SPATIAL_2D}/Caldor_CH/canopy_height",
            f"/{fs.SPATIAL_2D}/Caldor_CBH/canopy_height_bottom",
            f"/{fs.SPATIAL_2D}/Caldor_CBD/canopy_density_bulk",
        ],
    )

    ravg_cc_obs = apply_high_ravg_cc_mask(obs_dataset, landfire_mask_valid)
    ravg_cc_model = apply_high_ravg_cc_mask(model_dataset, landfire_mask_valid)

    rslt = func_cm_index(fm.confusion_matrix.binary_cm(ravg_cc_obs, ravg_cc_model))

    ft.logger.info("%s: %f", KPI_NAME, rslt)
    return {
        f"{KPI_NAME}": rslt,
        "Score": fm.kpi_norm_bounded_linear(rslt, KPI_NORM_PARAM_A, KPI_NORM_PARAM_B),
    }


def bench_wx_generic_index(
    model_dataset: File,
    obs_dataset: File,
    ctx: dict,
    kpi_name_custom: str,
    period: tuple[datetime, datetime],
    wx_variable_name: str,
    common_unit: str,
    metric_func: any,
    stat_func: any,
    value_norm_param_m: float,
    station_set: fs.WeatherStationSet,
):
    PENALTY_VALUE = -1e6
    metric_rslt = []
    selection = _model_height_compatible_selection(
        model_dataset,
        obs_dataset,
        wx_variable_name,
        period,
        station_set,
        ctx,
    )
    if not selection["included"]:
        ft.logger.warning(
            "Ignoring weather KPI %s: no stations are eligible for %s.",
            kpi_name_custom,
            station_set.value,
        )
        return None

    for station_info in selection["included"]:
        station = station_info["station"]
        station_path = f"{fs.TIME_SERIES}/{station}"
        data_path = f"{station_path}/{wx_variable_name}"
        mask_obs = get_mask_from_period(obs_dataset, station_path, period)
        mask_model = get_mask_from_period(model_dataset, station_path, period)
        assert np.sum(mask_obs) == np.sum(mask_model), "time vector size invalid"

        var_obs = (
            fs.read_quantity_from_fb_dataset(data_path, obs_dataset).to(common_unit).magnitude[mask_obs]
        )
        var_model = (
            fs.read_quantity_from_fb_dataset(data_path, model_dataset).to(common_unit).magnitude[mask_model]
        )

        # replace nan values in model by unrealistic value to severely penalize nans in model
        if any(np.isnan(var_model)):
            ft.logger.warning(
                "Nans found in model dataset for station %s and variable %s. Nans replaced by unrealistic value.",
                station,
                wx_variable_name,
            )
            var_model[np.isnan(var_model)] = PENALTY_VALUE

        metric_rslt.append(metric_func(var_model, var_obs))

    ft.logger.info("Nb processed stations: %s", len(selection["included"]))
    rslt = stat_func(metric_rslt)
    ft.logger.info("%s: %f", kpi_name_custom, rslt)
    return {
        f"{kpi_name_custom}": rslt,
        "Score": fm.kpi_norm_symmetric_open_exponential(rslt, value_norm_param_m),
    }


# ---------------------------
# Requirement registry
# ---------------------------

REQUIREMENTS = {
    "R01": {
        "main": lambda model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx: req_generic(
            model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name="R01"
        ),
        "benchmarks": ["FB001_BD01", "FB001_BD02", "FB001_BD03", "FB001_BD04", "FB001_BD05", "FB001_BD06"],
        "required_datasets": {f"/{fs.POINTS}/building_damaged/building_damage": ["units"]},
    },
    "R02": {
        "main": lambda model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx: req_generic(
            model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name="R02"
        ),
        "benchmarks": ["FB001_SV01", "FB001_SV02", "FB001_SV03", "FB001_SV04", "FB001_SV05", "FB001_SV06"],
        "required_datasets": {
            f"/{fs.SPATIAL_2D}/Caldor_MTBS": ["crs"],
            f"/{fs.SPATIAL_2D}/Caldor_MTBS/fire_burn_severity": ["units", "_FillValue"],
            f"/{fs.SPATIAL_2D}/Caldor_MTBS/position_lat": ["units"],
            f"/{fs.SPATIAL_2D}/Caldor_MTBS/position_lon": ["units"],
        },
    },
    "R03": {
        "main": lambda model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx: req_generic(
            model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name="R03"
        ),
        "benchmarks": [
            "FB001_FP01",
            "FB001_FP05",
            "FB001_FP09",
            "FB001_FP13",
            "FB001_FP17",
            "FB001_FP21",
            "FB001_FP25",
            "FB001_FP29",
        ],
        "required_datasets": {
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-18T20:30-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-19T20:45-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-20T20:20-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-21T21:15-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-24T22:07-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-26T03:30-06:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-26T22:15-06:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-27T00:22-06:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-28T21:30-06:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-29T22:32-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-30T21:09-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-31T21:08-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-09-01T21:12-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-09-03T00:40-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-09-04T23:29-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-09-05T23:41-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-09-06T23:09-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-09-07T22:40-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-09-08T22:33-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-09-10T23:34-07:00": ["rel_path", "time"],
        },
    },
    "R04": {
        "main": lambda model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx: req_generic(
            model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name="R04"
        ),
        "benchmarks": [
            "FB001_FP02",
            "FB001_FP06",
            "FB001_FP10",
            "FB001_FP14",
            "FB001_FP18",
            "FB001_FP22",
            "FB001_FP26",
            "FB001_FP30",
        ],
        "required_datasets": {
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-20T20:20-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-21T21:15-07:00": ["rel_path", "time"],
        },
    },
    "R05": {
        "main": lambda model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx: req_generic(
            model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name="R05"
        ),
        "benchmarks": [
            "FB001_FP03",
            "FB001_FP07",
            "FB001_FP11",
            "FB001_FP15",
            "FB001_FP19",
            "FB001_FP23",
            "FB001_FP27",
            "FB001_FP31",
        ],
        "required_datasets": {
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-26T22:15-06:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-27T00:22-06:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-28T21:30-06:00": ["rel_path", "time"],
        },
    },
    "R06": {
        "main": lambda model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx: req_generic(
            model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name="R06"
        ),
        "benchmarks": [
            "FB001_FP04",
            "FB001_FP08",
            "FB001_FP12",
            "FB001_FP16",
            "FB001_FP20",
            "FB001_FP24",
            "FB001_FP28",
            "FB001_FP32",
        ],
        "required_datasets": {
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-29T22:32-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-30T21:09-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-08-31T21:08-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-09-01T21:12-07:00": ["rel_path", "time"],
            f"/{fs.GEOPOLYGONS}/Caldor_2021-09-03T00:40-07:00": ["rel_path", "time"],
        },
    },
    "R07": {
        "main": lambda model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx: req_generic(
            model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name="R07"
        ),
        "benchmarks": [
            "FB001_CC01",
            "FB001_CC02",
            "FB001_CC03",
            "FB001_CC04",
            "FB001_CC05",
            "FB001_CC06",
        ],
        "required_datasets": {
            f"/{fs.SPATIAL_2D}/ravg_cc": ["crs"],
            f"/{fs.SPATIAL_2D}/ravg_cc/ravg_canopy_cover_loss": ["units", "_FillValue"],
            f"/{fs.SPATIAL_2D}/ravg_cc/position_lat": ["units"],
            f"/{fs.SPATIAL_2D}/ravg_cc/position_lon": ["units"],
        },
    },
    "R08": {
        "main": lambda model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx: req_wx_station(
            model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name="R08"
        ),
        "benchmarks": [],  # will be added in add_wx_benchmarks
        "required_datasets": {
            "station_pattern": "station_",
            "variable": "air_temperature",
        },
    },
    "R09": {
        "main": lambda model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx: req_wx_station(
            model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name="R09"
        ),
        "benchmarks": [],  # will be added in add_wx_benchmarks
        "required_datasets": {
            "station_pattern": "station_",
            "variable": "relative_humidity",
        },
    },
    "R10": {
        "main": lambda model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx: req_wx_station(
            model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name="R10"
        ),
        "benchmarks": [],  # will be added in add_wx_benchmarks
        "required_datasets": {
            "station_pattern": "station_",
            "variable": "wind_speed",
        },
    },
    "R11": {
        "main": lambda model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx: req_wx_station(
            model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name="R11"
        ),
        "benchmarks": [],  # will be added in add_wx_benchmarks
        "required_datasets": {
            "station_pattern": "station_",
            "variable": "wind_direction",
        },
    },
    "R12": {
        "main": lambda model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx: req_wx_station(
            model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name="R12"
        ),
        "benchmarks": [],  # will be added in add_wx_benchmarks
        "required_datasets": {
            "station_pattern": "station_",
            "variable": "fuel_moisture_content_10h",
        },
    },
}

LIST_PERIMETERS_W1 = cfg.CURATED_PERIMETERS["W1"]
LIST_PERIMETERS_W2 = cfg.CURATED_PERIMETERS["W2"]
LIST_PERIMETERS_W3 = cfg.CURATED_PERIMETERS["W3"]
LIST_PERIMETERS_W4 = cfg.CURATED_PERIMETERS["W4"]


BENCHMARK_FUNCTIONS = {
    "FB001_BD01": lambda model_dataset, obs_dataset, ctx: bench_bd_generic(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary Structure Loss Accuracy",
        fm.confusion_matrix.binary_accuracy,
    ),
    "FB001_BD02": lambda model_dataset, obs_dataset, ctx: bench_bd_generic(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary Structure Loss Precision",
        fm.confusion_matrix.binary_precision,
    ),
    "FB001_BD03": lambda model_dataset, obs_dataset, ctx: bench_bd_generic(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary Structure Loss Recall",
        fm.confusion_matrix.binary_recall_rate,
    ),
    "FB001_BD04": lambda model_dataset, obs_dataset, ctx: bench_bd_generic(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary Structure Loss Specificity",
        fm.confusion_matrix.binary_specificity,
    ),
    "FB001_BD05": lambda model_dataset, obs_dataset, ctx: bench_bd_generic(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary Structure Loss Negative Predictive Value",
        fm.confusion_matrix.binary_negative_predicted_value,
    ),
    "FB001_BD06": lambda model_dataset, obs_dataset, ctx: bench_bd_generic(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary Structure Loss F1 Score",
        fm.confusion_matrix.binary_f_score,
    ),
    "FB001_SV01": lambda model_dataset, obs_dataset, ctx: bench_sv_generic(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary High Severity Accuracy",
        fm.confusion_matrix.binary_accuracy,
    ),
    "FB001_SV02": lambda model_dataset, obs_dataset, ctx: bench_sv_generic(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary High Severity Precision",
        fm.confusion_matrix.binary_precision,
    ),
    "FB001_SV03": lambda model_dataset, obs_dataset, ctx: bench_sv_generic(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary High Severity Recall",
        fm.confusion_matrix.binary_recall_rate,
    ),
    "FB001_SV04": lambda model_dataset, obs_dataset, ctx: bench_sv_generic(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary High Severity Specificity",
        fm.confusion_matrix.binary_specificity,
    ),
    "FB001_SV05": lambda model_dataset, obs_dataset, ctx: bench_sv_generic(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary High Severity Negative Predictive Value",
        fm.confusion_matrix.binary_negative_predicted_value,
    ),
    "FB001_SV06": lambda model_dataset, obs_dataset, ctx: bench_sv_generic(
        model_dataset, obs_dataset, ctx, "Binary High Severity F1 Score", fm.confusion_matrix.binary_f_score
    ),
    "FB001_FP01": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Average Jaccard",
        "W1",
        LIST_PERIMETERS_W1,
        jaccard_from_list,
        np.mean,
    ),
    "FB001_FP02": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Average Jaccard",
        "W2",
        LIST_PERIMETERS_W2,
        jaccard_from_list,
        np.mean,
    ),
    "FB001_FP03": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Average Jaccard",
        "W3",
        LIST_PERIMETERS_W3,
        jaccard_from_list,
        np.mean,
    ),
    "FB001_FP04": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Average Jaccard",
        "W4",
        LIST_PERIMETERS_W4,
        jaccard_from_list,
        np.mean,
    ),
    "FB001_FP05": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Minimum Jaccard",
        "W1",
        LIST_PERIMETERS_W1,
        jaccard_from_list,
        np.min,
    ),
    "FB001_FP06": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Minimum Jaccard",
        "W2",
        LIST_PERIMETERS_W2,
        jaccard_from_list,
        np.min,
    ),
    "FB001_FP07": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Minimum Jaccard",
        "W3",
        LIST_PERIMETERS_W3,
        jaccard_from_list,
        np.min,
    ),
    "FB001_FP08": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Minimum Jaccard",
        "W4",
        LIST_PERIMETERS_W4,
        jaccard_from_list,
        np.min,
    ),
    "FB001_FP09": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Maximum Jaccard",
        "W1",
        LIST_PERIMETERS_W1,
        jaccard_from_list,
        np.max,
    ),
    "FB001_FP10": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Maximum Jaccard",
        "W2",
        LIST_PERIMETERS_W2,
        jaccard_from_list,
        np.max,
    ),
    "FB001_FP11": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Maximum Jaccard",
        "W3",
        LIST_PERIMETERS_W3,
        jaccard_from_list,
        np.max,
    ),
    "FB001_FP12": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Maximum Jaccard",
        "W4",
        LIST_PERIMETERS_W4,
        jaccard_from_list,
        np.max,
    ),
    "FB001_FP13": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Average Dice-Sorensen",
        "W1",
        LIST_PERIMETERS_W1,
        sorensen_dice_from_list,
        np.mean,
    ),
    "FB001_FP14": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Average Dice-Sorensen",
        "W2",
        LIST_PERIMETERS_W2,
        sorensen_dice_from_list,
        np.mean,
    ),
    "FB001_FP15": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Average Dice-Sorensen",
        "W3",
        LIST_PERIMETERS_W3,
        sorensen_dice_from_list,
        np.mean,
    ),
    "FB001_FP16": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Average Dice-Sorensen",
        "W4",
        LIST_PERIMETERS_W4,
        sorensen_dice_from_list,
        np.mean,
    ),
    "FB001_FP17": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Minimum Dice-Sorensen",
        "W1",
        LIST_PERIMETERS_W1,
        sorensen_dice_from_list,
        np.min,
    ),
    "FB001_FP18": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Minimum Dice-Sorensen",
        "W2",
        LIST_PERIMETERS_W2,
        sorensen_dice_from_list,
        np.min,
    ),
    "FB001_FP19": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Minimum Dice-Sorensen",
        "W3",
        LIST_PERIMETERS_W3,
        sorensen_dice_from_list,
        np.min,
    ),
    "FB001_FP20": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Minimum Dice-Sorensen",
        "W4",
        LIST_PERIMETERS_W4,
        sorensen_dice_from_list,
        np.min,
    ),
    "FB001_FP21": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Maximum Dice-Sorensen",
        "W1",
        LIST_PERIMETERS_W1,
        sorensen_dice_from_list,
        np.max,
    ),
    "FB001_FP22": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Maximum Dice-Sorensen",
        "W2",
        LIST_PERIMETERS_W2,
        sorensen_dice_from_list,
        np.max,
    ),
    "FB001_FP23": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Maximum Dice-Sorensen",
        "W3",
        LIST_PERIMETERS_W3,
        sorensen_dice_from_list,
        np.max,
    ),
    "FB001_FP24": lambda model_dataset, obs_dataset, ctx: bench_fp_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Maximum Dice-Sorensen",
        "W4",
        LIST_PERIMETERS_W4,
        sorensen_dice_from_list,
        np.max,
    ),
    "FB001_FP25": partial(
        bench_fp_generic_area_final_bias,
        period_name="W1",
        list_perims=LIST_PERIMETERS_W1,
    ),
    "FB001_FP26": partial(
        bench_fp_generic_area_final_bias,
        period_name="W2",
        list_perims=LIST_PERIMETERS_W2,
    ),
    "FB001_FP27": partial(
        bench_fp_generic_area_final_bias,
        period_name="W3",
        list_perims=LIST_PERIMETERS_W3,
    ),
    "FB001_FP28": partial(
        bench_fp_generic_area_final_bias,
        period_name="W4",
        list_perims=LIST_PERIMETERS_W4,
    ),
    "FB001_FP29": partial(
        bench_fp_generic_area,
        kpi_name_custom="Burn Area RMSE",
        period_name="W1",
        list_perims=LIST_PERIMETERS_W1,
        func=fm.stats.rmse,
    ),
    "FB001_FP30": partial(
        bench_fp_generic_area,
        kpi_name_custom="Burn Area RMSE",
        period_name="W2",
        list_perims=LIST_PERIMETERS_W2,
        func=fm.stats.rmse,
    ),
    "FB001_FP31": partial(
        bench_fp_generic_area,
        kpi_name_custom="Burn Area RMSE",
        period_name="W3",
        list_perims=LIST_PERIMETERS_W3,
        func=fm.stats.rmse,
    ),
    "FB001_FP32": partial(
        bench_fp_generic_area,
        kpi_name_custom="Burn Area RMSE",
        period_name="W4",
        list_perims=LIST_PERIMETERS_W4,
        func=fm.stats.rmse,
    ),
    "FB001_CC01": lambda model_dataset, obs_dataset, ctx: bench_cc_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary High Canopy Cover Loss Accuracy",
        fm.confusion_matrix.binary_accuracy,
    ),
    "FB001_CC02": lambda model_dataset, obs_dataset, ctx: bench_cc_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary High Canopy Cover Loss Precision",
        fm.confusion_matrix.binary_precision,
    ),
    "FB001_CC03": lambda model_dataset, obs_dataset, ctx: bench_cc_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary High Canopy Cover Loss Recall",
        fm.confusion_matrix.binary_recall_rate,
    ),
    "FB001_CC04": lambda model_dataset, obs_dataset, ctx: bench_cc_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary High Canopy Cover Loss Specificity",
        fm.confusion_matrix.binary_specificity,
    ),
    "FB001_CC05": lambda model_dataset, obs_dataset, ctx: bench_cc_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary High Canopy Cover Loss Negative Predictive Value",
        fm.confusion_matrix.binary_negative_predicted_value,
    ),
    "FB001_CC06": lambda model_dataset, obs_dataset, ctx: bench_cc_generic_index(
        model_dataset,
        obs_dataset,
        ctx,
        "Binary High Canopy Cover Loss F1 Score",
        fm.confusion_matrix.binary_f_score,
    ),
}

GROUPS = {}
AGGREGATION = {}
WX_GROUP_BENCHMARKS = {}
WX_GROUPS_BY_PERIOD = {}
HRRR_FP_GROUP_BENCHMARKS = {}
FIRE_PERIMETER_GROUP_PERIMETERS = {}
_BASE_REQUIREMENTS = copy.deepcopy(REQUIREMENTS)
_BASE_BENCHMARK_FUNCTIONS = BENCHMARK_FUNCTIONS.copy()

# ---------------------------
# Utilities
# ---------------------------

TZ_REF = cfg.TZ_REF
CURATED_VALIDATION_WINDOWS = cfg.CURATED_VALIDATION_WINDOWS
HRRR_VALIDATION_WINDOWS = cfg.HRRR_VALIDATION_WINDOWS
WH_PERIODS = cfg.HRRR_PERIODS
WH_PERIMETERS = cfg.HRRR_PERIMETERS

W1_PERIOD = cfg.CURATED_PERIODS["W1"]
W2_PERIOD = cfg.CURATED_PERIODS["W2"]
W3_PERIOD = cfg.CURATED_PERIODS["W3"]
W4_PERIOD = cfg.CURATED_PERIODS["W4"]

# list of all valid context dict structured key
CTX_SPEC: dict[fm.CTXKey, str] = cfg.CTX_SPEC


def add_wx_benchmarks():
    metric_funcs = {
        "standard": {"MAE": fm.stats.mae, "RMSE": fm.stats.rmse, "Bias": fm.stats.bias},
        "wind_direction": {"circular bias": fm.stats.circular_bias_deg},
    }
    summary_stats_func = {"min": np.nanmin, "mean": np.nanmean, "max": np.nanmax}
    bench_idx = 1

    for period_set in cfg.WX_PERIOD_SETS:
        for variable_spec in cfg.WX_VARIABLE_SPECS:
            for period_name, period in period_set["periods"].items():
                group_name = f"{variable_spec['group_label']} {period_name}"
                WX_GROUP_BENCHMARKS.setdefault(group_name, {})
                WX_GROUPS_BY_PERIOD.setdefault(period_name, []).append(group_name)
                for metric_name, metric_func in metric_funcs[variable_spec["metric_set"]].items():
                    for station_set_text, station_set, weight in cfg.WX_STATION_SET_OPTIONS:
                        for func_name, stat_func in summary_stats_func.items():
                            bench_id = f"FB001_WX{bench_idx:03d}"
                            bench_name = (
                                f"{variable_spec['label']} {metric_name} {func_name} "
                                f"{period_name} {station_set_text}"
                            )

                            BENCHMARK_FUNCTIONS[bench_id] = partial(
                                bench_wx_generic_index,
                                kpi_name_custom=bench_name,
                                period=period,
                                wx_variable_name=variable_spec["variable"],
                                common_unit=variable_spec["common_unit"],
                                metric_func=metric_func,
                                stat_func=stat_func,
                                value_norm_param_m=variable_spec["norm_m"],
                                station_set=station_set,
                            )
                            WX_GROUP_BENCHMARKS[group_name][bench_id] = weight
                            ft.logger.debug("Benchmark %s with name %s added", bench_id, bench_name)
                            REQUIREMENTS[variable_spec["requirement"]]["benchmarks"].append(bench_id)
                            bench_idx += 1


def add_hrrr_fire_perimeter_benchmarks():
    bench_idx = 1
    index_metrics = (
        ("Average Jaccard", jaccard_from_list, np.mean, 2),
        ("Minimum Jaccard", jaccard_from_list, np.min, 1),
        ("Maximum Jaccard", jaccard_from_list, np.max, 0),
        ("Average Dice-Sorensen", sorensen_dice_from_list, np.mean, 0),
        ("Minimum Dice-Sorensen", sorensen_dice_from_list, np.min, 0),
        ("Maximum Dice-Sorensen", sorensen_dice_from_list, np.max, 0),
    )

    for period_name, perimeters in cfg.HRRR_PERIMETERS.items():
        period_number = period_name.removeprefix("WH")
        group_name = f"FP_H{period_number}"
        requirement_name = f"R_FP_H{period_number}"
        HRRR_FP_GROUP_BENCHMARKS[group_name] = {}
        FIRE_PERIMETER_GROUP_PERIMETERS[group_name] = list(perimeters)
        REQUIREMENTS[requirement_name] = {
            "main": lambda model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name=requirement_name: req_generic(
                model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name=req_name
            ),
            "benchmarks": [],
            "required_datasets": {perimeter: ["rel_path", "time"] for perimeter in perimeters},
        }

        for metric_name, metric_func, agg_func, weight in index_metrics:
            bench_id = f"FB001_FPH{bench_idx:03d}"
            BENCHMARK_FUNCTIONS[bench_id] = partial(
                bench_fp_generic_index,
                kpi_name_custom=metric_name,
                period_name=period_name,
                list_perims=perimeters,
                func_index=metric_func,
                func_index_rslt_agg=agg_func,
            )
            HRRR_FP_GROUP_BENCHMARKS[group_name][bench_id] = weight
            REQUIREMENTS[requirement_name]["benchmarks"].append(bench_id)
            bench_idx += 1

        bench_id = f"FB001_FPH{bench_idx:03d}"
        BENCHMARK_FUNCTIONS[bench_id] = partial(
            bench_fp_generic_area_final_bias,
            period_name=period_name,
            list_perims=perimeters,
        )
        HRRR_FP_GROUP_BENCHMARKS[group_name][bench_id] = 1
        REQUIREMENTS[requirement_name]["benchmarks"].append(bench_id)
        bench_idx += 1

        bench_id = f"FB001_FPH{bench_idx:03d}"
        BENCHMARK_FUNCTIONS[bench_id] = partial(
            bench_fp_generic_area,
            kpi_name_custom="Burn Area RMSE",
            period_name=period_name,
            list_perims=perimeters,
            func=fm.stats.rmse,
        )
        HRRR_FP_GROUP_BENCHMARKS[group_name][bench_id] = 1
        REQUIREMENTS[requirement_name]["benchmarks"].append(bench_id)
        bench_idx += 1


def create_benchmark_groups():
    new_grp_benchs = {f"FB001_BD{i:02d}": 1 for i in range(1, 7)}
    GROUPS["Building Damage"] = {"weight": 1, "benchmarks": new_grp_benchs.copy()}

    new_grp_benchs = {f"FB001_SV{i:02d}": 1 for i in range(1, 7)}
    GROUPS["Burn Severity"] = {"weight": 1, "benchmarks": new_grp_benchs.copy()}

    new_grp_benchs = {f"FB001_CC{i:02d}": 1 for i in range(1, 7)}
    GROUPS["Canopy Cover Loss"] = {"weight": 1, "benchmarks": new_grp_benchs.copy()}

    GROUPS["Fire Perimeter W1"] = {
        "weight": 1,
        "benchmarks": {
            "FB001_FP01": 2,
            "FB001_FP05": 1,
            "FB001_FP09": 0,
            "FB001_FP13": 0,
            "FB001_FP17": 0,
            "FB001_FP21": 0,
            "FB001_FP25": 1,
            "FB001_FP29": 1,
        },
    }
    FIRE_PERIMETER_GROUP_PERIMETERS["Fire Perimeter W1"] = list(LIST_PERIMETERS_W1)
    GROUPS["Fire Perimeter W2"] = {
        "weight": 1,
        "benchmarks": {
            "FB001_FP02": 2,
            "FB001_FP06": 1,
            "FB001_FP10": 0,
            "FB001_FP14": 0,
            "FB001_FP18": 0,
            "FB001_FP22": 0,
            "FB001_FP26": 1,
            "FB001_FP30": 1,
        },
    }
    FIRE_PERIMETER_GROUP_PERIMETERS["Fire Perimeter W2"] = list(LIST_PERIMETERS_W2)
    GROUPS["Fire Perimeter W3"] = {
        "weight": 1,
        "benchmarks": {
            "FB001_FP03": 2,
            "FB001_FP07": 1,
            "FB001_FP11": 0,
            "FB001_FP15": 0,
            "FB001_FP19": 0,
            "FB001_FP23": 0,
            "FB001_FP27": 1,
            "FB001_FP31": 1,
        },
    }
    FIRE_PERIMETER_GROUP_PERIMETERS["Fire Perimeter W3"] = list(LIST_PERIMETERS_W3)
    GROUPS["Fire Perimeter W4"] = {
        "weight": 1,
        "benchmarks": {
            "FB001_FP04": 2,
            "FB001_FP08": 1,
            "FB001_FP12": 0,
            "FB001_FP16": 0,
            "FB001_FP20": 0,
            "FB001_FP24": 0,
            "FB001_FP28": 1,
            "FB001_FP32": 1,
        },
    }
    FIRE_PERIMETER_GROUP_PERIMETERS["Fire Perimeter W4"] = list(LIST_PERIMETERS_W4)

    for group_name, benchmark_weights in WX_GROUP_BENCHMARKS.items():
        GROUPS[group_name] = {"weight": 1, "benchmarks": benchmark_weights.copy()}

    for group_name, benchmark_weights in HRRR_FP_GROUP_BENCHMARKS.items():
        GROUPS[group_name] = {"weight": 1, "benchmarks": benchmark_weights.copy()}


def _copy_groups(group_names: list[str]) -> dict:
    return {group_name: GROUPS[group_name].copy() for group_name in group_names}


def _weather_group_names(period_name: str) -> list[str]:
    return WX_GROUPS_BY_PERIOD[period_name]


def _weather_period_aggregation(period_name: str) -> dict:
    return _copy_groups(_weather_group_names(period_name))


def _parse_benchmark_target(benchmark_target: str) -> tuple[str, list[str]]:
    target = str(benchmark_target).strip().upper()
    parts = target.split("_")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid benchmark target '{benchmark_target}'. Expected format like H013_B, H013_P, H013_W, or P02_P."
        )

    period_selector, analysis_flags = parts
    if not analysis_flags:
        raise ValueError(f"Invalid benchmark target '{benchmark_target}'. Missing analysis flags.")

    unsupported_flags = sorted(set(analysis_flags) - {"B", "P", "W"})
    if unsupported_flags:
        raise ValueError(
            f"Invalid benchmark target '{benchmark_target}'. Unsupported analysis flags: "
            f"{', '.join(unsupported_flags)}."
        )

    group_names = []
    canonical_flags = "".join(flag for flag in "BPW" if flag in analysis_flags)
    if period_selector.startswith("H"):
        period_number_text = period_selector.removeprefix("H")
        if not period_number_text.isdigit():
            raise ValueError(
                f"Invalid benchmark target '{benchmark_target}'. HRRR period must look like H013."
            )
        period_number = int(period_number_text)
        period_name = f"WH{period_number}"
        if period_name not in cfg.HRRR_PERIODS:
            raise ValueError(f"Unknown HRRR period selector '{period_selector}'.")
        canonical_period = f"H{period_number:03d}"
        if "B" in canonical_flags:
            group_names.append("Building Damage")
        if "P" in canonical_flags:
            group_names.append(f"FP_H{period_number}")
        if "W" in canonical_flags:
            group_names.extend(_weather_group_names(period_name))
    elif period_selector.startswith("P"):
        period_number_text = period_selector.removeprefix("P")
        if not period_number_text.isdigit():
            raise ValueError(
                f"Invalid benchmark target '{benchmark_target}'. Curated period must look like P02."
            )
        period_number = int(period_number_text)
        period_name = f"W{period_number}"
        if period_name not in cfg.CURATED_PERIODS:
            raise ValueError(f"Unknown curated period selector '{period_selector}'.")
        canonical_period = f"P{period_number:02d}"
        if "B" in canonical_flags:
            group_names.append("Building Damage")
        if "P" in canonical_flags:
            group_names.append(f"Fire Perimeter W{period_number}")
        if "W" in canonical_flags:
            group_names.extend(_weather_group_names(period_name))
    else:
        raise ValueError(
            f"Invalid benchmark target '{benchmark_target}'. Period selector must start with H or P."
        )

    return f"{canonical_period}_{canonical_flags}", group_names


def normalize_benchmark_target(benchmark_target: str) -> str:
    build_registries()
    return resolve_benchmark_target(benchmark_target)


def _target_period(period_selector: str) -> tuple[datetime, datetime]:
    if period_selector.startswith("H"):
        period_name = f"WH{int(period_selector.removeprefix('H'))}"
        return cfg.HRRR_PERIODS[period_name]
    if period_selector.startswith("P"):
        period_name = f"W{int(period_selector.removeprefix('P'))}"
        return cfg.CURATED_PERIODS[period_name]
    raise ValueError(f"Unknown period selector '{period_selector}'.")


def _perimeter_time_from_path(perimeter_path: str) -> str:
    return perimeter_path.rsplit("_", maxsplit=1)[-1]


def _benchmark_kpi_name(bench_id: str) -> str:
    if bench_id in STATIC_KPI_NAMES:
        return STATIC_KPI_NAMES[bench_id]
    benchmark = BENCHMARK_FUNCTIONS[bench_id]
    keywords = getattr(benchmark, "keywords", {}) or {}
    if getattr(benchmark, "func", None) is bench_fp_generic_index:
        return f"{keywords['kpi_name_custom']} Index"
    if getattr(benchmark, "func", None) is bench_fp_generic_area_final_bias:
        return "Final Burn Area Bias"
    return keywords.get("kpi_name_custom", _benchmark_debug_label(bench_id))


def _fire_area_norm_params(obs_data: Path, perimeter_paths: list[str]) -> dict[str, float]:
    if not perimeter_paths or not obs_data.is_file():
        return {}

    with File(obs_data, "r") as obs_dataset:
        observed_areas = area_from_list(obs_dataset, perimeter_paths, 3310).to("acre").magnitude
    return {
        "final_bias": fire_area_final_bias_norm_param_m(observed_areas),
        "rmse": fire_area_rmse_norm_param_m(observed_areas),
    }


def _benchmark_norm_param_m(benchmark, fire_area_norm_params: dict[str, float]):
    benchmark_func = getattr(benchmark, "func", None)
    if benchmark_func is bench_fp_generic_area_final_bias:
        return fire_area_norm_params.get("final_bias")
    if benchmark_func is bench_fp_generic_area:
        return fire_area_norm_params.get("rmse")
    keywords = getattr(benchmark, "keywords", {}) or {}
    return keywords.get("value_norm_param_m")


def _benchmark_norm_param_m_definition(benchmark) -> str | None:
    benchmark_func = getattr(benchmark, "func", None)
    if benchmark_func is bench_fp_generic_area_final_bias:
        return f"{AREA_RELATIVE_ERROR_AT_SCORE_50:.0%} of final observed area"
    if benchmark_func is bench_fp_generic_area:
        return f"{AREA_RELATIVE_ERROR_AT_SCORE_50:.0%} of RMS observed area"
    return None


def _weather_station_counts(obs_data: Path, period: tuple[datetime, datetime]) -> list[dict]:
    if not obs_data.is_file():
        return []

    weather_stations = []
    selection_context = {}
    with File(obs_data, "r") as obs_dataset:
        if fs.TIME_SERIES not in obs_dataset:
            return []

        for variable_spec in cfg.WX_VARIABLE_SPECS:
            variable = variable_spec["variable"]
            all_sources = _select_weather_stations(
                obs_dataset,
                variable,
                period,
                fs.WeatherStationSet.ALL_SOURCES,
                selection_context,
            )
            tso = _select_weather_stations(
                obs_dataset,
                variable,
                period,
                fs.WeatherStationSet.TSO,
                selection_context,
            )

            weather_stations.append(
                {
                    "variable": variable,
                    "label": variable_spec["label"],
                    "stations": len(all_sources["included"]),
                    "trusted_stations": len(tso["included"]),
                }
            )

    return weather_stations


def describe_available_targets(benchmark_target: str | None = None, obs_data: Path | None = None) -> dict:
    period_kpi_groups = dict(KPI_GROUP_CATEGORIES[index] for index in (0, 3, 4))

    if benchmark_target is not None:
        build_registries()
        canonical_target = resolve_benchmark_target(benchmark_target)
        period_target = PERIOD_TARGET_PATTERN.fullmatch(canonical_target)
        if period_target is not None:
            period_selector = period_target.group(1)
            start, end = _target_period(period_selector)
            period = {
                "target": period_selector,
                "start": start,
                "end": end,
            }
        else:
            period = None
        selected_groups = GROUPS if canonical_target == "0" else AGGREGATION[canonical_target]
        group_display_names = _target_group_display_names(canonical_target)
        kpi_groups = _target_kpi_groups(selected_groups)
        obs_data = obs_data or DEFAULT_OBS_DATA_PATH

        perimeters = []
        perimeter_paths_seen = set()
        kpis = []
        benchmarks_seen = set()
        for group_name, group_content in selected_groups.items():
            perimeter_paths = FIRE_PERIMETER_GROUP_PERIMETERS.get(group_name, [])
            fire_area_norm_params = _fire_area_norm_params(obs_data, perimeter_paths)
            for perimeter_path in perimeter_paths:
                if perimeter_path in perimeter_paths_seen:
                    continue
                perimeter_paths_seen.add(perimeter_path)
                perimeters.append(
                    {
                        "time": _perimeter_time_from_path(perimeter_path),
                        "path": perimeter_path,
                    }
                )
            for bench_id, weight in group_content["benchmarks"].items():
                if bench_id in benchmarks_seen:
                    continue
                benchmarks_seen.add(bench_id)
                benchmark = BENCHMARK_FUNCTIONS[bench_id]
                kpi = {
                    "id": bench_id,
                    "name": _benchmark_kpi_name(bench_id),
                    "group": group_display_names.get(group_name, group_name),
                    "weight": None if canonical_target == "0" else weight,
                    "value_norm_param_m": _benchmark_norm_param_m(benchmark, fire_area_norm_params),
                }
                norm_param_definition = _benchmark_norm_param_m_definition(benchmark)
                if norm_param_definition is not None:
                    kpi["value_norm_param_m_definition"] = norm_param_definition
                kpis.append(kpi)

        return {
            "target": canonical_target,
            "period": period,
            "aggregated": canonical_target != "0",
            "kpi_groups": kpi_groups,
            "perimeters": perimeters,
            "weather_stations": (
                _weather_station_counts(obs_data, (start, end))
                if "W" in kpi_groups and period is not None
                else []
            ),
            "kpis": kpis,
        }

    periods = []
    for period_name, (start, end) in cfg.HRRR_PERIODS.items():
        period_number = int(period_name.removeprefix("WH"))
        periods.append(
            {
                "target": f"H{period_number:03d}",
                "start": start,
                "end": end,
            }
        )
    for period_name, (start, end) in cfg.CURATED_PERIODS.items():
        period_number = int(period_name.removeprefix("W"))
        periods.append(
            {
                "target": f"P{period_number:02d}",
                "start": start,
                "end": end,
            }
        )

    return {
        "standalone_targets": dict(STANDALONE_TARGETS),
        "period_target_syntax": "PERIOD_FLAGS",
        "periods": periods,
        "kpi_groups": period_kpi_groups,
    }


def _group_category(group_name: str) -> tuple[str, str] | None:
    if group_name in {category[1] for category in KPI_GROUP_CATEGORIES[:3]}:
        return next(category for category in KPI_GROUP_CATEGORIES if category[1] == group_name)
    if group_name.startswith("FP_H") or group_name.startswith("Fire Perimeter W"):
        return "P", "Fire Perimeters"
    if group_name in WX_GROUP_BENCHMARKS:
        return "W", "Weather Stations"
    return None


def _target_kpi_groups(selected_groups: dict) -> dict[str, str]:
    selected_categories = {
        category for group_name in selected_groups if (category := _group_category(group_name)) is not None
    }
    return {
        flag: description
        for flag, description in KPI_GROUP_CATEGORIES
        if (flag, description) in selected_categories
    }


def _target_group_display_names(aggregation_scheme: str) -> dict[str, str]:
    selected_groups = GROUPS if aggregation_scheme == "0" else AGGREGATION.get(aggregation_scheme, {})
    return {
        group_name: category[1]
        for group_name in selected_groups
        if (category := _group_category(group_name)) is not None
    }


def resolve_benchmark_target(benchmark_target: str) -> str:
    raw_target = str(benchmark_target).strip()
    if raw_target == "0" or raw_target in AGGREGATION:
        return raw_target

    target = raw_target.upper()
    if target in AGGREGATION:
        return target

    canonical_target, group_names = _parse_benchmark_target(benchmark_target)
    AGGREGATION[canonical_target] = _copy_groups(group_names)
    return canonical_target


def create_aggregation_schemes():
    curated_period_names = list(cfg.CURATED_PERIODS.keys())
    hrrr_period_names = list(cfg.HRRR_PERIODS.keys())
    curated_weather_group_names = [
        group_name
        for period_name in curated_period_names
        for group_name in _weather_group_names(period_name)
    ]
    hrrr_weather_group_names = [
        group_name for period_name in hrrr_period_names for group_name in _weather_group_names(period_name)
    ]

    AGGREGATION["A"] = _copy_groups(
        [
            "Building Damage",
            "Burn Severity",
            "Canopy Cover Loss",
            "Fire Perimeter W1",
            "Fire Perimeter W2",
            "Fire Perimeter W3",
            "Fire Perimeter W4",
            *curated_weather_group_names,
        ]
    )
    AGGREGATION["B"] = {
        "Building Damage": GROUPS["Building Damage"].copy(),
    }
    AGGREGATION["S"] = {
        "Burn Severity": GROUPS["Burn Severity"].copy(),
    }
    AGGREGATION["CC"] = {
        "Canopy Cover Loss": GROUPS["Canopy Cover Loss"].copy(),
    }
    AGGREGATION["FP"] = _copy_groups([f"Fire Perimeter W{period_number}" for period_number in range(1, 5)])
    AGGREGATION["CDI"] = {
        "Building Damage": GROUPS["Building Damage"].copy(),
    }
    for i in range(2, 5):
        AGGREGATION[f"CDI"][f"Fire Perimeter W{i:1d}"] = GROUPS[f"Fire Perimeter W{i:1d}"].copy()

    for i in range(2, 5):
        AGGREGATION[f"CDI"][f"Air Temp W{i:1d}"] = GROUPS[f"Air Temp W{i:1d}"].copy()
        AGGREGATION[f"CDI"][f"RH W{i:1d}"] = GROUPS[f"RH W{i:1d}"].copy()
        AGGREGATION[f"CDI"][f"Wind Speed W{i:1d}"] = GROUPS[f"Wind Speed W{i:1d}"].copy()
        AGGREGATION[f"CDI"][f"Wind Direction W{i:1d}"] = GROUPS[f"Wind Direction W{i:1d}"].copy()
        AGGREGATION[f"CDI"][f"FMC 10h W{i:1d}"] = GROUPS[f"FMC 10h W{i:1d}"].copy()
        # Null weight for weather as input check only
        AGGREGATION[f"CDI"][f"Air Temp W{i:1d}"]["weight"] = 0
        AGGREGATION[f"CDI"][f"RH W{i:1d}"]["weight"] = 0
        AGGREGATION[f"CDI"][f"Wind Speed W{i:1d}"]["weight"] = 0
        AGGREGATION[f"CDI"][f"Wind Direction W{i:1d}"]["weight"] = 0
        AGGREGATION[f"CDI"][f"FMC 10h W{i:1d}"]["weight"] = 0
    # For demo
    AGGREGATION["BS3"] = {
        "Building Damage": {
            "weight": 2,
            "benchmarks": {
                "FB001_BD01": 1,
                "FB001_BD03": 1,
                "FB001_BD06": 2,
            },
        },
        "Burn Severity": {
            "weight": 1,
            "benchmarks": {
                "FB001_SV01": 1,
                "FB001_SV03": 1,
                "FB001_SV06": 2,
            },
        },
    }
    for period_name in curated_period_names:
        AGGREGATION[f"WX{period_name.removeprefix('W')}"] = _weather_period_aggregation(period_name)

    for period_name in hrrr_period_names:
        AGGREGATION[f"WX_{period_name}"] = _weather_period_aggregation(period_name)

    AGGREGATION["WX_WH_ALL"] = _copy_groups(hrrr_weather_group_names)
    for period_name in hrrr_period_names:
        period_number = period_name.removeprefix("WH")
        AGGREGATION[f"FP_H{period_number}"] = _copy_groups([f"FP_H{period_number}"])

    AGGREGATION[f"short_all"] = {}
    AGGREGATION[f"short_all"][f"Building Damage"] = GROUPS[f"Building Damage"].copy()
    AGGREGATION[f"short_all"][f"Canopy Cover Loss"] = GROUPS[f"Canopy Cover Loss"].copy()
    AGGREGATION[f"short_all"][f"Burn Severity"] = GROUPS[f"Burn Severity"].copy()
    for i in range(2, 5):
        AGGREGATION[f"short_all"][f"Air Temp W{i:1d}"] = GROUPS[f"Air Temp W{i:1d}"].copy()
        AGGREGATION[f"short_all"][f"RH W{i:1d}"] = GROUPS[f"RH W{i:1d}"].copy()
        AGGREGATION[f"short_all"][f"Wind Speed W{i:1d}"] = GROUPS[f"Wind Speed W{i:1d}"].copy()
        AGGREGATION[f"short_all"][f"Wind Direction W{i:1d}"] = GROUPS[f"Wind Direction W{i:1d}"].copy()
        AGGREGATION[f"short_all"][f"FMC 10h W{i:1d}"] = GROUPS[f"FMC 10h W{i:1d}"].copy()
        AGGREGATION[f"short_all"][f"Fire Perimeter W{i:1d}"] = GROUPS[f"Fire Perimeter W{i:1d}"].copy()

    AGGREGATION[f"WX_short"] = {}
    AGGREGATION[f"WX_short"][f"Building Damage"] = GROUPS[f"Building Damage"].copy()
    AGGREGATION[f"WX_short"][f"Canopy Cover Loss"] = GROUPS[f"Canopy Cover Loss"].copy()
    AGGREGATION[f"WX_short"][f"Burn Severity"] = GROUPS[f"Burn Severity"].copy()
    for i in range(2, 5):
        AGGREGATION[f"WX_short"][f"Air Temp W{i:1d}"] = GROUPS[f"Air Temp W{i:1d}"].copy()
        AGGREGATION[f"WX_short"][f"RH W{i:1d}"] = GROUPS[f"RH W{i:1d}"].copy()
        AGGREGATION[f"WX_short"][f"Wind Speed W{i:1d}"] = GROUPS[f"Wind Speed W{i:1d}"].copy()
        AGGREGATION[f"WX_short"][f"Wind Direction W{i:1d}"] = GROUPS[f"Wind Direction W{i:1d}"].copy()
        AGGREGATION[f"WX_short"][f"FMC 10h W{i:1d}"] = GROUPS[f"FMC 10h W{i:1d}"].copy()

    AGGREGATION["DEMO"] = _weather_period_aggregation("WH16")
    AGGREGATION["DEMO"]["FP_H16"] = GROUPS["FP_H16"].copy()

    AGGREGATION["DEMO_WX0"] = _weather_period_aggregation("WH16")
    for group_name in _weather_group_names("WH16"):
        AGGREGATION["DEMO_WX0"][group_name]["weight"] = 0
    AGGREGATION["DEMO_WX0"]["FP_H16"] = GROUPS["FP_H16"].copy()


def build_registries():
    global REQUIREMENTS, BENCHMARK_FUNCTIONS, GROUPS, AGGREGATION
    global WX_GROUP_BENCHMARKS, WX_GROUPS_BY_PERIOD, HRRR_FP_GROUP_BENCHMARKS
    global FIRE_PERIMETER_GROUP_PERIMETERS

    REQUIREMENTS = copy.deepcopy(_BASE_REQUIREMENTS)
    BENCHMARK_FUNCTIONS = _BASE_BENCHMARK_FUNCTIONS.copy()
    GROUPS = {}
    AGGREGATION = {}
    WX_GROUP_BENCHMARKS = {}
    WX_GROUPS_BY_PERIOD = {}
    HRRR_FP_GROUP_BENCHMARKS = {}
    FIRE_PERIMETER_GROUP_PERIMETERS = {}

    add_wx_benchmarks()
    add_hrrr_fire_perimeter_benchmarks()
    create_benchmark_groups()
    create_aggregation_schemes()

    return BENCHMARK_FUNCTIONS, GROUPS, AGGREGATION


def run_all_benchmarks(
    model_dataset_path: Path,
    agg_scheme: str,
    list_bench: list,
    obs_dataset_path: Path = DEFAULT_OBS_DATA_PATH,
):
    ft.logger.debug("run_all_benchmarks")

    rslt = {"benchmarks": {}}
    ctx = {"ignored_benchmarks": set()}
    with File(obs_dataset_path, "r") as obs_dataset, File(model_dataset_path, "r") as model_dataset:
        fs.validate_h5_std(obs_dataset)
        fs.validate_h5_std(model_dataset)
        for input_name, dataset in (
            ("observational", obs_dataset),
            ("model", model_dataset),
        ):
            valid, issue = fs.validate_h5_referenced_files(dataset)
            if not valid:
                raise ValueError(f"Invalid {input_name} referenced asset: {issue}")

        _validate_selected_weather_confidence(obs_dataset, list_bench, ctx)

        for req_name, req_dict in REQUIREMENTS.items():
            # filter list benchmarks
            list_filtered = [bench for bench in req_dict["benchmarks"] if bench in list_bench]
            ft.logger.debug(
                "Filtered list of benchmarks to run with current requirement: %s", list_filtered
            )
            rslt["benchmarks"] = ft.merge_dictionaries(
                rslt["benchmarks"],
                req_dict["main"](
                    model_dataset, obs_dataset, list_filtered, req_dict["required_datasets"], ctx
                ),
            )

    ignored_benchmarks = ctx["ignored_benchmarks"]
    raise_if_selected_benchmarks_missing(rslt["benchmarks"], list_bench, ignored_benchmarks)

    rslt = aggregate_scores(rslt, agg_scheme, ignored_benchmarks)

    return rslt


def get_benchmark_requirements() -> dict[str, list[str]]:
    benchmark_requirements = {}
    for req_name, req_dict in REQUIREMENTS.items():
        for bench_id in req_dict["benchmarks"]:
            benchmark_requirements.setdefault(bench_id, []).append(req_name)
    return benchmark_requirements


def raise_if_selected_benchmarks_missing(
    benchmark_results: dict,
    list_bench: list[str],
    ignored_benchmarks: set[str] | None = None,
) -> None:
    ignored = ignored_benchmarks or set()
    missing_benchmarks = [
        bench_id for bench_id in list_bench if bench_id not in benchmark_results and bench_id not in ignored
    ]
    if not missing_benchmarks:
        return

    benchmark_requirements = get_benchmark_requirements()
    missing_details = [
        f"{bench_id} ({'/'.join(benchmark_requirements.get(bench_id, ['unknown requirement']))})"
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


def aggregate_scores(benchmark_results, agg_scheme, ignored_benchmarks: set[str] | None = None):
    if agg_scheme == "0":
        ft.logger.warning("Aggregation scheme `0` selected. No aggregation performed")
        return benchmark_results

    if agg_scheme not in AGGREGATION.keys():
        ft.logger.error(
            "Selected aggregation scheme not available. See documentation for available agg scheme"
        )

    scheme = AGGREGATION[agg_scheme]
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
            # print(bench_id, benchmark_results["benchmarks"][bench_id]["Score"],  group_bench[bench_id])
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

    benchmark_results["score_card"]["aggregation_scheme_name"] = agg_scheme
    benchmark_results["score_card"]["benchmark_target_name"] = agg_scheme
    group_display_names = _target_group_display_names(agg_scheme)
    if group_display_names:
        benchmark_results["score_card"]["group_display_names"] = group_display_names

    return benchmark_results


def aggregate_building_damage_binary(data_file: File):
    """
    Aggregates building damage classes into binary classes
    - unburnt (0) from `No Damage`, `Affected (1-9%)`, and `Minor (10-25%)`,
    - burnt (1) from `Major (26-50%)`, and `Destroyed (>50%)`

    class `Inaccessible` is ignored.
    """
    UNBURNT_CAT = ["No Damage", "Affected (1-9%)", "Minor (10-25%)"]
    BURNT_CAT = ["Major (26-50%)", "Destroyed (>50%)"]
    binary_bd = []
    bd = np.array(data_file[f"/{fs.POINTS}/building_damaged/building_damage"][:], dtype="U")

    for i in range(len(bd)):
        if str(bd[i]) in UNBURNT_CAT:
            binary_bd.append(0)
        elif bd[i] in BURNT_CAT:
            binary_bd.append(1)

    binary_bd = np.array(binary_bd, dtype=np.int8)

    ft.logger.info(
        "aggregated building damaged stats: %d buildings burnt, %d buildings unburnt",
        np.sum(binary_bd),
        len(binary_bd) - np.sum(binary_bd),
    )

    return binary_bd


def aggregate_high_severity_binary(data_file: File):
    """
    Aggregates burn severity classes into binary classes
    - not high (0) from values: 0, 1, 2, 3, and 5,
    - high (1) from value 4
    """
    ft.logger.debug("aggregate_high_severity_binary")
    NOT_HIGH_VAL = [0, 1, 2, 3, 5, 6]
    HIGH_VAL = [4]
    binary_sv = []
    sv = np.array(
        data_file[f"/{fs.SPATIAL_2D}/Caldor_MTBS/fire_burn_severity"][:, :], dtype=np.uint8
    ).ravel()

    for i in range(len(sv)):
        if sv[i] in NOT_HIGH_VAL:
            binary_sv.append(0)
        elif sv[i] in HIGH_VAL:
            binary_sv.append(1)
        else:
            ft.logger.debug(sv[i])

    binary_sv = np.array(binary_sv, dtype=np.int8)

    ft.logger.info(
        "aggregated high burn severity stats: %d high severity, %d other",
        np.sum(binary_sv),
        len(binary_sv) - np.sum(binary_sv),
    )

    return binary_sv


def get_mask_ravg_cc_valid(dataset: File, mask: np.ndarray):
    ravg_cc = dataset[f"/{fs.SPATIAL_2D}/ravg_cc/ravg_canopy_cover_loss"][:, :]
    valid = (mask != 0) & (ravg_cc != 0)
    return valid


def apply_high_ravg_cc_mask(dataset: File, mask: np.ndarray):
    ravg_cc = dataset[f"/{fs.SPATIAL_2D}/ravg_cc/ravg_canopy_cover_loss"][:, :]
    high_cc_masked = np.zeros_like(ravg_cc, dtype=np.float64)
    high_cc_masked[~mask] = np.nan
    high_cc_masked[mask & (ravg_cc == 5)] = 1
    return high_cc_masked[np.isfinite(high_cc_masked)]


def mask_landfire_canopy(data_file: File, path_tgt_grp_var: str, list_datasets_landfire: list[str]):
    """
    Create a mask using a collection of landfire canopy dataset (typically CBH, CBD, CH)
    Create the mask for each calfire variable, then assert than grid is the same, then concatenate mask, then interpolate nearest of target variable grid
    """
    landfire_masks = []

    # get landfire grid
    pos_lat_landfire = data_file[f"{list_datasets_landfire[0].rsplit('/', 1)[0]}/position_lat"][:, :]
    pos_lon_landfire = data_file[f"{list_datasets_landfire[0].rsplit('/', 1)[0]}/position_lon"][:, :]

    # verify that landfire grid is the same for each field
    for landfire_var in list_datasets_landfire:
        assert np.all(
            np.isclose(pos_lat_landfire, data_file[f"{landfire_var.rsplit('/', 1)[0]}/position_lat"][:, :])
        ), "landfire latitude grid not consistent between landire variables"
        assert np.all(
            np.isclose(pos_lon_landfire, data_file[f"{landfire_var.rsplit('/', 1)[0]}/position_lon"][:, :])
        ), "landfire longitude grid not consistent between landire variables"
        # create mask
        landfire_masks.append((data_file[landfire_var][:, :] > 0))

    landfire_mask = np.logical_and.reduce(landfire_masks)

    # interpolate on target variable grid
    pos_lat_tgt = data_file[f"{path_tgt_grp_var}/position_lat"][:, :]
    pos_lon_tgt = data_file[f"{path_tgt_grp_var}/position_lon"][:, :]
    interp = NearestNDInterpolator(
        list(zip(pos_lat_landfire.ravel(), pos_lon_landfire.ravel())), landfire_mask.ravel()
    )

    mask_tgt_grid = interp(pos_lat_tgt, pos_lon_tgt)

    return get_mask_ravg_cc_valid(data_file, mask_tgt_grid)


def resolve_h5_relative_path(data_file: File, rel_path: str | bytes | Path):
    path = Path(rel_path.decode() if isinstance(rel_path, bytes) else rel_path)
    if path.is_absolute():
        return path
    return Path(data_file.filename).resolve().parent / path


def jaccard_from_list(model_dataset: File, obs_dataset: File, list_perims: list[str], projection: str):
    jaccard = []
    for perim in list_perims:
        gdf_obs = gpd.read_file(
            resolve_h5_relative_path(obs_dataset, obs_dataset[perim].attrs["rel_path"]), driver="KML"
        )
        gdf_model = gpd.read_file(
            resolve_h5_relative_path(model_dataset, model_dataset[perim].attrs["rel_path"]), driver="KML"
        )
        jaccard.append(fm.perimeter.jaccard_polygon(gdf_obs, gdf_model, projection=projection))
    return np.array(jaccard)


def sorensen_dice_from_list(
    model_dataset: File, obs_dataset: File, list_perims: list[str], projection: str
):
    sorensen_dice = []
    for perim in list_perims:
        gdf_obs = gpd.read_file(
            resolve_h5_relative_path(obs_dataset, obs_dataset[perim].attrs["rel_path"]), driver="KML"
        )
        gdf_model = gpd.read_file(
            resolve_h5_relative_path(model_dataset, model_dataset[perim].attrs["rel_path"]), driver="KML"
        )
        sorensen_dice.append(fm.perimeter.sorensen_dice_polygon(gdf_obs, gdf_model, projection=projection))
    return np.array(sorensen_dice)


def area_from_list(dataset: File, list_perims: list[str], projection_epsg: int):
    output = []
    for perim in list_perims:
        gdf = gpd.read_file(
            resolve_h5_relative_path(dataset, dataset[perim].attrs["rel_path"]), driver="KML"
        )
        gdf = gdf.to_crs(epsg=projection_epsg)
        output.append(np.sum(gdf.area))
    return Quantity(np.array(output), "m^2")


def get_mask_from_period(dataset: File, group_path: str, period: tuple[datetime, datetime]):
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

    return _mask_time_window_rel(time, time_origin, time_units, window=period, interval="closed")


def _mask_time_window_rel(
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
    if not (origin_aware == start_aware == end_aware):
        raise ValueError("time_origin, start_dt, and end_dt must all be naive or all be timezone-aware")

    # Convert datetime window to relative time in `time_units`
    start_seconds = (start_dt - time_origin).total_seconds()
    end_seconds = (end_dt - time_origin).total_seconds()

    start_rel = Quantity(start_seconds, "s").to(time_units).magnitude
    end_rel = Quantity(end_seconds, "s").to(time_units).magnitude

    # Ensure float arrays for safe comparisons
    t = np.asarray(time_rel, dtype=np.float64)

    return _mask_time_window(interval, t, start_rel, end_rel)


def _mask_time_window(
    interval: str, t: np.ndarray[np.float64], start_t: np.ndarray[np.float64], end_t: np.ndarray[np.float64]
):
    if interval == "closed":
        return (t >= start_t) & (t <= end_t)
    if interval == "left_closed":
        return (t >= start_t) & (t < end_t)
    if interval == "right_closed":
        return (t > start_t) & (t <= end_t)
    if interval == "open":
        return (t > start_t) & (t < end_t)

    raise ValueError(f"Unknown interval={interval}")


def overwrite_previous_run(overwrite: bool, output_path: Path = DEFAULT_OUTPUT_PATH_JSON):
    ft.logger.debug("overwrite_previous_run")
    if overwrite:
        return True

    if output_path.exists():
        choice = (
            input(
                f"Output file {output_path} already exists. Overwrite it? [y/N]  (use -o to force overwrite): "
            )
            .strip()
            .lower()
        )
        if choice == "y" or choice == "yes":
            ft.logger.debug("Overwrite authorized for output file: %s", output_path)
            return True
    else:
        return True

    return False


def get_files_hash(model_output: Path, obs_data_path: Path = DEFAULT_OBS_DATA_PATH):
    ft.logger.debug("get_files_hash")
    file_integrity = {}

    if not obs_data_path.exists():
        ft.logger.error("Observational file: %s not found", obs_data_path)
        raise FileExistsError()
    file_integrity["obs_dataset_hash"] = ft.calculate_sha256(obs_data_path)
    with File(obs_data_path, "r") as obs_dataset:
        obs_referenced_assets = fs.get_h5_referenced_file_integrity(obs_dataset)
    if obs_referenced_assets:
        file_integrity["obs_referenced_assets"] = obs_referenced_assets

    if not model_output.exists():
        ft.logger.error("Model file: %s not found", model_output)
        raise FileExistsError()
    file_integrity["model_output"] = ft.calculate_sha256(model_output)
    with File(model_output, "r") as model_dataset:
        model_referenced_assets = fs.get_h5_referenced_file_integrity(model_dataset)
    if model_referenced_assets:
        file_integrity["model_referenced_assets"] = model_referenced_assets

    file_integrity["benchmark_script"] = ft.calculate_sha256(Path(__file__))

    return file_integrity


def debug_json_dump(obj, path="root"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            debug_json_dump(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            debug_json_dump(v, f"{path}[{i}]")
    else:
        try:
            json.dumps(obj)
        except TypeError:
            print(f"Not serializable at {path}: {type(obj)} -> {obj}")


def get_list_benchmark_with_agg(agg_dict: dict, agg_scheme: str):
    if agg_scheme == "0":
        return list(BENCHMARK_FUNCTIONS.keys())
    agg = agg_dict.get(agg_scheme, {})
    bench_list = []
    for group_val in agg.values():
        for bench in group_val["benchmarks"].keys():
            if bench not in bench_list:
                bench_list.append(bench)

    return bench_list


def _benchmark_debug_label(bench_id: str) -> str:
    if bench_id in STATIC_KPI_NAMES:
        return STATIC_KPI_NAMES[bench_id]
    benchmark = BENCHMARK_FUNCTIONS[bench_id]
    keywords = getattr(benchmark, "keywords", {}) or {}
    if "kpi_name_custom" in keywords:
        return keywords["kpi_name_custom"]
    if getattr(benchmark, "func", None) is bench_fp_generic_area_final_bias:
        return "Final Burn Area Bias"
    return ""


def describe_benchmark_registry(benchmark_target: str = DEFAULT_AGGREGATION_SCHEME) -> str:
    build_registries()
    selected_target = resolve_benchmark_target(benchmark_target)
    if selected_target == "0":
        selected_groups = {
            "All Benchmarks": {
                "weight": 1,
                "benchmarks": {bench_id: 1 for bench_id in BENCHMARK_FUNCTIONS},
            }
        }
    elif selected_target in AGGREGATION:
        selected_groups = AGGREGATION[selected_target]
    else:
        available = ", ".join(sorted(AGGREGATION))
        raise ValueError(f"Unknown benchmark target '{benchmark_target}'. Available schemes: {available}")

    selected_benchmarks = []
    for group_content in selected_groups.values():
        for bench_id in group_content["benchmarks"]:
            if bench_id not in selected_benchmarks:
                selected_benchmarks.append(bench_id)

    lines = [
        f"Benchmark target: {selected_target}",
        f"Registered benchmarks: {len(BENCHMARK_FUNCTIONS)}",
        f"Registered groups: {len(GROUPS)}",
        f"Selected groups: {len(selected_groups)}",
        f"Selected benchmarks: {len(selected_benchmarks)}",
        "",
        "Groups:",
    ]
    for group_name, group_content in selected_groups.items():
        lines.append(
            f"- {group_name} (weight={group_content['weight']}, "
            f"benchmarks={len(group_content['benchmarks'])})"
        )
        perimeters = FIRE_PERIMETER_GROUP_PERIMETERS.get(group_name, [])
        if perimeters:
            lines.append("  Perimeters:")
            for perimeter in perimeters:
                lines.append(f"    - {perimeter}")
        for bench_id, bench_weight in group_content["benchmarks"].items():
            label = _benchmark_debug_label(bench_id)
            suffix = f" - {label}" if label else ""
            lines.append(f"  - {bench_id} (weight={bench_weight}){suffix}")

    return "\n".join(lines)


def create_report_figures(
    model_output: Path,
    obs_data: Path,
    benchmark_target: str,
    target_info: dict | None,
    output_dir: Path,
) -> list[dict]:
    if target_info is None:
        return []

    perimeter_paths = [perimeter["path"] for perimeter in target_info.get("perimeters", [])]
    if not perimeter_paths:
        return []

    output_path = Path(output_dir) / f"perimeters_{benchmark_target}.png"
    plot_perimeter_contours(
        model_output=model_output,
        obs_data=obs_data,
        perimeter_paths=perimeter_paths,
        output_path=output_path,
    )
    return [
        {
            "title": "Fire perimeter comparison",
            "path": output_path,
            "alt": "Observed and modeled fire perimeter contours",
        }
    ]


def print_benchmark_registry(benchmark_target: str = DEFAULT_AGGREGATION_SCHEME) -> None:
    print(describe_benchmark_registry(benchmark_target))


def run_caldor_benchmark(
    model_output: Path,
    benchmark_target: str,
    name: str = "",
    overwrite: bool = False,
    sign: tuple[str, str] | None = None,
    obs_data: Path = DEFAULT_OBS_DATA_PATH,
    output_json: Path = DEFAULT_OUTPUT_PATH_JSON,
    score_card_report: Path = DEFAULT_SCORE_CARD_REPORT_PATH,
    score_card_full_name: bool = False,
):
    model_output = Path(model_output)
    obs_data = Path(obs_data)
    output_json = Path(output_json)
    score_card_report = Path(score_card_report)

    if not overwrite_previous_run(overwrite, output_json):
        ft.logger.info("Overwrite not authorized for output file: %s. Benchmark stopped", output_json)
        return {}

    with File(obs_data, "r") as f:
        try:
            obs_data_version = f.attrs["version"]
        except KeyError:
            obs_data_version = "Unofficial"

    ft.logger.debug("Add default information about this run in output dict")
    output_dict = {
        "created_on": fs.current_datetime_iso8601(include_seconds=True),
        "case_version": obs_data_version,
        "firebench_version": fb_version,
        "case_name": CASE_NAME,
        "benchmark_short_name": BENCHMARK_SHORT_NAME,
        "case_id": CASE_ID,
        "evaluated_model_name": str(model_output).strip(".h5"),
    }
    if name != "":
        output_dict["evaluated_model_name"] = str(name)
    output_dict = ft.merge_dictionaries(output_dict, get_files_hash(model_output, obs_data))

    build_registries()
    aggregation_scheme = resolve_benchmark_target(benchmark_target)
    list_bench = get_list_benchmark_with_agg(AGGREGATION, aggregation_scheme)

    rslt = run_all_benchmarks(model_output, aggregation_scheme, list_bench, obs_data)
    output_dict = ft.merge_dictionaries(output_dict, rslt)

    # certification
    signed = False
    if sign:
        key, signer = sign
        output_dict["certificates_input"] = fsi.retrieve_h5_certificates(obs_data, model_output)
        output_dict = fsi.certify_benchmark_run(output_dict, key, signer)
        signed = True

    fm.save_as_table(
        score_card_report,
        output_dict,
        signed,
        "certificate_verif_lvl",
        full_name=score_card_full_name,
    )
    if not score_card_report.exists():
        ft.logger.error("Score card report: %s not found", score_card_report)
        raise FileExistsError()
    output_dict["score_card_report_hash"] = ft.calculate_sha256(score_card_report)
    if sign:
        output_dict, _ = fsi.add_certificate_to_dict(
            output_dict, "certificate_final", fsi.Certificates.FB_SCORE_CARD.value, key, signer
        )

    fsi.write_case_results(output_json, output_dict)
    return output_dict


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Run benchmark against a model HDF5 output.")

    parser.add_argument("benchmark_target", type=str, help="Benchmark target, for example H013_P")
    parser.add_argument("model_output", type=Path, help="Path to your model output HDF5 file")

    parser.add_argument(
        "-v",
        "--logging-level",
        type=int,
        default=DEFAULT_LOGGING_LEVEL,
        help=f"Logging level (default: {DEFAULT_LOGGING_LEVEL})",
    )

    parser.add_argument(
        "-n",
        "--name",
        type=str,
        default="",
        help=f"Name of the evaluated model/configuration",
    )

    parser.add_argument(
        "-o", "--overwrite", action="store_true", help="Overwrite existing results if present."
    )

    parser.add_argument(
        "-s",
        "--sign",
        nargs=2,
        metavar=("KEYID", "SIGNER"),
        help="Sign with Verification Level (VL) using KEYID and SIGNER",
    )
    parser.add_argument(
        "--full-name",
        "--full_name",
        action="store_true",
        help="Use full benchmark IDs and KPI names in the score-card PDF.",
    )

    args = parser.parse_args(argv)

    ft.create_file_handler(LOG_FILENAME, args.logging_level)
    run_caldor_benchmark(
        args.model_output,
        benchmark_target=args.benchmark_target,
        name=args.name,
        overwrite=args.overwrite,
        sign=tuple(args.sign) if args.sign else None,
        score_card_full_name=args.full_name,
    )


if __name__ == "__main__":
    main()
