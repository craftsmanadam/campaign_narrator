#!/usr/bin/env bash
# bin/run_local.sh: Start Ollama locally and run the CLI in interactive mode.
#
# Usage:
#   bin/run_local.sh              # loads .env (Ollama)
#   bin/run_local.sh --env openai # loads .env.openai (OpenAI)
#
# Secrets are loaded from .env.secrets if it exists (always, before the profile).

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

# Load secrets first so that profile values can override non-sensitive defaults.
if [ -f ".env.secrets" ]; then
  puts "${BLUE}Loading secrets: .env.secrets${RESET}"
  set -a && source ".env.secrets" && set +a
fi

ENV_FILE=".env${ENV_SUFFIX:+.$ENV_SUFFIX}"

if [ ! -f "$ENV_FILE" ]; then
  if [ -f "${ENV_FILE}.example" ]; then
    puts "${YELLOW}${ENV_FILE} not found — creating from ${ENV_FILE}.example${RESET}"
    cp "${ENV_FILE}.example" "$ENV_FILE"
  else
    puts "${RED}ERROR: $ENV_FILE not found and no ${ENV_FILE}.example to copy from.${RESET}"
    puts "Check available .env*.example files."
    exit 1
  fi
fi

puts "${BLUE}Loading env profile: ${ENV_FILE}${RESET}"
set -a && source "$ENV_FILE" && set +a

DATA_ROOT="${DATA_ROOT:-var/data_store}"
OLLAMA_MODEL="${OLLAMA_MODEL:-${OPENAI_MODEL:-orieg/gemma3-tools:12b-ft-v2}}"
EMBEDDING_MODEL="${EMBEDDING_MODEL:-nomic-embed-text}"
LLM_PROVIDER="${LLM_PROVIDER:-ollama}"

# Start Ollama (always needed for embeddings)
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

# Pull embedding model (always needed)
puts "${BLUE}Pulling embedding model (no-op if already cached)...${RESET}"
docker compose -f docker-compose.local.yml exec ollama ollama pull "$EMBEDDING_MODEL"

if [ "$LLM_PROVIDER" != "openai" ]; then
  # Pull and warm up the local LLM model
  puts "${BLUE}Pulling LLM model (no-op if already cached)...${RESET}"
  docker compose -f docker-compose.local.yml exec ollama ollama pull "$OLLAMA_MODEL"

  # Warm up: force model into memory before first player request.
  # Cold start takes ~12s; doing it here prevents the first game response from hanging.
  puts "${BLUE}Warming up model (may take ~12s)...${RESET}"
  curl -sf http://localhost:11434/api/chat \
    -d "{\"model\":\"$OLLAMA_MODEL\",\"stream\":false,\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}" \
    > /dev/null
  puts "${GREEN}Model warm.${RESET}"
else
  puts "${BLUE}LLM provider: openai — skipping local model pull and warmup.${RESET}"
fi

# Create data root and seed static game data (no-clobber: preserves live state)
mkdir -p "$DATA_ROOT"
puts "${BLUE}Seeding game data into ${DATA_ROOT}...${RESET}"
rsync -rl --ignore-existing data/ "$DATA_ROOT/"

# Run CLI
puts "${GREEN}Starting CampaignNarrator (profile: ${ENV_FILE}, data: ${DATA_ROOT})${RESET}"
puts ""
poetry run campaignnarrator --data-root "$DATA_ROOT"
