"""One-command demo: prepares whatever is missing, then serves API + PWA on one port.

    python scripts/demo.py [--port 8000] [--host 127.0.0.1] [--clock 08:30] [--speed 1]

Steps (each skipped when its output already exists):
  1. data/fetch_data.py         inputs into data/raw/
  2. db.seed                    schema + corridor network
  3. twin.generate --days 90    simulated history (needs config/demand_fitted.yaml from calibration)
  4. predictor.evaluate         train LSTM + Prophet, write reports/forecast_eval.md
  5. advisory.impact            impact summary for the dashboard
  6. npm run build (web/)       the PWA, served by FastAPI from web/dist
Then uvicorn starts; its scheduler streams today's twin events, forecasts every 5 min and runs
advisories every 15 min. --clock 08:30 runs the demo clock from 08:30 today (useful for showing
the morning peak at any hour).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def sh(args, **kw):
    print("$", " ".join(map(str, args)), flush=True)
    subprocess.run(args, cwd=kw.pop("cwd", ROOT), check=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--clock", default=None, help="demo clock start, HH:MM (default: real time)")
    ap.add_argument("--speed", type=float, default=1.0, help="demo clock speed multiplier")
    ap.add_argument("--skip-web", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT))

    if not (ROOT / "data/raw/gtfs/stops.txt").exists():
        sh([PY, "data/fetch_data.py"])
    from db.database import query

    try:
        n = query("SELECT COUNT(*) n FROM route").n.iloc[0]
    except Exception:
        n = 0
    if not n:
        sh([PY, "-m", "db.seed"])
    if not (ROOT / "config/demand_fitted.yaml").exists():
        sh([PY, "-m", "twin.calibrate"])
    hist = query("SELECT COUNT(*) n FROM event WHERE run_id LIKE 'history-%'").n.iloc[0]
    if hist == 0:
        sh([PY, "-m", "twin.generate", "--days", "90"])
    if not (ROOT / "models/lstm_v1.pt").exists():
        sh([PY, "-m", "predictor.evaluate"])
    if not (ROOT / "reports/impact_summary.json").exists():
        sh([PY, "-m", "advisory.impact"])
    if not a.skip_web and not (ROOT / "web/dist/index.html").exists():
        npm = shutil.which("npm")
        if npm:
            sh([npm, "ci" if (ROOT / "web/package-lock.json").exists() else "install"], cwd=ROOT / "web")
            sh([npm, "run", "build"], cwd=ROOT / "web")
        else:
            print("npm not found: API only (build web/ with `npm install && npm run build`).")
    env = dict(os.environ)
    if a.clock:
        env["DEMO_CLOCK_START"] = a.clock
        env["DEMO_CLOCK_SPEED"] = str(a.speed)
    print(f"\n  Commuter app:  http://{a.host}:{a.port}/\n  Depot:         http://{a.host}:{a.port}/depot\n"
          f"  API docs:      http://{a.host}:{a.port}/docs\n  (all crowd numbers are SIMULATED)\n", flush=True)
    subprocess.run([PY, "-m", "uvicorn", "api.main:app", "--host", a.host, "--port", str(a.port)], cwd=ROOT, env=env)


if __name__ == "__main__":
    main()
