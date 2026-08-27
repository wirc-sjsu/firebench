# Developer Guide

## Set Up a Development Environment

From the repository root, create an isolated environment and install the source tree, tests, and
documentation tools in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,docs]"
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

## Run Tests

```bash
pytest tests
```

```bash
make test
```

### Coverage Report

```bash
make test-cov
```

## Building Documentation Locally

### Update Changelog

```bash
make update-docs-changelog
```

### Build Documentation

```bash
make docs
```

This builds HTML in `docs/_build/html`. CI treats Sphinx warnings as errors; reproduce that check
locally with `make docs-strict`. Check external links separately with `make docs-linkcheck` because
remote services can be intermittent.

Preview the result at `http://localhost:8000`:

```bash
python -m http.server --directory docs/_build/html 8000
```

See [Preview the Documentation Locally with WSL](tutorials/preview_documentation_wsl.md) for a
complete Windows and WSL walkthrough.

## Linting

### Get Pylint Score

```bash
make lint
```

### Update Linting Score Badge

```bash
make update-lint-score
```

## Code Formatting

The following command will use `black` with a line length of 108 on directories that contains the main code sources:

```bash
make code-formatting
```

## Security Check

Run a security check using Bandit:

```bash
make bandit
```
