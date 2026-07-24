# FireBench

<div style="text-align: center;">
    <img src="docs/_static/images/firebench_logo.png" alt="FireBench Logo" width="300"/>
</div>

<div style="height: 20px;"></div> <!-- Adds a blank space -->

[![CI](https://github.com/wirc-sjsu/firebench/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/wirc-sjsu/firebench/actions/workflows/ci.yml)
[![pages-build-deployment](https://github.com/wirc-sjsu/firebench/actions/workflows/pages/pages-build-deployment/badge.svg?branch=main)](https://github.com/wirc-sjsu/firebench/actions/workflows/pages/pages-build-deployment)
[![codecov](https://codecov.io/github/wirc-sjsu/firebench/graph/badge.svg?token=8F44OX12EW)](https://codecov.io/github/wirc-sjsu/firebench)
[![Security Analysis](https://github.com/wirc-sjsu/firebench/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/wirc-sjsu/firebench/actions/workflows/security.yml)
![Pylint Score](https://img.shields.io/badge/Pylint-9.60-brightgreen.svg)
[![Check linting with Pylint](https://github.com/wirc-sjsu/firebench/actions/workflows/pylint.yml/badge.svg?branch=main)](https://github.com/wirc-sjsu/firebench/actions/workflows/pylint.yml)
[![Black Code Formatting Check](https://github.com/wirc-sjsu/firebench/actions/workflows/black.yml/badge.svg?branch=main)](https://github.com/wirc-sjsu/firebench/actions/workflows/black.yml)
![GitHub License](https://img.shields.io/github/license/wirc-sjsu/firebench)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.15477459.svg)](https://doi.org/10.5281/zenodo.15477459)

FireBench is an open-source Python library for systematic, transparent, and reproducible
benchmarking and intercomparison of fire models. It provides standardized model-output formats,
benchmark datasets, metrics, normalization, scorecards, and command-line workflows.

## Quick Start

```bash
git clone https://github.com/wirc-sjsu/firebench.git
cd firebench
python -m venv .venv
source .venv/bin/activate
python -m pip install .
firebench list
```

For environment setup, benchmark data, target selection, and complete workflows, use the
[FireBench documentation](https://firebench.readthedocs.io/en/latest/).

## Documentation

- [Getting Started](https://firebench.readthedocs.io/en/latest/getting_started/index.html)
- [Run the Caldor benchmark](https://firebench.readthedocs.io/en/latest/tutorials/cli_caldor_benchmark.html)
- [Prepare standard model output](https://firebench.readthedocs.io/en/latest/standard_format.html)
- [Reference and Concepts](https://firebench.readthedocs.io/en/latest/reference/index.html)

Questions and ideas are welcome in [GitHub Discussions](https://github.com/wirc-sjsu/firebench/discussions).
See the [contribution guide](docs/contribute.md) to contribute code, data, documentation, or workflows.
