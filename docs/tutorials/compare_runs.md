# Compare Multiple Model Runs

`firebench multirun` applies one case and target to two or more model outputs, writes each model's
normal results, and produces a comparison scorecard.

## Arrange the inputs

Paths in the YAML file are relative to the configuration file. A practical directory is:

```text
comparison/
├── Caldor.h5
├── multirun.yml
└── model_outputs/
    ├── wrf_sfire_baseline.h5
    └── wrf_sfire_calibrated.h5
```

Copy this complete configuration to `comparison/multirun.yml`:

```{literalinclude} ../examples/multirun.yml
:language: yaml
:caption: multirun.yml
```

Run it from any directory:

```bash
firebench multirun comparison/multirun.yml
```

Each model name is converted to a safe filename. The example writes
`results/wrf-sfire-baseline_rslt.json`, its PDF and log, the corresponding calibrated files, and
`results/comparison_scorecard.pdf`. `comparison_include_kpis` adds KPI rows to the comparison;
`full_name` expands identifiers in PDFs.

`overwrite: false` protects the comparison PDF from replacement. Set it to `true` only after
archiving results you need. `case`, `target`, and at least two models are required. Each model needs
a unique `name` and an existing `model_output` file. YAML must be a mapping and the extension must
be `.yml` or `.yaml`; FireBench reports these configuration errors before starting the runs.
