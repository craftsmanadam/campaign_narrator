#!/usr/bin/env bash

# bin/clean.sh: Clean up the project, including any temporary files.

set -e

# Set the working directory to be the project's base directory; all
# subsequent paths are relative to that base directory.
cd "$(dirname "$0")/.."

source bin/build_variables.sh

if [[  -d "tmp" ]];then
    echo "🤖 ⟶  Removing tmp directory…"
    rm -rf tmp
fi

if [[  -d "venv" ]];then
    echo "🤖 ⟶  Removing venv subdirectory…"
    rm -rf venv
fi

if [[  -d ".venv" ]];then
    echo "🤖 ⟶  Removing .venv subdirectory…"
    rm -rf .venv
fi

if [[ $(poetry env list) ]];then
    echo "🤖 ⟶  Removing Poetry env…"
    poetry env remove "$(poetry env info --path)/bin/python"
fi

if [[  -d ".pytest_cache" ]];then
    echo "🤖 ⟶  Removing .pytest_cache subdirectory…"
    rm -rf .pytest_cache
fi

echo "🤖 ⟶  Removing __pycache__ subdirectories…"
find . -type d -name "__pycache__" -exec rm -r "{}" \; -prune

echo "🤖 ⟶  Cleaning up docker…"
docker system prune -f
