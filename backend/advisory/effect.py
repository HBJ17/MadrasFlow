"""What the accepted advisories change, tested in the twin, for the heatmap's "with accepted changes" view.

All of today's accepted advisories are run together in one twin day (same date and seed as the
advisory test and today's stream), so changes that interact (two routes sharing a station) are
counted once. The result is stored per route x direction x stop x 15-min slot as the mean demand load
factor (on board + left behind, / capacity) without and with the changes, pooled over 30 min either
side; the heatmap scales the live forecast by that change.

Each kind becomes a twin modification:
  add_trips       extra trips on the route and direction in the window
  short_turn      extra trips that turn back after the crowded section
  move_bus        extra trips on the crowded route, the same number taken off the quiet route
  hold_for_train  the route's buses wait a couple of minutes at the rail station before boarding

Only the route-directions an advisory acts on are changed (a moved bus: both directions of both
routes), from 15 min before its window to an hour after, and only where the load moves by at least
3 points. Other routes are left as forecast: adding a bus re-orders the twin's random draws, so their
small differences are run-to-run noise rather than an effect (the advisory's own test already checks
that neighbouring routes do not tip over).
"""
from __future__ import annotations

import json
import re
import threading

import pandas as pd

from advisory.whatif import _base_run, _caps, window_stats
from common import clock
from common.config import IST, hhmm_to_min, iso
from db.database import engine, execute, query
from twin.simulate import run
from twin.stream import service_day

SEED = 7                 # same seed as the advisory test and today's twin stream
RUN_ID = "accepted-effect"
MIN_CHANGE = 0.03
AFTER_MIN = 60           # crowding effects carry on for a while after the window

_state = {"running": False, "error": None}
_lock = threading.Lock()


def _hhmm(ts) -> str:
    return pd.Timestamp(ts).tz_convert(IST).strftime("%H:%M")


def accepted() -> pd.DataFrame:
    """Accepted advisories for today's service day."""
    day = pd.Timestamp(service_day(clock.now())).tz_localize(IST) + pd.Timedelta(hours=3)
    return query("SELECT * FROM advisory WHERE status = 'accepted' AND slot_end > :d ORDER BY advisory_id",
                 {"d": iso(day)})


def _stop_index(route_id: str, direction: int, name: str) -> tuple[int, str] | None:
    st = query("SELECT rs.stop_id, s.name FROM route_stop rs JOIN stop s ON s.stop_id = rs.stop_id "
               "WHERE rs.route_id = :r AND rs.direction = :d ORDER BY rs.seq", {"r": route_id, "d": direction})
    hits = [i for i, n in enumerate(st.name) if n == name.strip()]
    return (hits[0], st.stop_id.iloc[hits[0]]) if hits else None


def _params(a) -> dict | None:
    """The stored parameters, or (for advisories made before they were stored) read from the text."""
    if isinstance(a.get("params"), str) and a["params"]:
        return json.loads(a["params"])
    kind, d = a.get("kind") or "add_trips", int(a["direction"])
    start = _hhmm(pd.Timestamp(a["slot_start"]) - pd.Timedelta(minutes=15))
    p = {"start": start, "end": _hhmm(a["slot_end"]), "n": int(a["extra_trips"] or 1)}
    if kind == "short_turn":
        m = re.search(r"→ (.+?) between", a["action"] or "")
        hit = m and _stop_index(a["route_id"], d, m.group(1))
        return {**p, "turn_idx": hit[0]} if hit else None
    if kind == "move_bus":
        m = re.search(r"move 1 bus from (\S+) to", a["action"] or "")
        r = m and query("SELECT route_id FROM route WHERE short_name = :s", {"s": m.group(1)})
        return {**p, "donor": r.route_id.iloc[0]} if m and len(r) else None
    if kind == "hold_for_train":
        m = re.search(r"min at (.+?) to meet", a["action"] or "")
        hit = m and _stop_index(a["route_id"], d, m.group(1))
        return {"stop_id": hit[1], "start": _hhmm(a["slot_start"]), "end": _hhmm(a["slot_end"]), "min": 2} if hit else None
    return p


