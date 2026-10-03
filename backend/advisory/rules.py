"""Extra heatmap rules on top of the add-trips advisory (advisory.headway). Each rule reads the same
forecast window and returns a ready-to-store advisory row with a plain-language reason.

  short_turn  crowding only on the first part of the route: run short trips that turn back after the
              crowded section instead of full trips (same added capacity where it is needed, less cost)
  move_bus    a bus route sharing a station stays quiet through the window: move a bus from it
  hold_for_train  a bus fills up sharply at a metro/MRTS station: hold it a couple of minutes so it
              leaves after the train arrives (passengers transferring off the train get on)

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
JUMP_LF = 0.35               # load rises by at least this much at the station ...
JUMP_MIN_LF = 0.75           # ... to at least HIGH, for at least two consecutive slots
HOLD_MIN = 2


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


def hold_for_train(fc: pd.DataFrame, now: pd.Timestamp, depots: dict) -> list[dict]:
    """Bus stops at rail stations where the bus fills up sharply for 2+ consecutive slots."""
    if not len(fc):
        return []
    rail = set(query("SELECT DISTINCT station_id FROM stop WHERE mode IN ('mrts','metro')").station_id)
    out = []
    for (rid, d), g in fc.groupby(["route_id", "direction"]):
        r = _route(rid)
        if r["mode"] != "bus":
            continue
        st = query("SELECT rs.seq, rs.stop_id, s.name, s.station_id FROM route_stop rs JOIN stop s ON s.stop_id = rs.stop_id "
                   "WHERE rs.route_id = :r AND rs.direction = :d ORDER BY rs.seq", {"r": rid, "d": int(d)})
        lf = g.pivot_table(index="stop_id", columns="slot", values="pred_lf")
        for i in range(1, len(st) - 1):
            stop, prev = st.stop_id.iloc[i], st.stop_id.iloc[i - 1]
            if st.station_id.iloc[i] not in rail or stop not in lf.index or prev not in lf.index:
                continue
            jump = (lf.loc[stop] - lf.loc[prev] >= JUMP_LF) & (lf.loc[stop] >= JUMP_MIN_LF)
            run = 0
            best = None
            for k, t in enumerate(lf.columns):
                run = run + 1 if bool(jump.get(t, False)) else 0
                if run >= 2:
                    best = (lf.columns[k - run + 1], t)
            if not best:
                continue
            a, b = best
            b = b + pd.Timedelta(minutes=15)
            top = float(lf.loc[stop, a:b].max())
            out.append({"created_at": iso(now), "route_id": rid, "depot": depots.get(rid), "direction": int(d),
                        "slot_start": iso(a), "slot_end": iso(b), "kind": "hold_for_train",
                        "reason": f"{r.short_name} fills from {lf.loc[prev, a:b].max():.0%} to {top:.0%} at {st.name.iloc[i]} "
                                  f"(rail interchange) between {a.tz_convert(IST):%H:%M} and {b.tz_convert(IST):%H:%M}",
                        "action": f"hold {r.short_name} {HOLD_MIN} min at {st.name.iloc[i]} to meet arriving trains "
                                  f"between {a.tz_convert(IST):%H:%M} and {b.tz_convert(IST):%H:%M}",
                        "extra_trips": 0, "expected_lf_before": round(top, 3), "expected_lf_after": None,
                        "neighbour_lf_after": None, "extra_vehicle_hours": 0.0, "status": "active",
                        "data_source": g.data_source.iloc[0]})
    return out
