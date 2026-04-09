#!/usr/bin/env bash

# bin/unit_tests.sh: Run test suite for project.

set -e

# Set the working directory to be the project's base directory; all
# subsequent paths are relative to that base directory.
cd "$(dirname "$0")/.."

source bin/build_variables.sh

mkdir -p "./tmp"
export PYTHONPATH="$(pwd)/app${PYTHONPATH:+:$PYTHONPATH}"

echo "🤖 ⟶  Running unit test…"
  poetry run pytest tests/unit \
    --cov="$APPLICATION_DIR" \
    --cov-report=term-missing \
    --cov-report=xml:tests/reports/coverage.xml \
    --cov-fail-under=$MIN_COVERAGE_PERCENTAGE \
    --junit-xml="tests/reports/xunit-result-unit.xml"
