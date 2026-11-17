from importlib import import_module
from pathlib import Path

from . import c001_caldor_config as caldor_config
from .c001_caldor_discovery import describe_available_targets_summary


def _call_caldor(attribute, *args, **kwargs):
    return getattr(import_module(".c001_caldor", __package__), attribute)(*args, **kwargs)


def _run_caldor_benchmark(*args, **kwargs):
    return _call_caldor("run_caldor_benchmark", *args, **kwargs)


def _print_caldor_registry(*args, **kwargs):
    return _call_caldor("print_benchmark_registry", *args, **kwargs)


def _normalize_caldor_target(*args, **kwargs):
    return _call_caldor("normalize_benchmark_target", *args, **kwargs)


def _describe_caldor_targets(benchmark_target=None, obs_data=None):
    if benchmark_target is None:
        return describe_available_targets_summary()
    return _call_caldor(
        "describe_available_targets",
        benchmark_target,
        obs_data=obs_data,
    )


def _create_caldor_report_figures(*args, **kwargs):
    return _call_caldor("create_report_figures", *args, **kwargs)


def _run_fmc_benchmark(model_output, *, benchmark_target, score_card_full_name=False, **kwargs):
    return import_module(".fmc", __package__).run_fmc_benchmark(
        model_output, benchmark_target=benchmark_target, score_card_full_name=score_card_full_name, **kwargs
    )


def _normalize_fmc_target(target):
    if target.upper() not in ("ALL", "A"):
        raise ValueError("Unknown FMC target; use ALL.")
    return "ALL"


def _describe_fmc_targets(target=None, obs_data=None):
    groups = {
        "FMC": "Fuel moisture: sampling events for live fuels, daily means for dead fuels; "
        "hourly and native comparisons are diagnostic"
    }
    if target is not None:
        return {
            "target": _normalize_fmc_target(target),
            "kpi_groups": groups,
            "kpis": [
                {
                    "id": "FMC-<series>-<scale>-<metric>",
                    "name": "MAE, RMSE and bias (percentage points)",
                    "weight": None,
                    "value_norm_param_m_definition": "--mae-half-score-pp",
                }
            ],
        }
    return {
        "standalone_targets": {"ALL": "All observed FMC station/fuel/variation series"},
        "period_target_syntax": "not applicable",
        "periods": [],
        "kpi_groups": groups,
    }


def _print_fmc_registry(benchmark_target):
    print(f"FMC target: {_normalize_fmc_target(benchmark_target)}")
    print("All observed station/fuel/variation series: MAE, RMSE, bias.")
    print("Primary: live sampling events, dead daily means; diagnostics: hourly and native.")


AVAIL_BENCHMARKS = {
    "FMC": {
        "name": "Station Fuel Moisture",
        "short_name": "Fuel_Moisture",
        "url": "https://firebench.readthedocs.io/en/latest/how_to/fuel_moisture.html",
        "func": _run_fmc_benchmark,
        "target_normalizer": _normalize_fmc_target,
        "target_describer": _describe_fmc_targets,
        "debug_func": _print_fmc_registry,
        "run_options": ("mae_half_score_pp", "event_tolerance_seconds"),
        "required_run_options": ("mae_half_score_pp",),
        "default_options": {
            "verbose": 2,
            "log_file": Path("fmc.log"),
            "output_json": Path("fmc_results.json"),
            "score_card_report": Path("fmc_scorecard.pdf"),
        },
    },
    "001": {
        "name": "2021 Caldor Fire",
        "short_name": caldor_config.BENCHMARK_SHORT_NAME,
        "url": "https://firebench.readthedocs.io/en/latest/benchmarks/California/01_Caldor.html",
        "func": _run_caldor_benchmark,
        "debug_func": _print_caldor_registry,
        "target_normalizer": _normalize_caldor_target,
        "target_describer": _describe_caldor_targets,
        "report_figure_func": _create_caldor_report_figures,
        "default_options": {
            "verbose": caldor_config.DEFAULT_VERBOSITY,
            "log_file": Path(caldor_config.LOG_FILENAME),
            "obs_data": caldor_config.DEFAULT_OBS_DATA_PATH,
            "output_json": caldor_config.DEFAULT_OUTPUT_PATH_JSON,
            "score_card_report": caldor_config.DEFAULT_SCORE_CARD_REPORT_PATH,
        },
        "data": {
            "latest": "https://zenodo.org/records/23383592/files/v2026.3.zip?download=1",
            "2026.3": "https://zenodo.org/records/23383592/files/v2026.3.zip?download=1",
            "2026.2": "https://zenodo.org/records/20279621/files/v2026.2.zip?download=1",
            "2026.1": "https://zenodo.org/records/19041000/files/v2026.1.zip?download=1",
            "2026.0": "https://zenodo.org/records/18250104/files/2021_Caldor_v1.0.0.zip?download=1",
        },
    },
}
