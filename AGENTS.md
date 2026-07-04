# Repository Guidelines

## Project Structure & Module Organization

FireBench is a Python package using a `src/` layout. Core library code lives in `src/firebench/`, with CLI entry points in `src/firebench/cli.py`, benchmark implementations under `src/firebench/benchmarks/`, and reusable tools, metrics, plotting, signing, and standardization modules in their matching subpackages. Tests are split into `tests/unit/`, `tests/func/`, and `tests/regression/`. Documentation is in `docs/`, static documentation assets in `docs/_static/`, benchmark and fuel-model data in `data/`, and analysis workflows in `workflow/`.

## Build, Test, and Development Commands

- `make test`: run the full test suite with `pytest tests`.
- `pytest tests/unit/test_cli.py`: run a focused test file during CLI work.
- `make test-cov`: run tests with terminal coverage for `src/firebench`.
- `make code-formatting`: check Black formatting.
- `make fix-code-formatting`: apply Black formatting to source, tests, actions, and workflows.
- `make lint`: run `pylint src/firebench --rcfile=.pylintrc`.
- `make bandit`: run high-severity Bandit security checks.
- `make docs`: build local Sphinx docs into `docs/_build/html`.
- `make check-dist`: build and validate source and wheel distributions.

## Coding Style & Naming Conventions

Use Python 3.10+ syntax compatible with the supported versions in `pyproject.toml`. Format Python code with Black using the configured 108-character line length. Prefer clear module-level functions for benchmark utilities and keep CLI behavior in `src/firebench/cli.py`. Use snake_case for functions, variables, modules, and test names; use UPPER_CASE for constants such as default paths and benchmark IDs.

## Testing Guidelines

Tests use `pytest`. Place fast behavioral checks in `tests/unit/`, workflow-level checks in `tests/func/`, and stability/hash checks in `tests/regression/`. Name test files `test_*.py` and test functions `test_*`. When changing a CLI option, add or update `CliRunner` coverage in `tests/unit/test_cli.py`. Run the narrowest relevant tests first, then `make test` before broader changes are submitted.

## Commit & Pull Request Guidelines

Recent commits use short, imperative, lower-case summaries, for example `fix perimeter extraction` or `add firebench data list cli to reproduce firebench list cli`. Keep commits focused on one logical change. Pull requests should describe the user-visible behavior, list tests run, link related issues when applicable, and include documentation or example command updates for CLI, benchmark, or data workflow changes.
Add a short `CHANGELOG.md` entry under `[Unreleased]` for user-visible features, fixes, deprecations, and behavior changes.

## Commit Message Workflow

Before committing, propose a short commit message and wait for maintainer approval. Use lower-case, imperative wording such as `add report skeleton option and contributor guide`. Never create a commit without explicit approval for that exact message, and do not push from this repository. The main development branch is `dev-metrics`; advanced work should move to `develop` by pull request, then later to `master` by pull request.

## Security & Configuration Tips

Do not commit generated build artifacts, local logs, downloaded benchmark archives, or private signing keys. Use explicit paths for benchmark data and outputs when testing commands that write files, and avoid overwriting existing benchmark results unless the change specifically exercises `--overwrite` behavior.
