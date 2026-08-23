#!/usr/bin/env bash
# Technology Prediction Tournament for Hermes
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
  echo "run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

ARGS=(run)
for arg in "$@"; do
  ARGS+=("$arg")
done

echo "[PREDICTION] Starting technology prediction tournament"
echo "[PREDICTION] time=$STAMP"

if [[ "$*" != *"--dry-run"* ]]; then
  if ! curl -sf "${OLLAMA_HOST%/}/api/tags" >/dev/null 2>&1; then
    if [[ -z "${OPENAI_API_KEY:-}" ]]; then
      echo "warning: Ollama unreachable and OPENAI_API_KEY not set; tournament may fail"
    fi
  fi
fi

set +e
OUTPUT="$("$PYTHON" -m app.prediction_tournament "${ARGS[@]}" 2>&1)"
STATUS=$?
set -e

echo "$OUTPUT"

if [[ $STATUS -ne 0 ]]; then
  echo "[PREDICTION] Failed with exit code $STATUS at $STAMP" >&2
  exit "$STATUS"
fi

echo "[PREDICTION] Complete at $STAMP"
