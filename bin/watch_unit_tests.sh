#!/usr/bin/env bash

# bin/watch_unit_tests.sh: Run test suite for project in a
# watcher/monitor mode, retesting code as file changes occur.

set -e

# Set the working directory to be the project's base directory; all
# subsequent paths are relative to that base directory.
cd "$(dirname "$0")/.."

source bin/build_variables.sh

mkdir -p "./tmp"
export PYTHONPATH="$(pwd)/app${PYTHONPATH:+:$PYTHONPATH}"

export TESTMON_DATAFILE="./tmp/.testmondata"

echo "🤖 ⟶  Running unit test…"
  poetry run ptw .
