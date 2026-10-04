"""Depot-level frequency advisories (section 8.2): detect -> propose -> verify.

Detect: for each route and direction, scan the next 3 h of forecasts; flag slots where the predicted
load factor is >= 1.0, or >= 0.85 with upper bound >= 1.1, at any stop; a window needs >= 2
consecutive flagged slots.
Propose: required = ceil(peak_demand_per_hour / (capacity * 0.85)); extra = required - scheduled;
new headway = scheduled_headway * scheduled / (scheduled + extra).
Verify: advisory.whatif runs the twin with the extra trips. Accepted only if the route's peak LF
drops below 1.0 and no neighbouring route rises above 1.0; otherwise extra trips are increased
(up to MAX_EXTRA_PER_HOUR) and re-tested, then stored as rejected_by_whatif if still failing.

    python -m advisory.headway     # run once at the current (demo) clock
"""
from __future__ import annotations

import json
import math
import threading

import numpy as np
import pandas as pd

from advisory import rules
from advisory.whatif import simulate_whatif
from common import clock
from common.config import IST, corridor, iso
from db.database import engine, execute, query

TARGET_LF = 0.85
MIN_SLOTS = 2
MAX_EXTRA_PER_HOUR = 6
# the scheduler and the dashboard's "Read heatmap now" take turns, so a window is never proposed twice
_run_lock = threading.Lock()


def latest_lstm() -> pd.DataFrame:
    m = query("SELECT MAX(made_at) m FROM forecast WHERE model='lstm'").m.iloc[0]
    if m is None:
        return pd.DataFrame()
    f = query("SELECT * FROM forecast WHERE made_at = :m AND model = 'lstm'", {"m": m})
    f["slot"] = pd.to_datetime(f.target_slot, utc=True).dt.tz_convert(IST)
    return f


def detect(now: pd.Timestamp | None = None) -> list[dict]:
    f = latest_lstm()
    if not len(f):
        return []
    m = f.made_at.iloc[0]
    f["flag"] = (f.pred_lf >= 1.0) | ((f.pred_lf >= 0.85) & (f.hi >= 1.1))
    stops = query("SELECT stop_id, name FROM stop").set_index("stop_id").name
    wins = []
    for (r, d), g in f.groupby(["route_id", "direction"]):
        per_slot = g.groupby("slot").agg(flag=("flag", "any"), lf=("pred_lf", "max"), hi=("hi", "max"))
        run_start, run_len = None, 0
        slots = list(per_slot.index) + [None]
        for s in slots:
            on = s is not None and per_slot.loc[s, "flag"]
            if on:
                run_start = run_start or s
                run_len += 1
            elif run_len >= MIN_SLOTS:
                sel = g[(g.slot >= run_start) & (g.slot < run_start + pd.Timedelta(minutes=15 * run_len))]
                top = sel.loc[sel.pred_lf.idxmax()]
                wins.append({"route_id": r, "direction": int(d), "start": run_start,
                             "end": run_start + pd.Timedelta(minutes=15 * run_len), "peak_lf": float(top.pred_lf),
                             "peak_hi": float(top.hi), "peak_stop": stops.get(top.stop_id, top.stop_id),
                             "minutes": 15 * run_len, "data_source": top.data_source, "made_at": m})
                run_start, run_len = None, 0
            else:
                run_start, run_len = None, 0
    return wins


def propose(w: dict) -> dict:
    r = query("SELECT capacity_total FROM route WHERE route_id = :r", {"r": w["route_id"]}).capacity_total.iloc[0]
    t = query("SELECT scheduled_start FROM trip WHERE route_id = :r AND direction = :d AND scheduled_start >= :a "
              "AND scheduled_start < :b", {"r": w["route_id"], "d": w["direction"],
                                           "a": iso(w["start"] - pd.Timedelta(minutes=60)), "b": iso(w["end"])})
    hours = max(w["minutes"] / 60.0, 0.5)
    sched_per_hour = max(len(t) / ((w["end"] - w["start"]).total_seconds() / 3600 + 1.0), 0.5)
    peak_demand_per_hour = w["peak_lf"] * r * sched_per_hour
    required = math.ceil(peak_demand_per_hour / (r * TARGET_LF))
    extra_per_hour = max(1, required - math.floor(sched_per_hour))
    extra = max(1, round(extra_per_hour * hours))
    sched_trips = max(1, round(sched_per_hour * hours))
    headway = 60.0 / sched_per_hour
    new_headway = headway * sched_trips / (sched_trips + extra)
    return {"extra_trips": int(extra), "scheduled_trips": int(sched_trips), "headway": round(headway, 1),
            "new_headway": round(new_headway, 1), "capacity": int(r)}


