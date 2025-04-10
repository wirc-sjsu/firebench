# 8. Developer's Guide

## Running Tests

To run tests, ensure you are at the root of the project directory.

### Install Dependencies

```bash
pip install ".[dev]"
```

### Run Tests

```bash
pytest tests
```

or

```bash
make test
```

### Coverage Report

```bash
make test-cov
```

## Building Documentation Locally

### Install Dependencies

```bash
pip install ".[dev]"
cd docs
pip install -r requirements.txt
```

### Update Changelog

```bash
make update-docs-changelog
```

### Serve Documentation

```bash
make clean && make docs
```
This will build the documentation in `docs/_build`

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
