# Declare these targets as phony to avoid conflicts with files of the same name
.PHONY: test test-cov lint update-lint-score code-formatting bandit update-docs-changelog check-consistency-namespace generate-api-doc docs clean clean-build install-build-tools build check-dist upload-test upload

PYTHON ?= python

# Run all tests without coverage report
test:
	pytest tests

# Run all tests with coverage report
test-cov:
	pytest --cov-report term-missing --cov=src/firebench

# Run pylint analysis
lint:
	pylint src/firebench --rcfile=.pylintrc

# Update pylint score in README.md
update-lint-score:
	python .github/actions/run_pylint.py

# Run black code formatting
code-formatting:
	black --line-length 108 src/firebench
	black --line-length 108 tests
	black --line-length 108 .github/actions
	black --line-length 108 workflow

# Run bandit analysis
bandit:
	bandit -r src/firebench --severity-level high --confidence-level high

# Update documentation
update-docs-changelog:
	python .github/actions/update_changelog_in_docs.py

# Check consistency between namespace in package and in docs
check-consistency-namespace:
	python .github/actions/check_namespace_file_consistency.py

# Update API documentation
generate-api-doc:
	python .github/actions/generate_api_docs.py

# generate local documentation
docs:
	sphinx-build -b html docs docs/_build/html

# Remove package build artifacts
clean-build:
	rm -rf build
	rm -rf dist
	rm -rf *.egg-info
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} +

# Install package build and upload tools
install-build-tools:
	$(PYTHON) -m pip install --upgrade build twine

# Build source and wheel distributions
build: clean-build
	$(PYTHON) -m build

# Validate built distributions
check-dist: build
	$(PYTHON) -m twine check dist/*

# Upload distributions to TestPyPI
upload-test: check-dist
	$(PYTHON) -m twine upload --repository testpypi dist/*

# Upload distributions to PyPI
upload: check-dist
	$(PYTHON) -m twine upload dist/*

# generate local documentation
clean:
	rm -rf docs/_build
