#!/usr/bin/env bash

# bin/acceptance_tests.sh: Placeholder acceptance test runner for the project.

set -e

# Set the working directory to be the project's base directory; all
# subsequent paths are relative to that base directory.
cd "$(dirname "$0")/.."

mkdir -p "./tests/acceptance"

echo "🤖 ⟶  Acceptance test placeholder…"
echo "No acceptance tests are defined yet. Add pytest-bdd scenarios under tests/acceptance."