def modifications(adv: pd.DataFrame) -> tuple[dict, dict, list]:
    """Twin mods for these advisories, the time windows per (route, direction) they act on, and the ids
    that had to be skipped (no parameters could be worked out)."""
    mods = {"extra_trips": [], "remove_trips": [], "holds": []}
    windows: dict[tuple, list] = {}
    skipped = []
    for a in adv.to_dict("records"):
        p = _params(a)
        if p is None:
            skipped.append(int(a["advisory_id"]))
            continue
        kind, r, d = a.get("kind") or "add_trips", a["route_id"], int(a["direction"])
        w = (p["start"], p["end"])
        if kind == "hold_for_train":
            mods["holds"].append({"route": r, "direction": d, "stop_id": p["stop_id"], "start": p["start"],
                                  "end": p["end"], "min": p["min"]})
        elif kind == "move_bus":   # the moved bus runs both ways on the crowded route
            mods["extra_trips"].append({"route": r, "direction": None, "start": p["start"], "end": p["end"], "n": p["n"]})
            mods["remove_trips"].append({"route": p["donor"], "start": p["start"], "end": p["end"], "n": p["n"]})
            for rr in (r, p["donor"]):
                for dd in (0, 1):
                    windows.setdefault((rr, dd), []).append(w)
            continue
        else:
            x = {"route": r, "direction": d, "start": p["start"], "end": p["end"], "n": p["n"]}
            if kind == "short_turn":
                x["turn_idx"] = p["turn_idx"]
            mods["extra_trips"].append(x)
        windows.setdefault((r, d), []).append(w)
    return mods, windows, skipped


KEYS = ["route_id", "direction", "stop_id", "slot_15"]


def _grid(ev: pd.DataFrame, acted: set) -> pd.Series:
    """Mean demand load factor per route x direction x stop x slot, pooled over 30 min either side: with a
    bus every half hour a single slot often has no departure in one of the two runs, and one or two
    departures are too few to compare."""
    x = ev[[k in acted for k in zip(ev.route_id, ev.direction)]]
    lf = (x.onboard_load + x.left_behind.fillna(0)) / x.route_id.map(pd.Series(_caps()))
    g = x.assign(lf=lf).groupby(KEYS).lf.agg(["sum", "count"]).reset_index()
    parts = [g.assign(slot_15=g.slot_15 + pd.Timedelta(minutes=k)) for k in (-30, -15, 0, 15, 30)]
    p = pd.concat(parts).groupby(KEYS)[["sum", "count"]].sum()
    return p["sum"] / p["count"]


