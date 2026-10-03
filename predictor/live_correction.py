"""Live correction of the near-term forecast (section 7.4).

load_est = load_pred + K * (load_obs - load_pred); the correction is propagated to the next stops
downstream and the next 1-3 slots with decay rho^h. Observations at a route's last stop are
ignored (terminal reset: vehicles end empty, and camera running counts are reset there). If no
live data arrived for a route in the last stale_after_min minutes, its rows are flagged stale.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common.config import load_yaml


def cfg():
    return load_yaml("predictor.yaml")["live_correction"]


def apply(fc: pd.DataFrame, obs: pd.DataFrame, now: pd.Timestamp, last_seq: dict) -> pd.DataFrame:
    """fc: forecast rows (route_id, direction, stop_id, seq, target_slot, pred_lf, lo, hi).
    obs: live observations in the last stale window (route_id, direction, stop_id, seq, ts, lf, source).
    last_seq: (route_id, direction) -> last seq number. Returns fc with corrected values + stale flag."""
    c = cfg()
    fc = fc.copy()
    fc["stale"] = 1
    fc["corrected"] = 0.0
    if obs is None or not len(obs):
        return fc
    recent = obs[obs.ts >= now - pd.Timedelta(minutes=c["stale_after_min"])]
    live_routes = set(zip(recent.route_id, recent.direction))
    fc.loc[[(r, d) in live_routes for r, d in zip(fc.route_id, fc.direction)], "stale"] = 0
    slots = np.sort(fc.target_slot.unique())
    latest = recent.sort_values("ts").groupby(["route_id", "direction", "stop_id"]).tail(1)
    for o in latest.itertuples(index=False):
        if o.seq >= last_seq.get((o.route_id, o.direction), 10 ** 6):
            continue  # terminal: reset, no propagation
        k = c["kalman_gain"].get(o.source, 0.5)
        here = fc[(fc.route_id == o.route_id) & (fc.direction == o.direction) & (fc.stop_id == o.stop_id)]
        if not len(here):
            continue
        slot_now = here.loc[here.target_slot >= pd.Timestamp(o.ts).floor("15min"), "pred_lf"]
        if not len(slot_now):
            continue
        c0 = k * (float(o.lf) - float(slot_now.iloc[0]))
        for h in range(c["max_slots"]):
            if h >= len(slots):
                break
            m = ((fc.route_id == o.route_id) & (fc.direction == o.direction) & (fc.target_slot == slots[h])
                 & (fc.seq >= o.seq) & (fc.seq < o.seq + c["downstream_stops"]))
            fc.loc[m, "corrected"] += c0 * c["rho"] ** h
    for col in ("pred_lf", "lo", "hi"):
        fc[col] = (fc[col] + fc.corrected).clip(lower=0, upper=2.0)
    return fc
