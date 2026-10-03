#!/usr/bin/env bash
# Smoke test: starts the API, runs a 1-day twin, trains a tiny model, hits every endpoint.
# Exits non-zero on any failure. Uses data/smoke/ so real data, models and reports are untouched.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/Scripts/python}"
[ -x "$PY" ] || PY=".venv/bin/python"
[ -x "$PY" ] || PY="python"
exec "$PY" scripts/smoke.py
