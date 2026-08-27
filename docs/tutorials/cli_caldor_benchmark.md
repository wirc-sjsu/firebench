# Run the Caldor Benchmark from the CLI

This tutorial shows how to download the 2021 Caldor Fire benchmark data and run a benchmark from
the `firebench` command line.

## 1. Install FireBench

From the repository root, install FireBench in your Python environment:

```bash
pip install .
```

Check that the CLI is available:

```bash
firebench list
```

The Caldor Fire benchmark is case `1`, also shown as `001`; either identifier can be used.

## 2. Download the Caldor Fire case

Create a working directory, then download the latest data archive for case `1`:

```bash
mkdir caldor_cli_example
cd caldor_cli_example
firebench data get 1
```

The command downloads the latest registered data archive for the Caldor Fire benchmark into the
current directory. Extract the archive; its files remain together under the versioned `v2026.2/`
directory:

```bash
unzip v2026.2.zip
```

If you downloaded a different version, replace `v2026.2` in both the archive name and the extracted
directory paths below with the version that `firebench data get 1` created.

## 3. Inspect the case and target

List the Caldor standalone targets, period syntax, available periods, and combinable KPI-group
flags:

```bash
firebench list 2021_Caldor
```

This tutorial uses `H013_P`, which selects only the fire-perimeter KPIs in the 48-hour HRRR-aligned
period `H013`. Inspect its period, perimeters, KPI weights, and normalization parameters before
running it:

```bash
firebench list 2021_Caldor H013_P --obs-data v2026.2/Caldor.h5
```

`H013_P` is a small perimeter-only example. It is not equivalent to the former `CDI` tutorial
command: `CDI` includes building damage, three curated perimeter periods, and passive weather
checks. Use `firebench list 2021_Caldor CDI --obs-data v2026.2/Caldor.h5` to inspect that retained
scheme.

To inspect weather KPIs, use a curated or HRRR-aligned target with `T` for TSO only or `W` for TSO
plus all sources:

```bash
firebench list 2021_Caldor P02_T --obs-data v2026.2/Caldor.h5
firebench list 2021_Caldor H013_W --obs-data v2026.2/Caldor.h5
```

TSO uses only confidence-level-2 sensor heights and is the scored mode. The `W` flag additionally
runs all-sources KPIs, which include TSO plus confidence levels 0 and 1. They are zero-weight
diagnostics, not an untrusted-only comparison. The detailed listing shows the generated KPI IDs,
station counts, weights, and normalization parameters. See
[Weather Sensor Height and Trust](../reference/weather_sensor_height.md) before preparing weather
model output.

## 4. Run the benchmark

Run benchmark case `2021_Caldor` with target `H013_P` and allow existing outputs to be overwritten:

```bash
firebench run 2021_Caldor H013_P my_model_output.h5 --obs-data v2026.2/Caldor.h5 -o
```

This command writes the default Caldor outputs in the working directory:

- `Caldor_rslt.json`
- `Caldor.pdf`
- `Caldor.log`

Use a different model output file by replacing `my_model_output.h5` with the path to your FireBench
standard HDF5 output. If you do not have model output yet, use the
observational dataset `v2026.2/Caldor.h5` as both model output and observations to produce a perfect
scorecard for a smoke test. In this exact same-file case, FireBench accepts the legacy numeric-string
sensor heights stored by released observation packages. Separate model files must use canonical
numeric sensor-height attributes.

For a TSO-only weather run, replace the target with `P02_T` or `H013_T`. Use `W` when the
zero-weight all-sources diagnostics are also wanted:

```bash
firebench run 2021_Caldor H013_T my_model_output.h5 --obs-data v2026.2/Caldor.h5 -o
```

Model values processed by TSO must be prepared at the trusted sensor height stored on the matching
observational variable, including when using height-aware wind interpolation.

The 0.10 positional syntax is `firebench run CASE TARGET MODEL_OUTPUT`. In FireBench 0.9 the same
parts were supplied as `firebench run -c CASE -a SCHEME MODEL_OUTPUT`; the `-c` and `-a` options
have been removed.

## 5. Useful CLI commands

Main helpers

```bash
firebench --help
firebench list --help
firebench data --help
firebench run --help
```

List all benchmark cases:

```bash
firebench list
```

List available Caldor data versions:

```bash
firebench data versions 1
```

Download a specific Caldor data version:

```bash
firebench data get 1 --version 2026.1
```
