#!/usr/bin/env bash

# bin/stop.sh: Stop the project and any associated services.

set -e

# Set the working directory to be the project's base directory; all
# subsequent paths are relative to that base directory.
cd "$(dirname "$0")/.."

source bin/build_variables.sh

dc()
{
  file_opts=(--file docker-compose.yml)
  if [ -z "$CI" ]; then
    file_opts+=(--file docker-compose.local.yml)
  fi

  docker compose \
    "${file_opts[@]}" \
    "$@"
}
