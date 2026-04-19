#!/usr/bin/env bash
# bin/clear_state.sh: Remove all local runtime state (actors, campaign, memory, lancedb).

set -e
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a && source .env && set +a
fi

DATA_ROOT="${DATA_ROOT:-tmp/data_store}"

if [ ! -d "$DATA_ROOT" ]; then
  echo "Nothing to clear — $DATA_ROOT does not exist."
  exit 0
fi

rm -rf "${DATA_ROOT:?}"/*
echo "State cleared: $DATA_ROOT"
