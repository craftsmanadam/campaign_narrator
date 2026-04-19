#!/usr/bin/env bash
# bin/run_local.sh: Start Ollama locally and run the CLI in interactive mode.
#
# Usage:
#   bin/run_local.sh              # loads .env
#   bin/run_local.sh --env openai # loads .env.openai

set -e
cd "$(dirname "$0")/.."

source bin/build_variables.sh

# Parse --env flag
ENV_SUFFIX=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV_SUFFIX="$2"; shift 2 ;;
    *) puts "${RED}Unknown argument: $1${RESET}"; exit 1 ;;
  esac
done

ENV_FILE=".env${ENV_SUFFIX:+.$ENV_SUFFIX}"

if [ ! -f "$ENV_FILE" ]; then
  puts "${RED}ERROR: $ENV_FILE not found.${RESET}"
  if [ -f "${ENV_FILE}.example" ]; then
    puts "Copy ${ENV_FILE}.example to ${ENV_FILE} and configure it."
  else
    puts "No example found. Check available .env*.example files."
  fi
  exit 1
fi

puts "${BLUE}Loading env profile: ${ENV_FILE}${RESET}"
set -a && source "$ENV_FILE" && set +a

DATA_ROOT="${DATA_ROOT:-tmp/data_store}"
OPENAI_MODEL="${OPENAI_MODEL:-orieg/gemma3-tools:12b-ft-v2}"
EMBEDDING_MODEL="${EMBEDDING_MODEL:-nomic-embed-text}"

# Start Ollama
puts "${BLUE}Starting Ollama...${RESET}"
docker compose -f docker-compose.local.yml up -d

# Wait for Ollama health (30 second timeout)
puts "${BLUE}Waiting for Ollama API...${RESET}"
timeout=30
elapsed=0
until curl -sf http://localhost:11434/api/version > /dev/null; do
  if [ "$elapsed" -ge "$timeout" ]; then
    puts "${RED}ERROR: Ollama did not become ready within ${timeout}s.${RESET}"
    puts "Check: docker compose -f docker-compose.local.yml logs ollama"
    exit 1
  fi
  sleep 1
  elapsed=$((elapsed + 1))
done
puts "${GREEN}Ollama ready.${RESET}"

# Pull models (no-op if already cached in ~/.ollama)
puts "${BLUE}Pulling models (no-op if already cached)...${RESET}"
docker compose -f docker-compose.local.yml exec ollama ollama pull "$EMBEDDING_MODEL"
docker compose -f docker-compose.local.yml exec ollama ollama pull "$OPENAI_MODEL"

# Warm up: force model into memory before first player request.
# Cold start takes ~12s; doing it here prevents the first game response from hanging.
puts "${BLUE}Warming up model (may take ~12s)...${RESET}"
curl -sf http://localhost:11434/api/chat \
  -d "{\"model\":\"$OPENAI_MODEL\",\"stream\":false,\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}" \
  > /dev/null
puts "${GREEN}Model warm.${RESET}"

# Create data root if absent
mkdir -p "$DATA_ROOT"

# Run CLI
puts "${GREEN}Starting CampaignNarrator (profile: ${ENV_FILE}, data: ${DATA_ROOT})${RESET}"
puts ""
poetry run campaignnarrator --data-root "$DATA_ROOT"