def run_advisories(now: pd.Timestamp | None = None, seed: int = 7, verify: bool = True) -> list[dict]:
    with _run_lock:
        return _run(now, seed, verify)


def _run(now: pd.Timestamp | None, seed: int, verify: bool) -> list[dict]:
    now = pd.Timestamp(now or clock.now()).tz_convert(IST)
    depots = {r["route_id"]: r.get("depot") for r in corridor()["routes"]}
    out = []
    fc = latest_lstm()
    for w in detect(now):
        # skip windows already covered by an active/accepted advisory
        dup = query("SELECT advisory_id FROM advisory WHERE route_id = :r AND direction = :d AND status IN "
                    "('active','accepted') AND slot_start < :e AND slot_end > :s",
                    {"r": w["route_id"], "d": w["direction"], "s": iso(w["start"]), "e": iso(w["end"])})
        if len(dup):
            continue
        p = propose(w)
        start = (w["start"] - pd.Timedelta(minutes=15)).strftime("%H:%M")
        end = w["end"].strftime("%H:%M")
        n = p["extra_trips"]
        result, status = None, "active"
        if verify:
            while True:
                res = simulate_whatif("baseline", [{"route": w["route_id"], "direction": w["direction"],
                                                    "start": start, "end": end, "n": n}], d=now.date().isoformat(), seed=seed)
                tgt = [x for x in res["table"] if x["role"] == "target"][0]
                nbs = [x for x in res["table"] if x["role"] == "neighbour"]
                ok = tgt["lf_after"] < 1.0 and all(x["lf_after"] <= max(1.0, x["lf_before"]) for x in nbs)
                result = res
                if ok or n >= MAX_EXTRA_PER_HOUR * max(1, w["minutes"] / 60):
                    break
                n += 1
            status = "active" if ok else "rejected_by_whatif"
            lf_before, lf_after = tgt["lf_before"], tgt["lf_after"]
            nb_after = max([x["lf_after"] for x in nbs], default=None)
        else:
            lf_before, lf_after, nb_after = w["peak_lf"], None, None
        dur_h = (w["end"] - w["start"]).total_seconds() / 3600 + 0.25
        rt = query("SELECT SUM(run_min) m FROM route_stop WHERE route_id = :r AND direction = :d",
                   {"r": w["route_id"], "d": w["direction"]}).m.iloc[0]
        veh_hours = round(n * (rt * 1.3 + 10) / 60, 1)
        rec = {
            "created_at": iso(now), "route_id": w["route_id"], "depot": depots.get(w["route_id"]),
            "slot_start": iso(w["start"]), "slot_end": iso(w["end"]), "direction": w["direction"],
            "reason": f"forecast LF {w['peak_lf']:.2f} at {w['peak_stop']} for {w['minutes']} min",
            "action": f"add {n} trip{'s' if n > 1 else ''} between {start} and {end} "
                      f"(headway {p['headway']:.0f} -> {p['headway'] * p['scheduled_trips'] / (p['scheduled_trips'] + n):.0f} min)",
            "extra_trips": int(n), "expected_lf_before": lf_before, "expected_lf_after": lf_after,
            "neighbour_lf_after": nb_after, "extra_vehicle_hours": veh_hours, "status": status,
            "data_source": w["data_source"], "kind": "add_trips",
            "params": json.dumps({"start": start, "end": end, "n": int(n)}),
        }
        rows = [rec]
        ctx = {**rec, "_start": start, "_end": end, "_cycle_min": rt * 2 + 20}
        for rule in (rules.short_turn, rules.move_bus):
            extra = rule(fc, w, ctx)
            if extra:
                rows.append({k: v for k, v in extra.items() if not k.startswith("_")})
        pd.DataFrame(rows).to_sql("advisory", engine(), if_exists="append", index=False)
        out.append({**rec, "whatif": result["table"] if result else None})
        out.extend(rows[1:])
    for h in rules.hold_for_train(fc, now, depots):
        dup = query("SELECT advisory_id FROM advisory WHERE route_id = :r AND direction = :d AND kind = 'hold_for_train' "
                    "AND status IN ('active','accepted') AND slot_start < :e AND slot_end > :s",
                    {"r": h["route_id"], "d": h["direction"], "s": h["slot_start"], "e": h["slot_end"]})
        if not len(dup):
            pd.DataFrame([h]).to_sql("advisory", engine(), if_exists="append", index=False)
            out.append(h)
    return out


if __name__ == "__main__":
    print(json.dumps(run_advisories(), indent=1, default=str))
