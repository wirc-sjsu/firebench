# Declare these targets as phony to avoid conflicts with files of the same name
.PHONY: test test-cov lint update-lint-score code-formatting bandit

# Run all tests without coverage report
test:
	pytest tests

# Run all tests with coverage report
test-cov:
	pytest --cov=src/firebench

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

# Run bandit analysis
bandit:
	bandit -r src/firebench --severity-level high --confidence-level high
