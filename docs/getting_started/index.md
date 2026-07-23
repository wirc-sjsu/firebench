# Getting Started

This section takes you from a clean Python environment to a working FireBench command. The
detailed Caldor tutorial continues from here with benchmark data, target selection, and a complete
benchmark run.

## Requirements

FireBench supports CPython 3.10 through 3.14. Use a virtual environment so its geospatial and
scientific dependencies do not conflict with other projects. The commands below work in a clean
shell on macOS and Linux; on Windows PowerShell, replace the activation command with
`.venv\Scripts\Activate.ps1`.

## Install a released version

Create and activate an environment, update the packaging tools, and install FireBench from PyPI:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install firebench
```

If the release is not yet available on PyPI, install the current repository revision directly:

```bash
python -m pip install "firebench @ git+https://github.com/wirc-sjsu/firebench.git"
```

## Install for development

Contributors need an editable source checkout and the development dependencies:

```bash
git clone https://github.com/wirc-sjsu/firebench.git
cd firebench
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,docs]"
```

See the [developer guide](../developers.md) for tests, formatting, and documentation commands.

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
[FireBench in Five Minutes](../tutorials/five_minutes.md) for a complete first run, or use
[Run the Caldor Benchmark from the CLI](../tutorials/cli_caldor_benchmark.md) to explore the
observational package and run a target against model output.
