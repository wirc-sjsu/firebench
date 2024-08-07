---
layout: default
title: "Developers Guide"
nav_order: 8
---

# Developers Guide

## Running tests
Notes here assumes you are at the root of the project directory.

Install dependencies for tests:
```bash
pip install ".[dev]"
```
Then you can run the tests by using:
```bash
pytest tests
```
or
```bash
make test
```
If you want to get the coverage report, use:
```bash
make test-cov
```

## Building documentation locally
You need to install the package dependencies for developers.
```bash
pip install ".[dev]"
```
You should update the changelog in the docs directory by using:
```bash
make update-docs-changelog
```
You need to install [Ruby](https://www.ruby-lang.org/en/) first.
Then, you need to install `Bundller` which is required to manade dependencies.
```bash
gem install bundler
```
Then, you can install the necessary Ruby dependencies:
```bash
cd docs
bundle install
```
Finally, you can run
```bash
bundle exec jekyll serve
```
This will build the documentation, and give you an adress to access it like `Server address: http://127.0.0.1:4000/`.


## Linting
You can get the pylint score by using:
```bash
make lint
```
If you need to update the linting score badge, use:
```bash
make update-lint-score
```

## Code formatting
The following line will use `black --line-length 108` on `src/firebench`, `tests`, `.github/actions`, and `workflow`.
```bash
make code-formatting
```

## Security check
You can run the security check using Bandit:
```bash
make bandit
```


