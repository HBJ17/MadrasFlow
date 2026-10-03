"""Twin streaming mode: today's simulated events are released into the event table as the (demo)
clock passes them, so the forecast job, live correction and dashboards behave as they would with a
live AFC/camera feed. Rows stay source='twin' and are labelled simulated everywhere.

ensure_today() also back-fills any whole days missing between the stored history and today (for
example when the demo runs a few days after the 90-day history was generated).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from common import clock
from common.config import IST, PROCESSED_DIR, iso
from db.database import query, write_events
from twin.simulate import run, to_db

log = logging.getLogger("twin.stream")
_CACHE: dict = {}


def _path(d: date):
    return PROCESSED_DIR / f"stream_{d:%Y%m%d}.parquet"


def ensure_today(seed: int = 7, scenario: str = "baseline") -> dict:
    today = clock.now().date()
    last = query("SELECT MAX(ts) m FROM event WHERE source='twin' AND run_id NOT LIKE 'stream-%'").m.iloc[0]
    filled = []
    if last:
        last_day = (pd.Timestamp(last).tz_convert(IST) - pd.Timedelta(hours=3)).date()
        d = last_day + timedelta(days=1)
        if d < today:
            days = (today - d).days
            ev, s = run(scenario=scenario, start_date=d, days=days, seed=seed + 1000, workers=min(days, 8),
                        run_id=f"backfill-{d:%Y%m%d}-{days}d")
            to_db(ev, s)
            filled = [str(d + timedelta(days=i)) for i in range(days)]
    p = _path(today)
    run_id = f"stream-{today:%Y%m%d}"
    if not p.exists():
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        ev, s = run(scenario=scenario, start_date=today, days=1, seed=seed, workers=1, run_id=run_id)
        ev.to_parquet(p, index=False)
        s["_unmet"] = s["_unmet"].iloc[0:0]  # unmet demand is not known in advance; not streamed
        # store the run and today's timetable (trips) without the events
        to_db(ev.iloc[0:0], s)
    _CACHE.clear()
    return {"today": str(today), "stream_file": p.name, "backfilled_days": filled}


def release(now: pd.Timestamp | None = None) -> int:
    """Insert today's twin events with ts <= now that are not in the DB yet. Returns rows inserted."""
    now = pd.Timestamp(now or clock.now()).tz_convert(IST)
    today = (now - pd.Timedelta(hours=3)).date() if now.hour < 3 else now.date()
    p = _path(today)
    if not p.exists():
        return 0
    if _CACHE.get("day") != today:
        _CACHE.update(day=today, ev=pd.read_parquet(p))
    ev = _CACHE["ev"]
    run_id = f"stream-{today:%Y%m%d}"
    wm = query("SELECT MAX(ts) m FROM event WHERE run_id = :r", {"r": run_id}).m.iloc[0]
    lo = pd.Timestamp(wm).tz_convert(IST) if wm else pd.Timestamp(today).tz_localize(IST) - pd.Timedelta(seconds=1)
    new = ev[(ev.ts > lo) & (ev.ts <= now)].copy()
    if not len(new):
        return 0
    new["ts"] = new.ts.map(iso)
    new["slot_15"] = new.slot_15.map(iso)
    return write_events(new)
