#!/usr/bin/env bash

# bin/format.sh: Run code formatting on the project.

set -e

# Set the working directory to be the project's base directory; all
# subsequent paths are relative to that base directory.
cd "$(dirname "$0")/.."

echo "🤖 ⟶  Running linter with autofix…"
poetry run ruff check --fix .
poetry run ruff check --fix --select UP

echo "🤖 ⟶  Formatting code…"
poetry run ruff format .
