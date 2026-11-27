#!/bin/bash
# Resume walk-forward OOS runs; skip combos already audited OK.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/reports/oos_quant_v2/run.log"
PIDFILE="$ROOT/reports/oos_quant_v2/run.pid"
mkdir -p "$ROOT/reports/oos_quant_v2"
cd "$ROOT"
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "already running pid $(cat "$PIDFILE")"
  exit 0
fi
# Also refuse if a stray runner is already going (unless it is our pidfile).
if pgrep -f "scripts/run_quant_walkforward.py" >/dev/null; then
  echo "a run_quant_walkforward.py process is already running; not starting a second one"
  pgrep -af "scripts/run_quant_walkforward.py"
  exit 1
fi
nohup "$ROOT/.venv/bin/python" -u "$ROOT/scripts/run_quant_walkforward.py" >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"
disown $! || true
echo "started pid $! log $LOG"
