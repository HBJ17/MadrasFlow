#!/usr/bin/env bash
# Rebuild every generated artifact after a model or config change, in spec phase order.
# Logs to reports/rebuild_log.txt. Stops at the first failing step (validation failures are reported
# but do not stop the chain, so all reports are refreshed).
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/Scripts/python}"; [ -x "$PY" ] || PY=".venv/bin/python"
LOG=reports/rebuild_log.txt; : > "$LOG"
run() { echo "=== $* ($(date +%H:%M:%S))" | tee -a "$LOG"; "$PY" -u "$@" >> "$LOG" 2>&1; rc=$?; echo "=== exit $rc" | tee -a "$LOG"; return $rc; }
CAL="${CALIBRATE:---stage-a-only}"
run -m twin.calibrate $CAL || exit 1
run -m db.seed || exit 1
run -m twin.validate
run -m twin.generate --days 90 --verify || exit 1
run -m predictor.evaluate
run -m advisory.impact || exit 1
echo "done $(date +%H:%M:%S)" | tee -a "$LOG"
