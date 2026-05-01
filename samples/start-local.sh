#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p "$ROOT/samples/generated"

ENV_FILE="$ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT/.env.example" "$ENV_FILE"
  echo "Created .env from .env.example — set OPENAI_API_KEY and LANGCHAIN_API_KEY (LangSmith is required). Optional: ANTHROPIC for vision fallback."
fi

has_key=false
[[ -n "${OPENAI_API_KEY:-}" ]] && has_key=true
if grep -qE '^[[:space:]]*OPENAI_API_KEY[[:space:]]*=[[:space:]]*[^[:space:]]' "$ENV_FILE" 2>/dev/null; then
  has_key=true
fi

if [[ "$has_key" != true ]]; then
  echo "ERROR: Set OPENAI_API_KEY in .env (see .env.example)." >&2
  exit 1
fi

ls_key=false
[[ -n "${LANGCHAIN_API_KEY:-}" ]] && ls_key=true
if grep -qE '^[[:space:]]*LANGCHAIN_API_KEY[[:space:]]*=[[:space:]]*[^[:space:]]' "$ENV_FILE" 2>/dev/null; then
  ls_key=true
fi

if [[ "$ls_key" != true ]]; then
  echo "ERROR: Set LANGCHAIN_API_KEY in .env — LangSmith tracing is required (see .env.example)." >&2
  exit 1
fi

echo "Starting stack (Postgres, LIMS mock, API, Prometheus, Grafana)..."
docker compose up --build
