---
layout: default
title: "Developer's Guide"
nav_order: 98
---

# Developer's Guide

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
```

### Update Changelog

```bash
make update-docs-changelog
```

### Install Ruby and Bundler

- [Install Ruby](https://www.ruby-lang.org/en/)
- Install Bundler:
  ```bash
  gem install bundler
  ```

### Install Ruby Dependencies

```bash
cd docs
bundle install
```

### Serve Documentation

```bash
bundle exec jekyll serve
```

This will build the documentation and provide an address like `http://127.0.0.1:4000/`.

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
