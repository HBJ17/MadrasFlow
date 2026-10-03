"""What-if testing through the twin's public run() (section 5.7). This is the only module outside
twin/ allowed to call the twin.

simulate_whatif(base_scenario, modifications) returns the load-factor change on the target route
and on neighbouring routes (routes sharing a station), so a frequency increase that just moves the
crowd elsewhere is visible.

Load factor here is the demand load factor (onboard + left behind) / capacity, matching the
predictor. 'Peak LF' for a route in a window = the 90th percentile over its vehicle-stop departures
(robust to a single vehicle).
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache

import numpy as np
import pandas as pd

from common.config import IST, hhmm_to_min
from db.database import query
from twin.simulate import run

PEAK_Q = 0.9


@lru_cache(maxsize=16)
def _base_run(base_scenario: str, d: str, seed: int):
    ev, s = run(scenario=base_scenario, start_date=d, days=1, seed=seed, workers=1, run_id=f"whatif-base-{d}-{seed}")
    return ev, s


@lru_cache(maxsize=1)
def neighbours() -> dict:
    rs = query("SELECT rs.route_id, s.station_id FROM route_stop rs JOIN stop s ON s.stop_id = rs.stop_id")
    st = rs.groupby("route_id").station_id.agg(set)
    return {r: sorted(o for o in st.index if o != r and st[r] & st[o]) for r in st.index}


def _caps():
    r = query("SELECT route_id, capacity_total FROM route")
    return dict(zip(r.route_id, r.capacity_total))


def window_stats(ev: pd.DataFrame, route_id: str, direction: int | None, t0: int, t1: int) -> dict:
    cap = _caps()
    m = (ev.route_id == route_id)
    if direction is not None:
        m &= ev.direction == direction
    mins = ev.ts.dt.hour * 60 + ev.ts.dt.minute
    x = ev[m & (mins >= t0) & (mins < t1)]
    if not len(x):
        return {"peak_lf": 0.0, "mean_lf": 0.0, "left_behind": 0, "crowded_vs": 0}
    lf = (x.onboard_load + x.left_behind.fillna(0)) / cap[route_id]
    return {"peak_lf": round(float(np.quantile(lf, PEAK_Q)), 3), "mean_lf": round(float(lf.mean()), 3),
            "left_behind": int(x.left_behind.sum()), "crowded_vs": int((lf >= 1.0).sum())}


def simulate_whatif(base_scenario: str = "baseline", extra_trips: list | None = None, d: str | None = None,
                    seed: int = 7) -> dict:
    """extra_trips: [{route, direction?, start 'HH:MM', end 'HH:MM', n}]. Compares the same day and seed
    with and without the extra trips, over each modification's window (+30 min after)."""
    d = d or date.today().isoformat()
    extra_trips = extra_trips or []
    ev0, _ = _base_run(base_scenario, d, seed)
    mods = {"extra_trips": extra_trips}
    scen = "extra_trips" if base_scenario == "baseline" else base_scenario
    ev1, s1 = run(scenario=scen, start_date=d, days=1, seed=seed, workers=1, mods=mods, run_id=f"whatif-{d}-{seed}")
    rows = []
    nb = neighbours()
    for x in extra_trips:
        t0, t1 = hhmm_to_min(x["start"]), hhmm_to_min(x["end"]) + 30
        for r, role in [(x["route"], "target")] + [(n, "neighbour") for n in nb.get(x["route"], [])]:
            dirn = x.get("direction") if role == "target" else None
            b, a = window_stats(ev0, r, dirn, t0, t1), window_stats(ev1, r, dirn, t0, t1)
            rows.append({"route_id": r, "role": role, "direction": dirn, "window": f"{x['start']}-{x['end']}",
                         "lf_before": b["peak_lf"], "lf_after": a["peak_lf"],
                         "mean_lf_before": b["mean_lf"], "mean_lf_after": a["mean_lf"],
                         "left_behind_before": b["left_behind"], "left_behind_after": a["left_behind"],
                         "crowded_before": b["crowded_vs"], "crowded_after": a["crowded_vs"]})
    return {"date": d, "seed": seed, "base_scenario": base_scenario, "extra_trips": extra_trips, "table": rows,
            "simulated": True, "data_source": "twin"}
