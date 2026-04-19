#!/usr/bin/env bash
# bin/stop_local.sh: Stop the local Ollama instance.

set -e
cd "$(dirname "$0")/.."

docker compose -f docker-compose.local.yml down
echo "Ollama stopped."
