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


AVAIL_BENCHMARKS = {
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
            "latest": "https://zenodo.org/records/20279621/files/v2026.2.zip?download=1",
            "2026.2": "https://zenodo.org/records/20279621/files/v2026.2.zip?download=1",
            "2026.1": "https://zenodo.org/records/19041000/files/v2026.1.zip?download=1",
            "2026.0": "https://zenodo.org/records/18250104/files/2021_Caldor_v1.0.0.zip?download=1",
        },
    },
}
