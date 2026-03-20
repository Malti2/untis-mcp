#!/usr/bin/env bash
# Run the standalone daily report
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi
exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/daily_report.py" "$@"
