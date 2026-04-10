#!/usr/bin/env bash

# bin/acceptance_tests.sh: Run acceptance tests for the project.

set -e

# Set the working directory to be the project's base directory; all
# subsequent paths are relative to that base directory.
cd "$(dirname "$0")/.."

mkdir -p "./tests/acceptance" "./tests/reports"
export PYTHONPATH="$(pwd)/app${PYTHONPATH:+:$PYTHONPATH}"

if ! find ./tests/acceptance -type f \( -name 'test_*.py' -o -name '*.feature' \) | grep -q .; then
  echo "🤖 ⟶  Acceptance test placeholder…"
  echo "No acceptance tests are defined yet. Add pytest-bdd scenarios under tests/acceptance."
  exit 0
fi

echo "🤖 ⟶  Running acceptance tests…"
poetry run pytest tests/acceptance \
  --junit-xml="tests/reports/xunit-result-acceptance.xml"
