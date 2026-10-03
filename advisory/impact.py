"""Impact summary for the pitch (section 8.2), computed, not typed by hand.

Runs baseline vs advised timetable over simulated peak weekdays: overloaded windows are detected
on the baseline run (route-direction slots with demand LF >= 1.0 at the 90th percentile for >= 2
consecutive slots), remedied with the same formula as advisory.headway, and the day is re-run with
those extra trips. Reports the reduction in CROWDED vehicle-stops, left-behind passengers and peak
load factor, plus the extra bus-hours required.

    python -m advisory.impact [--days 3]
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from common.config import REPORTS_DIR
from db.database import query
from twin.simulate import run

TARGET_LF = 0.85


def overloaded_windows(ev: pd.DataFrame, caps: dict, modes: dict) -> list[dict]:
    e = ev[ev.route_id.map(modes) == "bus"].copy()
    e["lf"] = (e.onboard_load + e.left_behind) / e.route_id.map(caps)
    e["slot"] = e.ts.dt.floor("15min")
    out = []
    for (r, d), g in e.groupby(["route_id", "direction"]):
        s = g.groupby("slot").lf.quantile(0.9)
        on = (s >= 1.0).values
        i = 0
        while i < len(s):
            if on[i]:
                j = i
                while j + 1 < len(s) and on[j + 1]:
                    j += 1
                if j - i + 1 >= 2:
                    st, en = s.index[i], s.index[j] + pd.Timedelta(minutes=15)
                    trips_in = g[(g.slot >= st) & (g.slot < en)].trip_id.nunique()
                    hours = (en - st).total_seconds() / 3600
                    per_hour = max(trips_in / hours, 0.5)
                    peak = float(s.iloc[i:j + 1].max())
                    required = math.ceil(peak * caps[r] * per_hour / (caps[r] * TARGET_LF))
                    n = max(1, round(max(1, required - math.floor(per_hour)) * hours))
                    out.append({"route": r, "direction": int(d), "start": (st - pd.Timedelta(minutes=15)).strftime("%H:%M"),
                                "end": en.strftime("%H:%M"), "n": int(n), "peak_lf": round(peak, 2)})
                i = j + 1
            else:
                i += 1
    return out


def day_metrics(ev, caps, modes):
    e = ev[ev.route_id.map(modes) == "bus"]
    lf = (e.onboard_load + e.left_behind) / e.route_id.map(caps)
    peak = e.assign(lf=lf, slot=e.ts.dt.floor("15min")).groupby(["route_id", "direction", "slot"]).lf.quantile(0.9)
    # busiest-slot load factor: 95th percentile over route-direction-slots of the slot's P90 (the max
    # over ~1,400 slots would be a single outlier)
    return {"crowded_vehicle_stops": int((lf >= 1.0).sum()), "left_behind": int(e.left_behind.sum()),
            "peak_lf_p90": round(float(peak.quantile(0.95)), 3),
            "mean_peak_hour_lf": round(float(lf[e.ts.dt.hour.isin([8, 9, 18, 19])].mean()), 3)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--start", default="2026-09-22")
    a = ap.parse_args(argv)
    r = query("SELECT route_id, capacity_total, mode FROM route")
    caps, modes = dict(zip(r.route_id, r.capacity_total)), dict(zip(r.route_id, r["mode"]))
    rt = query("SELECT route_id, direction, SUM(run_min) m FROM route_stop GROUP BY route_id, direction")
    run_min = {(x.route_id, x.direction): x.m for x in rt.itertuples()}
    d0 = date.fromisoformat(a.start)
    days, rows = [], []
    d = d0
    while len(days) < a.days:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    tot_b, tot_a, extra_h = {}, {}, 0.0
    for i, d in enumerate(days):
        ev0, _ = run(start_date=d, days=1, seed=500 + i, workers=1, use_calendar=False, run_id=f"impact-base-{d}")
        wins = overloaded_windows(ev0, caps, modes)
        ev1, _ = run(scenario="extra_trips", start_date=d, days=1, seed=500 + i, workers=1, use_calendar=False,
                     mods={"extra_trips": wins}, run_id=f"impact-adv-{d}")
        mb, ma = day_metrics(ev0, caps, modes), day_metrics(ev1, caps, modes)
        hrs = sum(w["n"] * (run_min[(w["route"], w["direction"])] * 1.3 + 10) / 60 for w in wins)
        extra_h += hrs
        rows.append({"date": str(d), "windows": len(wins), "extra_trips": sum(w["n"] for w in wins),
                     "extra_bus_hours": round(hrs, 1), "before": mb, "after": ma, "advisories": wins})
        for k in mb:
            tot_b[k] = tot_b.get(k, 0) + mb[k]
            tot_a[k] = tot_a.get(k, 0) + ma[k]
        print(f"{d}: {len(wins)} windows, +{sum(w['n'] for w in wins)} trips; before {mb}; after {ma}")
    n = len(days)
    summ = {
        "generated_at": datetime.now().isoformat(timespec="seconds"), "days": n, "simulated": True,
        "scope": "MTC bus routes in the twin; weekdays without calendar effects",
        "crowded_vehicle_stops_per_day": {"before": round(tot_b["crowded_vehicle_stops"] / n), "after": round(tot_a["crowded_vehicle_stops"] / n)},
        "left_behind_per_day": {"before": round(tot_b["left_behind"] / n), "after": round(tot_a["left_behind"] / n)},
        "peak_lf_p90": {"before": round(tot_b["peak_lf_p90"] / n, 3), "after": round(tot_a["peak_lf_p90"] / n, 3)},
        "peak_hour_mean_lf": {"before": round(tot_b["mean_peak_hour_lf"] / n, 3), "after": round(tot_a["mean_peak_hour_lf"] / n, 3)},
        "extra_bus_hours_per_day": round(extra_h / n, 1),
        "extra_trips_per_day": round(sum(x["extra_trips"] for x in rows) / n, 1),
        "per_day": rows,
    }
    for k in ("crowded_vehicle_stops_per_day", "left_behind_per_day", "peak_lf_p90"):
        b, af = summ[k]["before"], summ[k]["after"]
        summ[k]["change"] = f"{(af / b - 1) if b else 0:+.0%}"
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "impact_summary.json").write_text(json.dumps(summ, indent=1, default=str), encoding="utf8")
    md = ["# Impact summary (simulated)", "", f"Generated {summ['generated_at']} by `python -m advisory.impact` "
          f"over {n} simulated weekdays. **Simulated data.**", "",
          "| Metric (MTC routes in the twin, per day) | Baseline | With advisories | Change |", "|---|---|---|---|"]
    for k, lbl in (("crowded_vehicle_stops_per_day", "CROWDED vehicle-stops"), ("left_behind_per_day", "Passengers left behind"),
                   ("peak_lf_p90", "Busiest-slot load factor (95th pct of route-slots)")):
        md.append(f"| {lbl} | {summ[k]['before']:,} | {summ[k]['after']:,} | {summ[k]['change']} |")
    md += [f"| Extra bus-hours required | - | {summ['extra_bus_hours_per_day']} | - |",
           f"| Extra trips | - | {summ['extra_trips_per_day']} | - |", "",
           "Windows are found on the baseline run itself (perfect foresight), so this is an upper bound on what "
           "forecast-driven advisories achieve."]
    (REPORTS_DIR / "impact_summary.md").write_text("\n".join(md), encoding="utf8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
