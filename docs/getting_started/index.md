# Getting Started

This section takes you from a clean Python environment to a working FireBench command. The
detailed Caldor tutorial continues from here with benchmark data, target selection, and a complete
benchmark run.

## Install FireBench

FireBench supports Python 3.10 and later. Clone the repository, create an isolated environment,
and install the package:

```bash
git clone https://github.com/wirc-sjsu/firebench.git
cd firebench
python -m venv .venv
source .venv/bin/activate
python -m pip install .
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

## Verify the installation

List the registered benchmark cases:

```bash
firebench list
```

Then inspect the Caldor case and its available targets:

```bash
firebench list 2021_Caldor
```

These commands do not download data or write benchmark results. Continue with
[Run the Caldor Benchmark from the CLI](../tutorials/cli_caldor_benchmark.md) to download the
observational package and run a target against model output.
