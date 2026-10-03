"""Read-side helpers for occupancy endpoints: latest forecast, vehicle ETAs, history profiles.

ETA: if a trip has already reported a stop (event rows from the stream/camera), ETA = time of its
last reported stop + scheduled run time from there; otherwise scheduled start + scheduled run time.
This mirrors an AVL-based ETA. Crowd levels always come from the forecast table, never from
future simulated events.
"""
from __future__ import annotations

import time
from functools import lru_cache

import numpy as np
import pandas as pd

from api.deps import route_stops_df, routes_df
from common.config import IST, crowd_level, iso
from db.database import query

DWELL_EST = {"bus": 0.5, "mrts": 0.6, "metro": 0.5}
_cache: dict = {}


def _ttl(key, seconds, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < seconds:
        return hit[1]
    v = fn()
    _cache[key] = (time.time(), v)
    return v


def latest_forecast(model: str = "lstm") -> pd.DataFrame:
    def load():
        m = query("SELECT MAX(made_at) m FROM forecast WHERE model = :m", {"m": model}).m.iloc[0]
        mdl = model
        if m is None and model == "lstm":
            mdl = "baseline"
            m = query("SELECT MAX(made_at) m FROM forecast WHERE model = 'baseline'").m.iloc[0]
        if m is None:
            return pd.DataFrame()
        f = query("SELECT * FROM forecast WHERE made_at = :m AND model = :mdl", {"m": m, "mdl": mdl})
        f["slot"] = pd.to_datetime(f.target_slot, utc=True).dt.tz_convert(IST)
        return f
    return _ttl(("fc", model), 20, load)


def cum_minutes(route_id: str, direction: int) -> pd.DataFrame:
    rs = route_stops_df()
    g = rs[(rs.route_id == route_id) & (rs.direction == direction)].sort_values("seq").copy()
    mode = g["mode"].iloc[0] if len(g) else "bus"
    g["cum"] = (g.run_min + np.where(np.arange(len(g)) > 0, DWELL_EST.get(mode, 0.5), 0)).cumsum()
    return g


def trips_today(now: pd.Timestamp) -> pd.DataFrame:
    day0 = now.normalize() - (pd.Timedelta(days=1) if now.hour < 3 else pd.Timedelta(0))

    def load():
        t = query("SELECT * FROM trip WHERE scheduled_start >= :a AND scheduled_start < :b",
                  {"a": iso(day0), "b": iso(day0 + pd.Timedelta(days=1, hours=3))})
        t["start"] = pd.to_datetime(t.scheduled_start, utc=True).dt.tz_convert(IST)
        return t
    return _ttl(("trips", str(day0.date())), 300, load)


def last_reports(now: pd.Timestamp) -> pd.DataFrame:
    """Latest reported stop per trip in the last 3 hours (twin stream or camera)."""
    def load():
        r = query("""SELECT trip_id, vehicle_id, route_id, direction, stop_id, MAX(ts) ts, onboard_load, source
                     FROM event WHERE ts >= :a AND ts <= :b AND trip_id IS NOT NULL GROUP BY trip_id""",
                  {"a": iso(now - pd.Timedelta(hours=3)), "b": iso(now)})
        r["ts"] = pd.to_datetime(r.ts, utc=True).dt.tz_convert(IST)
        return r
    return _ttl(("last", now.floor("30s").isoformat()), 25, load)


def upcoming(route_id: str, direction: int, stop_id: str, now: pd.Timestamp, n: int = 5) -> list[dict]:
    """Next n vehicles of a route-direction at a stop: [{trip_id, vehicle_id, eta (Timestamp), eta_min}]."""
    g = cum_minutes(route_id, direction)
    if stop_id not in set(g.stop_id):
        return []
    cum = dict(zip(g.stop_id, g.cum))
    seq_of = dict(zip(g.stop_id, g.seq))
    target_cum, target_seq = cum[stop_id], seq_of[stop_id]
    trips = trips_today(now)
    trips = trips[(trips.route_id == route_id) & (trips.direction == direction)]
    rep = last_reports(now).set_index("trip_id")
    out = []
    for t in trips.itertuples(index=False):
        if t.trip_id in rep.index:
            r = rep.loc[t.trip_id]
            if r.stop_id not in seq_of or seq_of[r.stop_id] >= target_seq:
                continue  # already passed this stop
            eta = r.ts + pd.Timedelta(minutes=target_cum - cum[r.stop_id])
        else:
            eta = t.start + pd.Timedelta(minutes=target_cum)
        if eta >= now - pd.Timedelta(seconds=30):
            out.append({"trip_id": t.trip_id, "vehicle_id": t.vehicle_id if isinstance(t.vehicle_id, str) else None, "eta": eta,
                        "eta_min": max(0, round((eta - now).total_seconds() / 60))})
    out.sort(key=lambda x: x["eta"])
    return out[:n]


def forecast_at(fc: pd.DataFrame, route_id: str, direction: int, stop_id: str, when: pd.Timestamp) -> dict | None:
    if fc is None or not len(fc):
        return None
    f = fc[(fc.route_id == route_id) & (fc.direction == direction) & (fc.stop_id == stop_id)]
    if not len(f):
        return None
    slot = when.floor("15min")
    x = f[f.slot == slot]
    if not len(x):
        x = f.iloc[[int(np.argmin(np.abs((f.slot - slot).dt.total_seconds().values)))]]
    r = x.iloc[0]
    lf = float(r.pred_lf)
    return {"level": crowd_level(lf), "load_factor": round(lf, 3),
            "lo": None if pd.isna(r.lo) else round(float(r.lo), 3), "hi": None if pd.isna(r.hi) else round(float(r.hi), 3),
            "stale": bool(r.stale), "source": r.data_source, "slot": iso(r.slot)}


def flag(fc: pd.DataFrame) -> str:
    """Combine per-row data_source flags (twin | camera | mixed | none) into one."""
    vals = set(fc.data_source) if fc is not None and len(fc) else set()
    if "mixed" in vals or {"twin", "camera"} <= vals:
        return "mixed"
    for v in ("camera", "twin"):
        if v in vals:
            return v
    return "none"


@lru_cache(maxsize=1)
def route_meta() -> dict:
    r = routes_df()
    return {x.route_id: {"short_name": x.short_name, "mode": x["mode"], "capacity": int(x.capacity_total),
                         "long_name": x.long_name, "depot": x.depot} for _, x in r.iterrows()}
