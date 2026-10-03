"""Background jobs (APScheduler): twin streaming release (30 s), forecast (5 min), advisories (15 min).

Set DISABLE_TWIN_STREAM=1 to run without the simulated live feed (e.g. cameras only)."""
from __future__ import annotations

import logging
import os
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from common.config import load_yaml

log = logging.getLogger("jobs")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
_lock = threading.Lock()


def _release():
    from twin.stream import release

    try:
        n = release()
        if n:
            log.info("stream: released %d twin events", n)
    except Exception:
        log.exception("stream release failed")


def _forecast():
    from predictor.serve import run_forecast

    if not _lock.acquire(blocking=False):
        return
    try:
        log.info("forecast: %s", run_forecast())
    except Exception:
        log.exception("forecast failed")
    finally:
        _lock.release()


def _advisories():
    from advisory.headway import run_advisories

    try:
        out = run_advisories()
        log.info("advisories: %d new", len(out))
    except Exception:
        log.exception("advisories failed")


def _startup():
    if os.environ.get("DISABLE_TWIN_STREAM") != "1":
        from twin.stream import ensure_today

        try:
            log.info("stream: %s", ensure_today())
        except Exception:
            log.exception("stream setup failed")
        _release()
    _forecast()
    _advisories()


def start_scheduler() -> BackgroundScheduler:
    cfg = load_yaml("predictor.yaml")
    s = BackgroundScheduler(timezone="Asia/Kolkata")
    if os.environ.get("DISABLE_TWIN_STREAM") != "1":
        s.add_job(_release, "interval", seconds=cfg["stream"]["release_every_s"], id="release", max_instances=1)
    s.add_job(_forecast, "interval", minutes=cfg["serve"]["interval_min"], id="forecast", max_instances=1)
    s.add_job(_advisories, "interval", minutes=15, id="advisories", max_instances=1)
    s.start()
    threading.Thread(target=_startup, daemon=True).start()
    return s
