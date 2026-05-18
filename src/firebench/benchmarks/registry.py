from pathlib import Path

from . import c001_caldor

AVAIL_BENCHMARKS = {
    "001": {
        "name": "2021 Caldor Fire",
        "url": "https://firebench.readthedocs.io/en/latest/benchmarks/California/01_Caldor.html",
        "func": c001_caldor.run_caldor_benchmark,
        "default_options": {
            "agg_scheme": c001_caldor.DEFAULT_AGGREGATION_SCHEME,
            "verbose": c001_caldor.DEFAULT_VERBOSITY,
            "log_file": Path(c001_caldor.LOG_FILENAME),
            "obs_data": c001_caldor.DEFAULT_OBS_DATA_PATH,
            "output_json": c001_caldor.DEFAULT_OUTPUT_PATH_JSON,
            "score_card_report": c001_caldor.DEFAULT_SCORE_CARD_REPORT_PATH,
        },
    },
}
