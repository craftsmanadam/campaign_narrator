#!/usr/bin/env bash

# bin/build_variables.sh: Sets any required env vars.

set -e

export PROJECT_NAME="$(poetry version | awk {'print $1'})"
export IMAGE_NAME=craftsmanadam/${PROJECT_NAME}
export VERSION="$(poetry version --short)"
export APPLICATION_DIR="./app"
export MIN_COVERAGE_PERCENTAGE=90
export COVERAGE_FILE="./tmp/.coverage"

# A way to echo that will respect escape sequences.
puts()
{
  echo -e "$1"
}

# Shortcut for the `docker compose` command.
dc()
{
  file_opts=(--file docker-compose.yml)
  if [ -z "$CI" ]; then
    file_opts+=(--file docker-compose.local.yml)
  fi
  COMPOSE_BAKE=true docker compose \
    "${file_opts[@]}" \
    "$@"
}

OS="$(uname -s)"
if [ "${OS}" = "Linux" ]; then
  export GREEN='\e[32m'
  export BLUE='\e[34m'
  export PURPLE="\e[35m"
  export YELLOW='\e[0;33m'
  export RED='\e[31m'
  export RESET='\e[0m'
elif [ "${OS}" = "Darwin" ]; then
  export GREEN='\033[32m'
  export BLUE='\033[34m'
  export PURPLE="\033[35m"
  export YELLOW='\033[33m'
  export RED='\033[31m'
  export RESET='\033[m'
fi
