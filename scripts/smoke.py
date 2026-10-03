"""End-to-end smoke test (section 12.2). Uses its own DB, models and reports directories.

    python scripts/smoke.py        (or: bash scripts/smoke.sh)

Seeds a fresh DB, runs a 1-day twin, trains a tiny model on it, runs the forecast and advisory
jobs, starts the API, hits every endpoint, and exits non-zero on any failure.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "data" / "smoke"
os.environ.update({
    "DATABASE_URL": f"sqlite:///{(SMOKE / 'smoke.db').as_posix()}",
    "TRANSIT_MODELS_DIR": str(SMOKE / "models"),
    "TRANSIT_REPORTS_DIR": str(SMOKE / "reports"),
    "DISABLE_SCHEDULER": "1",
    "CAMERA_API_KEY": "smoke-key",
})
SRC = [ROOT / d for d in ("backend", "database", "ml", "simulation")]   # Python package roots
sys.path[:0] = [str(p) for p in SRC]
os.environ["PYTHONPATH"] = os.pathsep.join([*map(str, SRC), os.environ.get("PYTHONPATH", "")])   # for subprocesses
FAIL: list[str] = []


def step(name, fn):
    t = time.time()
    try:
        out = fn()
        print(f"  ok   {name} ({time.time() - t:.1f}s){' - ' + out if isinstance(out, str) else ''}", flush=True)
        return out
    except Exception as e:  # report and continue so every failure is listed
        FAIL.append(f"{name}: {e}")
        print(f"  FAIL {name}: {e}", flush=True)


def main() -> int:
    if SMOKE.exists():
        shutil.rmtree(SMOKE)
    SMOKE.mkdir(parents=True)
    import pandas as pd

    from common.config import IST
    from db.seed import main as seed

    print("1. seed + twin + tiny model")
    step("seed db", lambda: None if seed() == 0 else (_ for _ in ()).throw(RuntimeError("seed failed")))
    today = date.today()

    def twin():
        from twin.simulate import run, to_db

        ev, s = run(start_date=today, days=1, seed=5, workers=1, run_id=f"stream-{today:%Y%m%d}")
        assert (ev.source == "twin").all() and len(ev) > 5000
        now = pd.Timestamp.now(tz=IST)
        to_db(ev[ev.ts <= now], s)  # only the part of today that has 'happened'
        return f"{len(ev):,} events, {s['boardings_per_day']:,} boardings"

    step("1-day twin", twin)

    def tiny_model():
        from predictor.evaluate import main as ev_main

        rc = ev_main(["--epochs", "1", "--samples", "3000"])
        assert (SMOKE / "models" / "lstm_v1.pt").exists() and (SMOKE / "reports" / "forecast_eval.md").exists()
        return f"evaluate exit {rc} (acceptance not expected on 1 day)"

    step("train tiny model + evaluate", tiny_model)

    def forecast():
        from predictor.serve import run_forecast

        r = run_forecast()
        assert r["rows"] > 1000 and "lstm" in r["models"]
        return f"{r['rows']:,} rows, models {r['models']}"

    step("forecast job", forecast)

    print("2. API")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--port", str(port)], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}/api/v1"
    try:
        import requests

        for _ in range(60):
            try:
                if requests.get(base + "/health", timeout=1).ok:
                    break
            except Exception:
                time.sleep(0.5)
        H = {"X-API-Key": "smoke-key"}
        g = lambda p, **kw: _ok(requests.get(base + p, timeout=60, **kw))  # noqa: E731
        post = lambda p, body, **kw: _ok(requests.post(base + p, json=body, timeout=120, **kw))  # noqa: E731

        step("GET /health", lambda: _expect(g("/health")["sources"].get("twin", 0) > 0, "twin rows"))
        routes = step("GET /routes", lambda: g("/routes"))
        step("GET /stops", lambda: _expect(len(g("/stops", params={"q": "guindy"})) > 0, "stops"))
        now = pd.Timestamp.now(tz=IST)
        ev = [{"ts": now.isoformat(), "stop_id": "MRTS_VLCY", "source": "camera_stop", "waiting_count": 11,
               "client_event_id": "smoke-1"},
              {"ts": now.isoformat(), "stop_id": "MRTS_VLCY", "source": "camera_vehicle", "route_id": "MRTS_BV",
               "direction": 1, "vehicle_id": "SMOKE-V1", "boardings": 6, "alightings": 2, "client_event_id": "smoke-2"}]
        step("POST /ingest/events", lambda: _expect(post("/ingest/events", ev, headers=H)["accepted"] == 2, "accepted"))
        step("POST /ingest/heartbeat", lambda: post("/ingest/heartbeat", {"node_id": "smoke", "fps": 5}, headers=H))
        for r in (routes or [])[:7]:
            step(f"GET /occupancy/route/{r['route_id']}",
                 lambda r=r: _expect(g(f"/occupancy/route/{r['route_id']}", params={"direction": 0})["data_source"] in ("twin", "mixed"), "data_source"))
        step("GET /occupancy/stop", lambda: g("/occupancy/stop/MRTS_VLCY"))
        step("GET /vehicles + /vehicle", lambda: g(f"/vehicle/{g('/vehicles')[0]['vehicle_id']}") if g("/vehicles") else "no active vehicle now")
        step("GET /forecast", lambda: _expect(len(g("/forecast", params={"route_id": "BUS_95"})["rows"]) > 0, "rows"))
        step("GET /history", lambda: _expect(len(g("/history", params={"stop_id": "MRTS_VLCY", "route_id": "MRTS_BV"})["lf"]) == 96, "96 slots"))
        step("GET /wait-or-go", lambda: g("/wait-or-go", params={"stop_id": "MRTS_VLCY", "route_id": "MRTS_BV"})["suggestion"])
        step("POST /plan", lambda: f"{len(post('/plan', {'from_stop': '6693', 'to_stop': 'MRTS_VLCY'})['itineraries'])} itineraries")
        step("GET /stops/nearest", lambda: g("/stops/nearest", params={"lat": 12.9792, "lon": 80.2205})[0]["stop_id"])
        step("POST /plan/window", lambda: _expect(len(post("/plan/window", {"from_stop": "CMRL_26", "to_stop": "MRTS_TVMR", "window_min": 15,
                                                                         "filters": {"women": True}})["slots"]) == 3, "3 slots"))
        step("GET /fleet/heatmap", lambda: f"{len(g('/fleet/heatmap')['rows'])} rows")
        step("GET /fleet/heatmap/BUS_95 stops+buses", lambda: (g("/fleet/heatmap/BUS_95", params={"view": "stops"}),
                                                               g("/fleet/heatmap/BUS_95", params={"view": "buses"}))[0]["route"])
        step("POST /advisories/run", lambda: f"{post('/advisories/run', {})['created']} created")
        step("GET /advisories", lambda: g("/advisories"))
        step("GET /twin/scenarios", lambda: _expect(len(g("/twin/scenarios")) >= 8, "scenarios"))

        def twin_run():
            rid = post("/twin/run", {"scenario": "rain_heavy", "days": 1, "seed": 3})["run_id"]
            for _ in range(240):
                st = g(f"/twin/run/{rid}")
                if st["status"] in ("done", "error"):
                    break
                time.sleep(1)
            assert st["status"] == "done", st
            return f"rain_heavy boardings {st['summary']['scenario']['boardings_total']:,}"

        step("POST /twin/run + poll", twin_run)

        def builder_run():
            rid = post("/twin/run", {"scenario": "builder", "mods": {"fleet": [{"route": "BUS_95", "hour": 8, "buses": 2}]}})["run_id"]
            for _ in range(240):
                st = g(f"/twin/run/{rid}")
                if st["status"] in ("done", "error"):
                    break
                time.sleep(1)
            assert st["status"] == "done" and st["summary"]["fleet"]["bus_hours"] == 2, st
            return f"fleet-only plan: {st['summary']['fleet']['trips_added']} trips added"

        step("POST /twin/run builder (fleet only)", builder_run)
        step("POST /twin/whatif", lambda: f"{len(post('/twin/whatif', {'extra_trips': [{'route': 'BUS_95', 'direction': 0, 'start': '08:00', 'end': '09:30', 'n': 2}]})['table'])} rows")
        step("GET /accuracy", lambda: g("/accuracy"))
        step("GET /impact (404 until computed)", lambda: requests.get(base + "/impact", timeout=10).status_code in (200, 404) or (_ for _ in ()).throw(RuntimeError("bad status")))

        def sse():
            with requests.get(base + "/stream/occupancy", stream=True, timeout=30) as r:
                for line in r.iter_lines():
                    if line:
                        return line.decode()[:60]

        step("GET /stream/occupancy (SSE)", sse)
        step("GET /docs", lambda: _expect(requests.get(f"http://127.0.0.1:{port}/docs", timeout=10).ok, "docs"))
    finally:
        proc.terminate()
    print(f"\n{'SMOKE FAILED' if FAIL else 'SMOKE OK'}: {len(FAIL)} failure(s)")
    for f in FAIL:
        print("  -", f)
    return 1 if FAIL else 0


def _ok(r):
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def _expect(cond, what):
    if not cond:
        raise RuntimeError(f"unexpected {what}")
    return what


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


if __name__ == "__main__":
    sys.exit(main())
