#!/usr/bin/env bash
# Monthly Technology Prediction Verification for Hermes
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs"
PYTHON="$ROOT/.venv/bin/python"
STAMP="$(date '+%Y-%m-%d %H:%M %Z')"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${HOME}/.local/bin:${PATH}"
export TZ="${TZ:-America/Los_Angeles}"
export PYTHONPATH="$ROOT"
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3.6:27b}"
export PREDICTION_LLM_PROVIDER="${PREDICTION_LLM_PROVIDER:-ollama}"
export PREDICTION_LLM_MODEL="${PREDICTION_LLM_MODEL:-$OLLAMA_MODEL}"
export PREDICTION_LLM_BASE_URL="${PREDICTION_LLM_BASE_URL:-${OLLAMA_HOST%/}/v1}"

mkdir -p "$LOG_DIR"
cd "$ROOT"

if [[ ! -x "$PYTHON" ]]; then
  echo "error: virtualenv missing at $PYTHON"
  exit 1
fi

ARGS=(verify)
for arg in "$@"; do
  ARGS+=("$arg")
done

echo "[PREDICTION] Starting monthly verification"
echo "[PREDICTION] time=$STAMP"

set +e
OUTPUT="$("$PYTHON" -m app.prediction_tournament "${ARGS[@]}" 2>&1)"
STATUS=$?
set -e

echo "$OUTPUT"

if [[ $STATUS -ne 0 ]]; then
  echo "[PREDICTION] Verification failed with exit code $STATUS at $STAMP" >&2
  exit "$STATUS"
fi

echo "[PREDICTION] Verification complete at $STAMP"
