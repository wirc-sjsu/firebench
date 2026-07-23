# Output Files and Defaults

Paths are relative to the current directory unless an option or configuration file supplies
another location.

Workflow | Default output | Replacement behavior
--- | --- | ---
Single Caldor run | `Caldor_rslt.json`, `Caldor.pdf`, `Caldor.log` | Existing benchmark outputs require `--overwrite`.
Run report | `firebench_report.md`, `figures/` | Existing report requires `--overwrite`; the directory is reused.
Data download | URL filename under `--output-dir` (default `.`) | Download behavior is delegated to the URL retrieval operation.
Multirun model | `OUTPUT_DIR/MODEL-SLUG_rslt.json`, `_scorecard.pdf`, and `.log` | Controlled by YAML `overwrite`.
Multirun comparison | `OUTPUT_DIR/comparison_scorecard.pdf` | Existing file requires YAML `overwrite: true`.
Plot | One safe-name PNG per common perimeter under configured `output_dir` | Matplotlib writes the configured output path.

`run` supports explicit `--output-json`, `--score-card-report`, and `--log-file` paths. `multirun`
always derives individual names from model labels and accepts a configurable
`comparison_score_card_report`. The `plot` output directory is required in TOML.

Logs contain selection, validation, progress, warnings, and output locations. JSON is the
machine-readable record; PDF is a presentation derived from its scorecard. Preserve the model
output, observations, FireBench version, configuration, JSON, PDF, and log together when publishing
a result.
