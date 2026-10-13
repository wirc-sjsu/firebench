"""
Generic weather-forecast benchmark: one forecast cycle scored against weather stations.

The case is not tied to a fire: it is configured by a forecast cycle, lead-time bins and cadence
tiers, and scores any model file with ``/time_series/station_<STID>`` groups (for example the
output of the embedded HRRR adapter) against a standard observation file.

KPI axes: variable x metric x station set x summary statistic x cadence x lead-time bin. Variables,
metrics and normalization parameters are those of the Caldor weather benchmark
(``c001_caldor_config.WX_VARIABLE_SPECS``); trusted-source (TSO) KPIs have weight 1 and all-source
KPIs weight 0, as in Caldor. Lead bins marked informational (by default ``F00``, the analysis, which
assimilates surface observations) form weight-0 groups that are displayed but move neither the
numerator nor the denominator of the total.

Benchmark IDs are semantic and order-independent, e.g. ``WX-AT-MAE-MEAN-TSO-1H-F0148``.
A variable that the model or the observations do not provide is reported as excluded, with its
reason, instead of being scored as empty.

Fire-weather diagnostics are optional (``WxForecastSpec.diagnostics``) and never move the total:
compound indices computed from the station variables (``fire_weather_index``) and contingency
metrics of threshold events (``event_threshold``). Their groups have weight 0.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

import hdf5plugin  # pylint: disable=unused-import  # registers the Zstd filter of station datasets
import numpy as np
from h5py import File

from firebench import __version__ as fb_version
from firebench import metrics as fm
from firebench import signing as fsi
from firebench import standardize as fs
from firebench import tools as ft

from . import wx_cadence
from . import wx_common as wxc
from .c001_caldor_config import WX_VARIABLE_SPECS

CASE_ID = "WXF"
BENCHMARK_SHORT_NAME = "WX_Forecast"
DEFAULT_TARGET = "ALL"

# Metric families: what a KPI evaluates. Only direct weather accuracy counts in the total.
FAMILY_ACCURACY = "weather_accuracy"
FAMILY_INDEX = "fire_weather_index"
FAMILY_EVENT = "event_threshold"
DIAGNOSTIC_FAMILIES = (FAMILY_INDEX, FAMILY_EVENT)

# Thresholds of the events, on the hourly values at the sensor height of each station.
LOW_RELATIVE_HUMIDITY_PERCENT = 20.0
STRONG_WIND_SPEED_MS = 4.5

VARIABLE_CODES = {
    "air_temperature": "AT",
    "relative_humidity": "RH",
    "wind_speed": "WS",
    "wind_direction": "WD",
    "fuel_moisture_content_10h": "FM10",
    "vapor_pressure_deficit": "VPD",
    "fosberg_fire_weather_index": "FFWI",
    "low_relative_humidity": "RHLOW",
    "strong_wind": "WSHIGH",
    "critical_fire_weather": "CFW",
}


def _probability_of_detection(counts: np.ndarray):
    _, _, misses, hits = counts.ravel()
    if hits + misses == 0:
        return wx_cadence.KpiIgnored("the event was not observed")
    value = float(fm.confusion_matrix.binary_recall_rate(counts))
    return value, fm.kpi_norm_bounded_linear(value, 0.0, 1.0)


def _false_alarm_ratio(counts: np.ndarray):
    _, false_alarms, _, hits = counts.ravel()
    if hits + false_alarms == 0:
        return wx_cadence.KpiIgnored("the event was not forecast")
    value = float(fm.confusion_matrix.binary_false_alarm_ratio(counts))
    return value, fm.kpi_norm_bounded_linear(1.0 - value, 0.0, 1.0)


def _critical_success_index(counts: np.ndarray):
    _, false_alarms, misses, hits = counts.ravel()
    if hits + false_alarms + misses == 0:
        return wx_cadence.KpiIgnored("the event was neither observed nor forecast")
    value = float(fm.confusion_matrix.binary_critical_success_index(counts))
    return value, fm.kpi_norm_bounded_linear(value, 0.0, 1.0)


METRICS = {
    "standard": (
        ("MAE", "MAE", fm.stats.mae),
        ("RMSE", "RMSE", fm.stats.rmse),
        ("Bias", "BIAS", fm.stats.bias),
    ),
    "wind_direction": (("circular bias", "CBIAS", fm.stats.circular_bias_deg),),
    "event": (
        ("POD", "POD", _probability_of_detection),
        ("FAR", "FAR", _false_alarm_ratio),
        ("CSI", "CSI", _critical_success_index),
    ),
}
SUMMARY_STATS = (("min", np.nanmin), ("mean", np.nanmean), ("max", np.nanmax))
# An event is counted over every station and timestamp at once: a ratio per station has too few events.
POOLED_STATS = (("pooled", None),)
STATION_SETS = (
    ("TSO", "TSO", fs.WeatherStationSet.TSO, 1),
    ("All sources", "ALL", fs.WeatherStationSet.ALL_SOURCES, 0),
)


def _low_relative_humidity(relative_humidity):
    return relative_humidity <= LOW_RELATIVE_HUMIDITY_PERCENT


def _strong_wind(wind_speed):
    return wind_speed >= STRONG_WIND_SPEED_MS


def _critical_fire_weather(relative_humidity, wind_speed):
    return _low_relative_humidity(relative_humidity) & _strong_wind(wind_speed)


_AIR_TEMPERATURE = ("air_temperature", "degC")
_RELATIVE_HUMIDITY = ("relative_humidity", "percent")
_WIND_SPEED = ("wind_speed", "m/s")

# Quantities computed from several station variables, for the model and the observations alike.
# ``inputs`` lists ``(variable, unit)`` in the order of the arguments of ``function``.
WX_DIAGNOSTIC_SPECS = (
    {
        "family": FAMILY_INDEX,
        "label": "VPD",
        "group_label": "VPD",
        "variable": "vapor_pressure_deficit",
        "common_unit": "hPa",
        "norm_m": 10,
        "metric_set": "standard",
        "inputs": (_AIR_TEMPERATURE, _RELATIVE_HUMIDITY),
        "function": fm.fire_weather.vapor_pressure_deficit,
    },
    {
        "family": FAMILY_INDEX,
        "label": "Fosberg FWI",
        "group_label": "Fosberg FWI",
        "variable": "fosberg_fire_weather_index",
        "common_unit": "dimensionless",
        "norm_m": 10,
        "metric_set": "standard",
        "inputs": (_AIR_TEMPERATURE, _RELATIVE_HUMIDITY, _WIND_SPEED),
        "function": fm.fire_weather.fosberg_fire_weather_index,
    },
    {
        "family": FAMILY_EVENT,
        "label": "Low RH",
        "group_label": "Low RH",
        "variable": "low_relative_humidity",
        "common_unit": "dimensionless",
        "metric_set": "event",
        "inputs": (_RELATIVE_HUMIDITY,),
        "function": _low_relative_humidity,
        "definition": f"relative humidity <= {LOW_RELATIVE_HUMIDITY_PERCENT:g} %",
    },
    {
        "family": FAMILY_EVENT,
        "label": "Strong wind",
        "group_label": "Strong wind",
        "variable": "strong_wind",
        "common_unit": "dimensionless",
        "metric_set": "event",
        "inputs": (_WIND_SPEED,),
        "function": _strong_wind,
        "definition": f"wind speed >= {STRONG_WIND_SPEED_MS:g} m/s",
    },
    {
        "family": FAMILY_EVENT,
        "label": "Critical fire wx",
        "group_label": "Critical fire wx",
        "variable": "critical_fire_weather",
        "common_unit": "dimensionless",
        "metric_set": "event",
        "inputs": (_RELATIVE_HUMIDITY, _WIND_SPEED),
        "function": _critical_fire_weather,
        "definition": (
            f"relative humidity <= {LOW_RELATIVE_HUMIDITY_PERCENT:g} % and "
            f"wind speed >= {STRONG_WIND_SPEED_MS:g} m/s"
        ),
    },
)


@dataclass(frozen=True)
class LeadBin:
    """Forecast lead-time bin ``[start, end]`` in hours after the cycle."""

    start: int
    end: int
    informational: bool = False

    @property
    def label(self) -> str:
        """Display label, e.g. ``F01-48`` or ``F00``."""
        return f"F{self.start:02d}" if self.start == self.end else f"F{self.start:02d}-{self.end:02d}"

    @property
    def code(self) -> str:
        """ID fragment, e.g. ``F0148``."""
        return f"F{self.start:02d}{self.end:02d}"


@dataclass
class WxForecastSpec:
    """What to score for one forecast cycle."""

    case_name: str
    cycle: datetime
    horizon_hours: int = 48
    lead_bins: tuple = ((1, 48),)
    informational_lead_bins: tuple = ((0, 0),)
    cadences: tuple = (1,)
    obs_tolerance_s: float = wx_cadence.DEFAULT_OBS_TOLERANCE_S
    model_tolerance_s: float = wx_cadence.DEFAULT_MODEL_TOLERANCE_S
    min_coverage: float = wx_cadence.DEFAULT_MIN_COVERAGE
    variables: tuple = tuple(spec["variable"] for spec in WX_VARIABLE_SPECS)
    # Families of fire-weather diagnostics to add, among ``DIAGNOSTIC_FAMILIES``. None by default.
    diagnostics: tuple = ()

    def bins(self) -> list[LeadBin]:
        """Scored then informational lead bins, clamped to the forecast horizon."""
        bins = []
        for bounds, informational in [(b, False) for b in self.lead_bins] + [
            (b, True) for b in self.informational_lead_bins
        ]:
            start, end = (int(value) for value in bounds)
            if not 0 <= start <= end:
                raise ValueError(f"invalid lead bin {list(bounds)}: expected 0 <= start <= end (hours)")
            if start > self.horizon_hours:
                ft.logger.warning(
                    "Lead bin %s ignored: beyond the %d h forecast horizon.",
                    list(bounds),
                    self.horizon_hours,
                )
                continue
            if end > self.horizon_hours:
                ft.logger.warning(
                    "Lead bin %s clamped to the %d h forecast horizon.", list(bounds), self.horizon_hours
                )
                end = self.horizon_hours
            lead_bin = LeadBin(start, end, informational)
            if lead_bin not in bins:
                bins.append(lead_bin)
        return bins


@dataclass
class WxRegistry:
    """Registries of one forecast cycle, in the shape the shared weather helpers expect."""

    requirements: dict = field(default_factory=dict)
    benchmark_functions: dict = field(default_factory=dict)
    groups: dict = field(default_factory=dict)
    aggregation: dict = field(default_factory=dict)
    excluded: list = field(default_factory=list)


def benchmark_id(
    variable: str, metric_code: str, stat: str, set_code: str, cadence: int, lead_bin: LeadBin
) -> str:
    """Semantic benchmark ID, e.g. ``WX-AT-MAE-MEAN-TSO-1H-F0148``."""
    return (
        f"WX-{VARIABLE_CODES[variable]}-{metric_code}-{stat.upper()}-{set_code}-{cadence}H-{lead_bin.code}"
    )


def group_name(group_label: str, cadence: int, lead_bin: LeadBin) -> str:
    """Group name, e.g. ``Air Temp 1h F01-48`` or ``Air Temp 1h F00 analysis``."""
    name = f"{group_label} {cadence}h {lead_bin.label}"
    if lead_bin.informational:
        name += " analysis" if lead_bin.start == lead_bin.end == 0 else " (info)"
    return name


def summary_stats(metric_set: str) -> tuple:
    """Summaries over stations of a metric set: ``(label, function)`` pairs."""
    return POOLED_STATS if metric_set == "event" else SUMMARY_STATS


def quantity_specs(spec: WxForecastSpec) -> list[dict]:
    """
    Every quantity a cycle scores, in score-card order: station variables, then the diagnostics.

    Each item has the keys of ``WX_VARIABLE_SPECS`` and a ``family``. A diagnostic also has its
    ``inputs`` and the ``function`` that computes it from them.
    """
    unknown = sorted(set(spec.diagnostics) - set(DIAGNOSTIC_FAMILIES))
    if unknown:
        raise ValueError(f"unknown diagnostics {unknown}; available: {', '.join(DIAGNOSTIC_FAMILIES)}")
    quantities = [
        {"family": FAMILY_ACCURACY, **item}
        for item in WX_VARIABLE_SPECS
        if item["variable"] in spec.variables
    ]
    quantities += [item for item in WX_DIAGNOSTIC_SPECS if item["family"] in spec.diagnostics]
    return quantities


def kpi_table(spec: WxForecastSpec) -> list[dict]:
    """
    Every KPI a cycle can define, with its dimensions, in registry order.

    For a consumer that reads a result file: it gives the meaning of a benchmark ID without taking
    the ID apart. A KPI of the table is absent from a result when its quantity was excluded or the
    KPI was ignored.
    """
    rows = []
    for quantity in quantity_specs(spec):
        for cadence in spec.cadences:
            for lead_bin in spec.bins():
                for kpi in _group_kpis(quantity, cadence, lead_bin):
                    rows.append(
                        {
                            "id": kpi["id"],
                            "variable": quantity["variable"],
                            "label": quantity["label"],
                            "family": quantity["family"],
                            "units": quantity["common_unit"],
                            "metric": kpi["metric_code"],
                            "metric_label": kpi["metric_label"],
                            "statistic": kpi["stat_label"],
                            "station_set": kpi["set_code"],
                            "station_set_label": kpi["set_label"],
                            "cadence_hours": cadence,
                            "lead_bin": lead_bin,
                            "group": group_name(quantity["group_label"], cadence, lead_bin),
                            "weight": kpi["weight"],
                            "group_weight": _group_weight(quantity, lead_bin),
                        }
                    )
    return rows


def _group_weight(quantity: dict, lead_bin: LeadBin) -> int:
    """Weight of a group in the total: 0 for an informational lead bin and for a diagnostic."""
    return 0 if lead_bin.informational or quantity["family"] != FAMILY_ACCURACY else 1


def _group_kpis(quantity: dict, cadence: int, lead_bin: LeadBin) -> list[dict]:
    """KPIs of one group: metric x station set x summary over stations."""
    kpis = []
    for metric_label, metric_code, metric_func in METRICS[quantity["metric_set"]]:
        for set_label, set_code, station_set, weight in STATION_SETS:
            for stat_label, stat_func in summary_stats(quantity["metric_set"]):
                kpis.append(
                    {
                        "id": benchmark_id(
                            quantity["variable"], metric_code, stat_label, set_code, cadence, lead_bin
                        ),
                        "metric_label": metric_label,
                        "metric_code": metric_code,
                        "metric_func": metric_func,
                        "set_label": set_label,
                        "set_code": set_code,
                        "station_set": station_set,
                        "weight": weight,
                        "stat_label": stat_label,
                        "stat_func": stat_func,
                    }
                )
    return kpis


def _exclusion_reason(quantity: dict, model_variables, obs_variables) -> str | None:
    """Why a quantity cannot be scored with these files, or None when it can."""
    compound = "inputs" in quantity
    needed = [name for name, _ in quantity["inputs"]] if compound else [quantity["variable"]]
    for available, reason in ((model_variables, "no model data"), (obs_variables, "no observation")):
        if available is None:
            continue
        missing = [name for name in needed if name not in available]
        if missing:
            return f"{reason} for {', '.join(missing)}" if compound else reason
    return None


def station_variables(dataset: File) -> set[str]:
    """Variables present in at least one ``station*`` group of a standard file."""
    variables = set()
    for name, group in dataset.get(fs.TIME_SERIES, {}).items():
        if name.startswith("station"):
            variables.update(group.keys())
    return variables


def build_registry(
    spec: WxForecastSpec, model_dataset: File | None, obs_dataset: File | None
) -> WxRegistry:
    """Build the requirements, benchmarks, groups and targets of one cycle."""
    cycle = spec.cycle.astimezone(timezone.utc)
    for cadence in spec.cadences:
        wx_cadence.check_tolerance(spec.obs_tolerance_s, cadence)
    model_variables = station_variables(model_dataset) if model_dataset is not None else None
    obs_variables = station_variables(obs_dataset) if obs_dataset is not None else None
    bins = spec.bins()
    registry = WxRegistry()

    for variable_spec in quantity_specs(spec):
        variable = variable_spec["variable"]
        reason = _exclusion_reason(variable_spec, model_variables, obs_variables)
        if reason:
            registry.excluded.append({"variable": variable, "reason": reason})
            continue

        requirement = f"R-{VARIABLE_CODES[variable]}"
        required_datasets = {"station_pattern": "station_", "variable": variable}
        if "inputs" in variable_spec:
            required_datasets["inputs"] = [name for name, _ in variable_spec["inputs"]]
        registry.requirements[requirement] = {
            "main": partial(
                _compound_requirement if "inputs" in variable_spec else _weather_requirement,
                req_name=requirement,
                benchmark_functions=registry.benchmark_functions,
            ),
            "benchmarks": [],
            "required_datasets": required_datasets,
        }
        for cadence in spec.cadences:
            for lead_bin in bins:
                _add_group(registry, spec, variable_spec, requirement, cycle, cadence, lead_bin)

    registry.aggregation[DEFAULT_TARGET] = _copy_groups(registry.groups, list(registry.groups))
    for cadence in spec.cadences:
        suffix = f" {cadence}h "
        registry.aggregation[f"{cadence}H"] = _copy_groups(
            registry.groups, [name for name in registry.groups if suffix in name]
        )
    return registry


def run_wx_forecast_benchmark(
    model_output: Path,
    obs_data: Path,
    spec: WxForecastSpec,
    *,
    target: str = DEFAULT_TARGET,
    name: str = "",
    overwrite: bool = False,
    output_json: Path = Path("wx_forecast_rslt.json"),
    score_card_report: Path = Path("wx_forecast_scorecard.pdf"),
    full_name: bool = False,
) -> dict:
    """Score one model file against the observations for one cycle; writes the JSON and PDF."""
    model_output = Path(model_output)
    obs_data = Path(obs_data)
    output_json = Path(output_json)
    score_card_report = Path(score_card_report)
    if output_json.exists() and not overwrite:
        raise FileExistsError(f"benchmark result {output_json} already exists; use overwrite to replace it")

    with File(obs_data, "r") as obs_dataset:
        case_version = _attr_text(obs_dataset.attrs.get("version"), "Unofficial")
        data_tier = _attr_text(obs_dataset.attrs.get("data_tier"), "")
    certificates = fsi.retrieve_h5_certificates(obs_data)
    output_dict = {
        "created_on": fs.current_datetime_iso8601(include_seconds=True),
        "case_version": case_version,
        "firebench_version": fb_version,
        "case_name": spec.case_name,
        "benchmark_short_name": BENCHMARK_SHORT_NAME,
        "case_id": CASE_ID,
        "evaluated_model_name": name or model_output.stem,
        "obs_dataset_hash": ft.calculate_sha256(obs_data),
        "model_output": ft.calculate_sha256(model_output),
        "benchmark_script": ft.calculate_sha256(Path(__file__)),
        "certificates_input": certificates,
        "verification_lvl": fsi.compute_input_verification_lvl(certificates),
        "cycle": spec.cycle.astimezone(timezone.utc).isoformat(),
        "horizon_hours": spec.horizon_hours,
        "cadences_hours": list(spec.cadences),
        "lead_bins": [
            {
                "label": lead_bin.label,
                "start": lead_bin.start,
                "end": lead_bin.end,
                "informational": lead_bin.informational,
            }
            for lead_bin in spec.bins()
        ],
        "obs_tolerance_s": spec.obs_tolerance_s,
        "model_tolerance_s": spec.model_tolerance_s,
        "min_coverage": spec.min_coverage,
    }
    if spec.diagnostics:
        output_dict["diagnostics"] = list(spec.diagnostics)
    if data_tier:
        output_dict["data_tier"] = data_tier

    ctx = {"ignored_benchmarks": set()}
    with File(obs_data, "r") as obs_dataset, File(model_output, "r") as model_dataset:
        wxc.validate_benchmark_inputs(obs_dataset, model_dataset)
        registry = build_registry(spec, model_dataset, obs_dataset)
        if target not in registry.aggregation:
            raise ValueError(f"unknown target {target!r}; available: {', '.join(registry.aggregation)}")
        list_bench = _target_benchmarks(registry.aggregation[target])
        wxc.validate_selected_weather_confidence(obs_dataset, registry.benchmark_functions, list_bench, ctx)
        results = wxc.run_requirements(model_dataset, obs_dataset, registry.requirements, list_bench, ctx)
        height_policy = model_dataset.attrs.get("height_policy")

    ignored = ctx["ignored_benchmarks"]
    wxc.raise_if_selected_benchmarks_missing(results, list_bench, ignored, registry.requirements)
    scored = wxc.aggregate_scheme_scores(
        {"benchmarks": results}, target, registry.aggregation[target], ignored
    )
    output_dict.update(scored)
    output_dict["excluded_kpis"] = registry.excluded
    output_dict["ignored_benchmarks"] = sorted(ignored)
    if spec.diagnostics:
        # Why a diagnostic KPI has no value: an event that was not observed has no detection rate.
        output_dict["ignored_reasons"] = dict(sorted(ctx.get("ignored_reasons", {}).items()))
    output_dict["cadence_exclusions"] = list(ctx.get("cadence_exclusions", {}).values())
    if height_policy is not None:
        output_dict["height_policy"] = json.loads(_attr_text(height_policy, "{}"))

    score_card_report.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    fm.save_as_table(score_card_report, output_dict, False, "certificate_verif_lvl", full_name=full_name)
    output_dict["score_card_report_hash"] = ft.calculate_sha256(score_card_report.with_suffix(".pdf"))
    fsi.write_case_results(output_json, output_dict)
    return output_dict


def _weather_requirement(
    model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, *, req_name, benchmark_functions
):
    return wxc.run_weather_requirement(
        model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, req_name, benchmark_functions
    )


def _compound_requirement(
    model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, *, req_name, benchmark_functions
):
    """
    Check that the model has every input of a compound quantity, then run its KPIs.

    A KPI that cannot be computed is ignored and its reason is kept in ``ctx["ignored_reasons"]``.
    """
    ft.logger.info("Check Requirement %s", req_name)
    bench_output = {}
    if not list_benchmarks:
        ft.logger.info("No benchmark to run for Requirement %s", req_name)
        return bench_output

    periods = wxc.weather_requirement_periods(benchmark_functions, list_benchmarks)
    stations = set()
    for bench_id in list_benchmarks:
        keywords = benchmark_functions[bench_id].keywords
        stations.update(
            wx_cadence.compound_stations(
                None, obs_dataset, keywords["inputs"], keywords["period"], keywords["station_set"], ctx
            )
        )
    for variable in required_datasets["inputs"]:
        req_ok, miss = fs.validate_h5_weather_stations_structure(
            model_dataset,
            obs_dataset,
            variable,
            required_datasets["station_pattern"],
            periods=periods,
            selected_stations=stations,
        )
        if not req_ok:
            ft.logger.warning(
                "Requirement %s not satisfied. All related benchmarks ignored. Missing item(s): %s",
                req_name,
                miss,
            )
            wxc.log_missing_wx_station_requirements(req_name, variable, miss)
            return bench_output

    ft.logger.info("Requirement %s valid", req_name)
    for bench_id in list_benchmarks:
        ft.logger.info("Run Benchmark %s", bench_id)
        result = benchmark_functions[bench_id](model_dataset, obs_dataset, ctx)
        if isinstance(result, wx_cadence.KpiIgnored):
            ctx.setdefault("ignored_benchmarks", set()).add(bench_id)
            ctx.setdefault("ignored_reasons", {})[bench_id] = result.reason
        else:
            bench_output[bench_id] = result
    return bench_output


def _add_group(
    registry: WxRegistry,
    spec: WxForecastSpec,
    variable_spec: dict,
    requirement: str,
    cycle,
    cadence,
    lead_bin,
):
    variable = variable_spec["variable"]
    group = group_name(variable_spec["group_label"], cadence, lead_bin)
    registry.groups[group] = {"weight": _group_weight(variable_spec, lead_bin), "benchmarks": {}}
    lead_window = (cycle + timedelta(hours=lead_bin.start), cycle + timedelta(hours=lead_bin.end))
    join = {
        "lead_window": lead_window,
        "period": wx_cadence.expand_window(lead_window, spec.obs_tolerance_s),
        "cadence_hours": cadence,
        "obs_tolerance_s": spec.obs_tolerance_s,
        "model_tolerance_s": spec.model_tolerance_s,
        "min_coverage": spec.min_coverage,
    }
    for kpi in _group_kpis(variable_spec, cadence, lead_bin):
        name = " ".join(
            (variable_spec["label"], kpi["metric_label"], kpi["stat_label"], f"{cadence}h", lead_bin.label)
            + (kpi["set_label"],)
        )
        if variable_spec["family"] == FAMILY_ACCURACY:
            function = partial(
                wx_cadence.bench_wx_cadence_index,
                kpi_name_custom=name,
                wx_variable_name=variable,
                common_unit=variable_spec["common_unit"],
                metric_func=kpi["metric_func"],
                stat_func=kpi["stat_func"],
                value_norm_param_m=variable_spec["norm_m"],
                station_set=kpi["station_set"],
                **join,
            )
        elif variable_spec["family"] == FAMILY_INDEX:
            function = partial(
                wx_cadence.bench_wx_cadence_compound_index,
                kpi_name_custom=name,
                quantity=variable,
                inputs=variable_spec["inputs"],
                function=variable_spec["function"],
                metric_func=kpi["metric_func"],
                stat_func=kpi["stat_func"],
                value_norm_param_m=variable_spec["norm_m"],
                station_set=kpi["station_set"],
                **join,
            )
        else:
            function = partial(
                wx_cadence.bench_wx_cadence_event,
                kpi_name_custom=name,
                quantity=variable,
                inputs=variable_spec["inputs"],
                function=variable_spec["function"],
                metric_func=kpi["metric_func"],
                station_set=kpi["station_set"],
                **join,
            )
        registry.benchmark_functions[kpi["id"]] = function
        registry.groups[group]["benchmarks"][kpi["id"]] = kpi["weight"]
        registry.requirements[requirement]["benchmarks"].append(kpi["id"])


def _copy_groups(groups: dict, names: list[str]) -> dict:
    return {
        name: {"weight": groups[name]["weight"], "benchmarks": dict(groups[name]["benchmarks"])}
        for name in names
    }


def _target_benchmarks(scheme: dict) -> list[str]:
    benchmarks = []
    for group in scheme.values():
        for bench_id in group["benchmarks"]:
            if bench_id not in benchmarks:
                benchmarks.append(bench_id)
    return benchmarks


def _attr_text(value, default: str) -> str:
    if value is None:
        return default
    return value.decode() if isinstance(value, bytes) else str(value)
