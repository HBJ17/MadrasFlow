"""Extra heatmap rules on top of the add-trips advisory (advisory.headway). Each rule reads the same
forecast window and returns a ready-to-store advisory row with a plain-language reason.

  short_turn  crowding only on the first part of the route: run short trips that turn back after the
              crowded section instead of full trips (same added capacity where it is needed, less cost)
  move_bus    a bus route sharing a station stays quiet through the window: move a bus from it

Neither rule runs its own twin test. A short-turn adds the same capacity on the crowded section as
the twin-tested extra trips, so it reuses that result; a moved bus is estimated from the forecast.
"""
from __future__ import annotations

import math

import pandas as pd

from advisory.whatif import neighbours
from common.config import IST, iso
from db.database import query

SHORT_TURN_MAX_SHARE = 0.6   # crowded stops all within the first 60% of the route
QUIET_LF = 0.30              # a donor route stays below this load in every slot of the window


def _route(rid: str):
    return query("SELECT route_id, short_name, mode, depot, capacity_total FROM route WHERE route_id = :r", {"r": rid}).iloc[0]


def _stops(rid: str, d: int) -> pd.DataFrame:
    return query("SELECT rs.seq, rs.stop_id, rs.run_min, s.name FROM route_stop rs JOIN stop s ON s.stop_id = rs.stop_id "
                 "WHERE rs.route_id = :r AND rs.direction = :d ORDER BY rs.seq", {"r": rid, "d": d})


def _window_rows(fc: pd.DataFrame, w: dict) -> pd.DataFrame:
    return fc[(fc.route_id == w["route_id"]) & (fc.direction == w["direction"]) & (fc.slot >= w["start"]) & (fc.slot < w["end"])]


def short_turn(fc: pd.DataFrame, w: dict, base: dict) -> dict | None:
    st = _stops(w["route_id"], w["direction"])
    if len(st) < 6:
        return None
    sel = _window_rows(fc, w)
    flagged = sel[(sel.pred_lf >= 1.0) | ((sel.pred_lf >= 0.85) & (sel.hi >= 1.1))]
    if not len(flagged):
        return None
    pos = {s: i for i, s in enumerate(st.stop_id)}
    last = max(pos.get(s, len(st)) for s in flagged.stop_id)
    if last >= SHORT_TURN_MAX_SHARE * (len(st) - 1):
        return None
    turn = min(len(st) - 1, last + 2)          # turn back two stops after the last crowded one
    share = st.run_min.iloc[1:turn + 1].sum() / max(st.run_min.iloc[1:].sum(), 1e-6)
    r = _route(w["route_id"])
    n = base["extra_trips"]
    return {**base, "kind": "short_turn",
            "reason": f"crowding only between {st.name.iloc[0]} and {st.name.iloc[last]} "
                      f"({last + 1} of {len(st)} stops), forecast LF {w['peak_lf']:.2f}",
            "action": f"run {n} short trip{'s' if n > 1 else ''} {st.name.iloc[0]} → {st.name.iloc[turn]} "
                      f"between {base['_start']} and {base['_end']} instead of full trips",
            "extra_vehicle_hours": round((base["extra_vehicle_hours"] or 0) * share, 1),
            "neighbour_lf_after": None, "route_id": r.route_id}


def move_bus(fc: pd.DataFrame, w: dict, base: dict) -> dict | None:
    target = _route(w["route_id"])
    if target["mode"] != "bus":
        return None
    best = None
    for rid in neighbours().get(w["route_id"], []):
        donor = _route(rid)
        if donor["mode"] != "bus":
            continue
        g = fc[(fc.route_id == rid) & (fc.slot >= w["start"]) & (fc.slot < w["end"])]
        if not len(g):
            continue
        peak = float(g.groupby("slot").pred_lf.max().max())
        if peak <= QUIET_LF and (best is None or peak < best[1]):
            best = (donor, peak)
    if best is None:
        return None
    donor, peak = best
    sched = query("SELECT COUNT(*) n FROM trip WHERE route_id = :r AND scheduled_start >= :a AND scheduled_start < :b",
                  {"r": donor.route_id, "a": iso(w["start"]), "b": iso(w["end"])}).n.iloc[0]
    donor_after = peak * sched / max(sched - 1, 1) if sched > 1 else None
    hours = (w["end"] - w["start"]).total_seconds() / 3600
    return {**base, "kind": "move_bus",
            "reason": f"forecast LF {w['peak_lf']:.2f} on {target.short_name} at {w['peak_stop']} while "
                      f"{donor.short_name} ({donor.depot} depot) stays at or below {peak:.0%}",
            "action": f"move 1 bus from {donor.short_name} to {target.short_name} between {base['_start']} and {base['_end']}",
            "extra_trips": max(1, math.floor(hours * 60 / max(base.get('_cycle_min', 60), 1))),
            "extra_vehicle_hours": 0.0, "neighbour_lf_after": None if donor_after is None else round(donor_after, 3)}
