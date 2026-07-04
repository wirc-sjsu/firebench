from pathlib import Path

from . import c001_caldor

AVAIL_BENCHMARKS = {
    "001": {
        "name": "2021 Caldor Fire",
        "short_name": "2021_Caldor",
        "url": "https://firebench.readthedocs.io/en/latest/benchmarks/California/01_Caldor.html",
        "func": c001_caldor.run_caldor_benchmark,
        "debug_func": c001_caldor.print_benchmark_registry,
        "target_normalizer": c001_caldor.normalize_benchmark_target,
        "default_options": {
            "verbose": c001_caldor.DEFAULT_VERBOSITY,
            "log_file": Path(c001_caldor.LOG_FILENAME),
            "obs_data": c001_caldor.DEFAULT_OBS_DATA_PATH,
            "output_json": c001_caldor.DEFAULT_OUTPUT_PATH_JSON,
            "score_card_report": c001_caldor.DEFAULT_SCORE_CARD_REPORT_PATH,
        },
        "data": {
            "latest": "https://zenodo.org/records/20279621/files/v2026.2.zip?download=1",
            "2026.2": "https://zenodo.org/records/20279621/files/v2026.2.zip?download=1",
            "2026.1": "https://zenodo.org/records/19041000/files/v2026.1.zip?download=1",
            "2026.0": "https://zenodo.org/records/18250104/files/2021_Caldor_v1.0.0.zip?download=1",
        },
    },
}
