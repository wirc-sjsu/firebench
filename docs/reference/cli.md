# CLI Reference

The generated [Click command reference](cli_generated.rst) is the source of truth for syntax and
options. This page describes command behavior, files, and failures that are not visible in `--help`.

## Exit behavior

All commands return exit status `0` on success. Click returns a nonzero status for missing or extra
arguments, invalid option values, and `UsageError` conditions. FireBench reports user-correctable
problems—unknown cases, targets or data versions; missing files; malformed YAML; existing protected
outputs—as `Error: ...` followed by command usage. Unexpected library or I/O failures propagate so
the traceback remains available for diagnosis.

## `list`

```text
firebench list [CASE] [TARGET] [--obs-data FILE]
```

With no arguments, list registered cases. With `CASE`, list standalone targets, period syntax, and
flags. With both arguments, resolve and describe a target. `--obs-data` enables summaries that
depend on observation contents. Numeric cases are zero-padded, and registered short names are
accepted. The command writes no files.

## `data`

```text
firebench data list
firebench data versions CASE
firebench data get CASE [--version TEXT] [--output-dir DIRECTORY]
```

`list` discovers downloadable cases; `versions` prints registered versions; `get` downloads one
archive. The version defaults to `latest` and the output directory defaults to the current
directory. FireBench creates the directory but does not extract the archive. An unknown case or
version, a URL without a filename, or a network/filesystem failure is nonzero.

## `run`

```text
firebench run [OPTIONS] CASE TARGET MODEL_OUTPUT
```

The three positional arguments are required. Options are:

Option | Meaning
--- | ---
`-n`, `--name TEXT` | Model/configuration label; defaults to the model filename stem.
`-o`, `--overwrite` | Allow replacement of protected result artifacts.
`-s`, `--sign KEYID SIGNER` | Sign with a registered key ID and local GPG signer.
`-v`, `--verbose INTEGER` | `0` critical, `1` error, `2` warning, `3` info, `4+` debug.
`--log-file FILE` | Override the case log path.
`--no-console` | Disable console logging while retaining file logging.
`--obs-data FILE` | Override the observational HDF5 file.
`--output-json FILE` | Override the result JSON path.
`--score-card-report FILE` | Override the scorecard PDF path.
`--full-name`, `--full_name` | Expand benchmark IDs and KPI names in the PDF.
`--no-run` | Resolve and print selected registries without reading model output or running metrics.
`--report` | Add `firebench_report.md` and `figures/`.

Case defaults apply when path and verbosity options are omitted. The target is normalized before
execution. Missing model output, invalid targets, unmet dataset requirements, or protected existing
outputs fail nonzero. See [Output Files and Defaults](outputs.md).

## `multirun`

```text
firebench multirun CONFIG
```

`CONFIG` must be an existing `.yml` or `.yaml` mapping with `case`, `target`, and at least two model
entries. Each model needs a unique name and existing output path. Relative paths resolve against
the YAML file, not the current directory. See [Compare Multiple Model Runs](../tutorials/compare_runs.md)
for every supported key and generated file.

## `plot`

```text
firebench plot CONFIG
```

`CONFIG` is a TOML file. The command prints `Wrote PATH` for each image. Invalid tables, missing
inputs, invalid numeric settings, unresolved polygon files, or no common perimeter paths fail
nonzero. See [Generate Plots from TOML](../how_to/plot_from_toml.md).

## `wx-qc`

```text
firebench wx-qc
```

Launch the Tk weather-station QC application. It accepts no command-line options beyond
`--help`; files and sessions are selected in the application. A graphical desktop and a Python
installation with Tk support are required. See
[Review Weather-Station Data with the QC GUI](../how_to/review_weather_station_qc.md) for the input
schema, assertion semantics, review workflow, sessions, and exports.
