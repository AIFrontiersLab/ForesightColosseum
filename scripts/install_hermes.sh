#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_HOME_DIR="${HERMES_HOME:-$HOME/.hermes}"
SCRIPTS_DIR="$HERMES_HOME_DIR/scripts"
TOURNAMENT_WRAPPER="$SCRIPTS_DIR/technology-prediction-tournament.sh"
CHECK_WRAPPER="$SCRIPTS_DIR/technology-prediction-check.sh"
TOURNAMENT_JOB="Technology Prediction Tournament"
CHECK_JOB="Technology Prediction Check"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Virtualenv missing. Create it first:"
  echo "  cd $ROOT && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

mkdir -p "$SCRIPTS_DIR"
chmod +x "$ROOT/scripts/technology-prediction-tournament.sh"
chmod +x "$ROOT/scripts/technology-prediction-check.sh"

cat > "$TOURNAMENT_WRAPPER" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$ROOT"
exec "$ROOT/scripts/technology-prediction-tournament.sh" "\$@"
EOF
chmod +x "$TOURNAMENT_WRAPPER"

cat > "$CHECK_WRAPPER" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$ROOT"
exec "$ROOT/scripts/technology-prediction-check.sh" "\$@"
EOF
chmod +x "$CHECK_WRAPPER"

echo "Hermes wrappers installed:"
echo "  $TOURNAMENT_WRAPPER"
echo "  $CHECK_WRAPPER"

if ! command -v hermes >/dev/null 2>&1; then
  echo "hermes is not on PATH; wrappers installed but cron jobs were not created."
  echo "Manual run: $TOURNAMENT_WRAPPER"
  echo "Manual verify: $CHECK_WRAPPER"
  exit 0
fi

if hermes cron list 2>/dev/null | grep -q "$TOURNAMENT_JOB"; then
  echo "Cron job already exists: $TOURNAMENT_JOB"
else
  hermes cron create "0 3 * * 0" \
    --no-agent \
    --script "technology-prediction-tournament.sh" \
    --deliver local \
    --name "$TOURNAMENT_JOB" \
    --workdir "$ROOT"
  echo "Created Hermes cron job: $TOURNAMENT_JOB (0 3 * * 0 — Sundays at 3:00 AM)"
fi

if hermes cron list 2>/dev/null | grep -q "$CHECK_JOB"; then
  echo "Cron job already exists: $CHECK_JOB"
else
  hermes cron create "0 6 1 * *" \
    --no-agent \
    --script "technology-prediction-check.sh" \
    --deliver local \
    --name "$CHECK_JOB" \
    --workdir "$ROOT"
  echo "Created Hermes cron job: $CHECK_JOB (0 6 1 * * — monthly at 6:00 AM on the 1st)"
fi

echo
echo "Verify:"
echo "  hermes cron list"
echo "  hermes cron run \"$TOURNAMENT_JOB\""
echo "  $TOURNAMENT_WRAPPER --dry-run"
echo "  $CHECK_WRAPPER --dry-run"
