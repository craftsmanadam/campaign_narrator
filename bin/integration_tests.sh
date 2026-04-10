#!/usr/bin/env bash

# bin/integration_tests.sh: Run integration tests for the project.

set -e

# Set the working directory to be the project's base directory; all
# subsequent paths are relative to that base directory.
cd "$(dirname "$0")/.."

mkdir -p "./tests/integration" "./tests/reports"
export PYTHONPATH="$(pwd)/app${PYTHONPATH:+:$PYTHONPATH}"

if ! find ./tests/integration -type f \( -name 'test_*.py' -o -name '*.feature' \) | grep -q .; then
  echo "🤖 ⟶  Integration test placeholder…"
  echo "No integration tests are defined yet. Add tests under tests/integration."
  exit 0
fi

echo "🤖 ⟶  Running integration tests…"
poetry run pytest tests/integration \
  --junit-xml="tests/reports/xunit-result-integration.xml"
