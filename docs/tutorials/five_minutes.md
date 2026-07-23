# FireBench in Five Minutes

This first run uses the Caldor observational file as both the reference and model input. It is a
smoke test that should produce perfect scores; replace it with real model output afterward.

## 1. Install in a clean environment

FireBench supports Python 3.10 through 3.14.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install firebench
```

Use the [source-install instructions](../getting_started/index.md#install-for-development) when
working from an unreleased revision.

## 2. Discover the benchmark

```bash
firebench list
```

The table contains the numeric case ID, its short name, and the specification URL. Caldor accepts
`1`, `001`, or `2021_Caldor` wherever a case is required.

## 3. Download the data

```bash
mkdir firebench-first-run
cd firebench-first-run
firebench data versions 1
firebench data get 1
unzip v2026.2.zip
```

Use the archive name printed by `data get` if `latest` points to a newer release.

## 4. Select a target

```bash
firebench list 2021_Caldor
firebench list 2021_Caldor H013_P --obs-data Caldor.h5
```

`H013` is a 48-hour period and `P` selects the perimeter KPI group. The second command displays the
exact dates, perimeters, KPI weights, and normalization parameters before any work is run.

## 5. Run the smoke test

```bash
firebench run 2021_Caldor H013_P Caldor.h5 --obs-data Caldor.h5
```

The working directory now contains:

- `Caldor_rslt.json`, the machine-readable metrics, unit scores, group score, and total score;
- `Caldor.pdf`, the human-readable scorecard;
- `Caldor.log`, the selected checks, benchmark progress, warnings, and output paths.

The total should be `1.0` because the same values were compared. A real result below `1.0` is not
by itself good or bad: interpret it alongside the selected KPIs, normalization, weights, and model
purpose.

Next, [prepare model output](prepare_model_output.md), then follow the
[detailed Caldor tutorial](cli_caldor_benchmark.md) with your own file.
