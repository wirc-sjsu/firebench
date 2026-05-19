# Run the Caldor Benchmark from the CLI

This tutorial shows how to download the 2021 Caldor Fire benchmark data and run benchmark from the `firebench` command line.

## 1. Install FireBench

From the repository root, install FireBench in your Python environment:

```bash
pip install .
```

Check that the CLI is available:

```bash
firebench list
```

The Caldor Fire benchmark is case `1`, also shown as `001` (both id can be used).

## 2. Download the Caldor Fire case

Create a working directory, then download the latest data archive for case `1`:

```bash
mkdir caldor_cli_example
cd caldor_cli_example
firebench data get 1
```

The command downloads the latest registered data archive for the Caldor Fire benchmark into the current directory.
Extract the archive so that `Caldor.h5` is available in the working directory:

```bash
unzip v2026.2.zip
```

If you downloaded a different version, replace `v2026.2.zip` with the archive file that `firebench data get 1` created.

## 3. Run the benchmark

Run benchmark case `1` with the `CDI` aggregation scheme and allow existing outputs to be overwritten:

```bash
firebench run -c 1 -o -a CDI my_model_output.h5
```

This command writes the default Caldor outputs in the working directory:

- `Caldor_rslt.json`
- `Caldor.pdf`
- `Caldor.log`

Use a different model output file by replacing the final `my_model_output.h5` argument with the path to your FireBench standard HDF5 output.

## 4. Useful CLI commands

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
