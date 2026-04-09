#!/usr/bin/env bash

# bin/analyze_code.sh: Run linting and code formatting on the project.

set -e

# Set the working directory to be the project's base directory; all
# subsequent paths are relative to that base directory.
cd "$(dirname "$0")/.."

source bin/build_variables.sh

echo "🤖 ⟶  Running linter…"
poetry run ruff check .

echo "🤖 ⟶  Checking security…"
poetry run ruff check . --select S

echo "🤖 ⟶  Checking code format…"
poetry run ruff format --check .
