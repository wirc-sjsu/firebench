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

VARIABLE_CODES = {
    "air_temperature": "AT",
    "relative_humidity": "RH",
    "wind_speed": "WS",
    "wind_direction": "WD",
    "fuel_moisture_content_10h": "FM10",
}
METRICS = {
    "standard": (
        ("MAE", "MAE", fm.stats.mae),
        ("RMSE", "RMSE", fm.stats.rmse),
        ("Bias", "BIAS", fm.stats.bias),
    ),
    "wind_direction": (("circular bias", "CBIAS", fm.stats.circular_bias_deg),),
}
SUMMARY_STATS = (("min", np.nanmin), ("mean", np.nanmean), ("max", np.nanmax))
STATION_SETS = (
    ("TSO", "TSO", fs.WeatherStationSet.TSO, 1),
    ("All sources", "ALL", fs.WeatherStationSet.ALL_SOURCES, 0),
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

    for variable_spec in WX_VARIABLE_SPECS:
        variable = variable_spec["variable"]
        if variable not in spec.variables:
            continue
        if model_variables is not None and variable not in model_variables:
            registry.excluded.append({"variable": variable, "reason": "no model data"})
            continue
        if obs_variables is not None and variable not in obs_variables:
            registry.excluded.append({"variable": variable, "reason": "no observation"})
            continue

        requirement = f"R-{VARIABLE_CODES[variable]}"
        registry.requirements[requirement] = {
            "main": partial(
                _weather_requirement, req_name=requirement, benchmark_functions=registry.benchmark_functions
            ),
            "benchmarks": [],
            "required_datasets": {"station_pattern": "station_", "variable": variable},
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
    registry.groups[group] = {"weight": 0 if lead_bin.informational else 1, "benchmarks": {}}
    lead_window = (cycle + timedelta(hours=lead_bin.start), cycle + timedelta(hours=lead_bin.end))
    period = wx_cadence.expand_window(lead_window, spec.obs_tolerance_s)
    for metric_label, metric_code, metric_func in METRICS[variable_spec["metric_set"]]:
        for set_label, set_code, station_set, weight in STATION_SETS:
            for stat_label, stat_func in SUMMARY_STATS:
                bench_id = benchmark_id(variable, metric_code, stat_label, set_code, cadence, lead_bin)
                registry.benchmark_functions[bench_id] = partial(
                    wx_cadence.bench_wx_cadence_index,
                    kpi_name_custom=" ".join(
                        (
                            variable_spec["label"],
                            metric_label,
                            stat_label,
                            f"{cadence}h",
                            lead_bin.label,
                            set_label,
                        )
                    ),
                    lead_window=lead_window,
                    period=period,
                    wx_variable_name=variable,
                    common_unit=variable_spec["common_unit"],
                    metric_func=metric_func,
                    stat_func=stat_func,
                    value_norm_param_m=variable_spec["norm_m"],
                    station_set=station_set,
                    cadence_hours=cadence,
                    obs_tolerance_s=spec.obs_tolerance_s,
                    model_tolerance_s=spec.model_tolerance_s,
                    min_coverage=spec.min_coverage,
                )
                registry.groups[group]["benchmarks"][bench_id] = weight
                registry.requirements[requirement]["benchmarks"].append(bench_id)


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
