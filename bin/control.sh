#!/usr/bin/env bash
# bin/control.sh: Run the bare-bones D&D narrator control session.
# Loads .env.secrets (API key) then .env.openai (model, base URL).
# No Docker, no Ollama, no state — pure OpenAI API loop.

set -e
cd "$(dirname "$0")/.."

if [ -f ".env.secrets" ]; then
  set -a && source ".env.secrets" && set +a
fi

if [ -f ".env.openai" ]; then
  set -a && source ".env.openai" && set +a
elif [ -f ".env.openai.example" ]; then
  echo "WARNING: .env.openai not found — creating from .env.openai.example"
  cp ".env.openai.example" ".env.openai"
  set -a && source ".env.openai" && set +a
else
  echo "ERROR: .env.openai not found." >&2
  exit 1
fi

echo "Model: ${OPENAI_MODEL:-gpt-4o-mini}"
poetry run python control/narrator.py