def compute(adv: pd.DataFrame) -> dict:
    d = service_day(clock.now())
    ids = ",".join(str(i) for i in adv.advisory_id)
    mods, windows, skipped = modifications(adv)
    ev0, s0 = _base_run("baseline", d.isoformat(), SEED)
    ev1, s1 = run(scenario="extra_trips", start_date=d, days=1, seed=SEED, workers=1, mods=mods, run_id=RUN_ID)
    acted = set(windows)
    g = pd.concat([_grid(ev0, acted).rename("lf_before"), _grid(ev1, acted).rename("lf_after")], axis=1).dropna().reset_index()
    mins = g.slot_15.dt.hour * 60 + g.slot_15.dt.minute
    keep = pd.Series(False, index=g.index)
    for (r, dirn), wins in windows.items():
        for a, b in wins:
            keep |= (g.route_id == r) & (g.direction == dirn) & mins.between(hhmm_to_min(a) - 15, hhmm_to_min(b) + AFTER_MIN)
    cells = g[keep & ((g.lf_after - g.lf_before).abs() >= MIN_CHANGE)].copy()

    now = iso(clock.now())
    execute("DELETE FROM advisory_effect")
    if len(cells):
        out = pd.DataFrame({"computed_at": now, "advisory_ids": ids, "route_id": cells.route_id,
                            "direction": cells.direction.astype(int), "stop_id": cells.stop_id,
                            "target_slot": cells.slot_15.map(iso), "lf_before": cells.lf_before.round(3),
                            "lf_after": cells.lf_after.round(3)})
        out.to_sql("advisory_effect", engine(), if_exists="append", index=False)

    # per advisory: the route's peak load in its window (90th percentile of departures, as in the advisory's
    # own twin test, so an add-trips card accepted alone shows the same numbers), without and with
    per = []
    for a in adv.to_dict("records"):
        p = None if int(a["advisory_id"]) in skipped else _params(a)
        if p is None:
            per.append({"advisory_id": int(a["advisory_id"]), "skipped": True})
            continue
        t0, t1 = hhmm_to_min(p["start"]), hhmm_to_min(p["end"]) + 30
        b = window_stats(ev0, a["route_id"], int(a["direction"]), t0, t1)
        f = window_stats(ev1, a["route_id"], int(a["direction"]), t0, t1)
        per.append({"advisory_id": int(a["advisory_id"]), "lf_before": b["peak_lf"], "lf_after": f["peak_lf"],
                    "left_behind_before": b["left_behind"], "left_behind_after": f["left_behind"]})
    summary = {"computed_at": now, "advisory_ids": ids, "cells": int(len(cells)), "skipped": skipped,
               "trips_added": int(s1["per_day"][0]["extra_trips"]) if s1.get("per_day") else None,
               **{k: {"before": int(s0[k]), "after": int(s1[k])} for k in ("left_behind_total", "crowded_vehicle_stops", "unmet_demand")},
               "per_advisory": per}
    execute("INSERT OR REPLACE INTO twin_run(run_id, scenario_id, created_at, status, params, summary) VALUES "
            "(:r, 'accepted', :c, 'done', :p, :s)",
            {"r": RUN_ID, "c": now, "p": json.dumps({"advisory_ids": ids, "mods": mods}), "s": json.dumps(summary)})
    return summary


def stored() -> dict | None:
    row = query("SELECT summary FROM twin_run WHERE run_id = :r", {"r": RUN_ID})
    return json.loads(row.summary.iloc[0]) if len(row) and row.summary.iloc[0] else None


def _current_ids() -> str:
    return ",".join(str(i) for i in accepted().advisory_id)


def _worker():
    try:
        while True:   # the accepted set may change while the twin runs: repeat until it settles
            adv = accepted()
            ids = ",".join(str(i) for i in adv.advisory_id)
            if not ids:
                execute("DELETE FROM advisory_effect")
                execute("DELETE FROM twin_run WHERE run_id = :r", {"r": RUN_ID})
                break
            compute(adv)
            if _current_ids() == ids:
                break
        _state["error"] = None
    except Exception as e:  # shown on the dashboard; the forecast view keeps working
        _state["error"] = str(e)
    finally:
        _state["running"] = False


def ensure_current() -> None:
    """Start a background twin run if the stored effect does not match today's accepted advisories."""
    with _lock:
        if _state["running"]:
            return
        s = stored()
        ids = _current_ids()
        if (s or {}).get("advisory_ids", "") == ids:
            return
        _state.update(running=True, error=None)
    threading.Thread(target=_worker, daemon=True).start()


def status() -> dict:
    ensure_current()
    s = stored()
    ids = _current_ids()
    ready = bool(s) and s.get("advisory_ids") == ids and bool(ids)
    return {"status": "computing" if _state["running"] else ("error" if _state["error"] else ("ready" if ready else "none")),
            "accepted": [int(i) for i in ids.split(",")] if ids else [], "error": _state["error"],
            "summary": s if ready else None}


def effect_cells() -> pd.DataFrame:
    """Stored cells, only if they belong to the current accepted set."""
    e = query("SELECT * FROM advisory_effect")
    if not len(e) or e.advisory_ids.iloc[0] != _current_ids():
        return pd.DataFrame()
    e["slot"] = pd.to_datetime(e.target_slot, utc=True).dt.tz_convert(IST)
    return e
