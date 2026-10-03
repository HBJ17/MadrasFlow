"""Public entry point of the twin (section 5.6).

    run(config, scenario, start_date, days, seed) -> (events_df, summary)

Deterministic given the seed: one numpy Generator per run, with one child generator per day
(spawned up front), so results do not depend on how days are spread across processes.

CLI:
    python -m twin.simulate --scenario baseline --start 2026-10-01 --days 1 --seed 42 [--to-db] [--parquet]
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta

import numpy as np
import pandas as pd

from common.config import DATA_DIR, IST, PROCESSED_DIR, RAW_DIR, corridor, crowd_level, demand_config
from twin.agents import TwinSim
from twin.demand import DayContext, generate_arrivals
from twin.network import load_network
from twin.paths import PathIndex
from twin.scenarios import resolve

EVENT_COLUMNS = ["t_min", "route_id", "trip_id", "vehicle_id", "stop_id", "direction", "boardings", "alightings",
                 "onboard_load", "waiting_count", "left_behind", "payment_mode", "fare_inr"]

_PATHS = None


def _paths(net):
    global _PATHS
    if _PATHS is None:
        _PATHS = PathIndex(net, demand_config().get("min_trip_km", 1.0))
    return _PATHS


# ------------------------------------------------------------------------------- day context
def _holidays() -> dict:
    p = RAW_DIR / "holidays_tn.csv"
    if not p.exists():
        return {}
    h = pd.read_csv(p)
    return dict(zip(pd.to_datetime(h.date).dt.date, h.name))


def _weather_daily() -> dict:
    p = RAW_DIR / "weather_hourly.csv"
    if not p.exists():
        return {}
    w = pd.read_csv(p)
    w["ts"] = pd.to_datetime(w.ts, utc=True).dt.tz_convert(IST)
    w = w[(w.ts.dt.hour >= 5) & (w.ts.dt.hour <= 23)]
    return w.groupby(w.ts.dt.date).precip_mm.sum().to_dict()


def day_context(d: date, dcfg: dict) -> DayContext:
    hol = _holidays()
    day_type = "holiday" if d in hol else ("weekend" if d.weekday() >= 5 else "weekday")
    precip = float(_weather_daily().get(d, 0.0))
    wc = dcfg["weather"]
    weather = "heavy" if precip >= wc["heavy_rain_mm_per_day"] else ("light" if precip >= wc["light_rain_mm_per_day"] else "dry")
    ev = pd.read_csv(DATA_DIR / "events.csv")
    st, en = pd.to_datetime(ev.start_ts), pd.to_datetime(ev.end_ts)
    active = ev[(st.dt.date <= d) & (en.dt.date >= d)].to_dict("records")
    return DayContext(pd.Timestamp(d), day_type, precip, weather, active)


# ------------------------------------------------------------------------------- one day
def simulate_day(d: date, scenario: str, rng: np.random.Generator, run_id: str, mods: dict | None = None,
                 use_calendar: bool = True, dcfg: dict | None = None):
    net = load_network()
    paths = _paths(net)
    dcfg = dcfg or demand_config()
    ccfg = corridor()
    ctx = day_context(d, dcfg)
    scen = resolve(scenario, ctx, net, dcfg, mods, use_calendar=use_calendar)
    if scen.day_type == "weekend":
        ctx.day_type = "weekend"
    sim = TwinSim(net, paths, dcfg, ccfg, scen, ctx, rng, run_id)
    arrivals = generate_arrivals(paths, net, dcfg, ctx, scen, rng, sim.svc_start, sim.svc_end)
    events, unmet, stats = sim.run(arrivals)
    ev = pd.DataFrame(events, columns=EVENT_COLUMNS)
    base = pd.Timestamp(d).tz_localize(IST)
    ts = base + pd.to_timedelta(ev.t_min.round(4), unit="m")
    ev.insert(0, "ts", ts.dt.round("s"))
    ev.insert(1, "slot_15", ev.ts.dt.floor("15min"))
    ev = ev.drop(columns="t_min")
    ev["source"] = "twin"
    ev["scenario_id"] = scenario
    ev["run_id"] = run_id
    um = pd.DataFrame(unmet, columns=["t_min", "stop_id", "route_id", "reason"])
    um["date"] = d.isoformat()
    stats.update({"date": d.isoformat(), "day_type": ctx.day_type, "weather": ctx.weather,
                  "precip_mm": round(ctx.precip_mm, 1), "tags": scen.tags, "arrivals": len(arrivals),
                  "trips_run": len(sim.timetable), "extra_trips": int(sim.timetable.extra.sum())})
    tt = sim.timetable
    stats["_trips"] = pd.DataFrame({
        "trip_id": tt.trip_id, "route_id": tt.route_id, "direction": tt.direction,
        "scheduled_start": (base + pd.to_timedelta(tt.start_min, unit="m")).dt.round("s"), "vehicle_id": tt.vehicle_id})
    return ev, um, stats


def _day_worker(args):
    d, scenario, rng, run_id, mods, use_calendar, dcfg = args
    return simulate_day(d, scenario, rng, run_id, mods, use_calendar, dcfg)


# ------------------------------------------------------------------------------- run
def run(config: dict | None = None, scenario: str = "baseline", start_date: date | str | None = None, days: int = 1,
        seed: int = 42, mods: dict | None = None, workers: int | None = None, use_calendar: bool = True,
        run_id: str | None = None):
    """Simulate `days` consecutive days. Returns (events_df, summary).

    events_df conforms to the event table (ts/slot_15 as tz-aware timestamps, source='twin').
    `config` may override demand parameters (dict merged over demand_config()), used by calibrate.py.
    """
    if start_date is None:
        start_date = date.today()
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    run_id = run_id or f"{scenario}-{start_date:%Y%m%d}-{days}d-s{seed}-{uuid.uuid4().hex[:6]}"
    root = np.random.default_rng(seed)
    rngs = root.spawn(days)
    dlist = [start_date + timedelta(days=i) for i in range(days)]
    t0 = time.time()
    dcfg = None
    if config:
        dcfg = demand_config()
        for k, v in config.items():
            dcfg[k] = {**dcfg[k], **v} if isinstance(v, dict) and isinstance(dcfg.get(k), dict) else v
    if workers is None:
        workers = min(days, max(1, (os.cpu_count() or 2) - 1))
    if workers > 1 and days > 1:
        load_network()  # build cache once before starting workers
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_day_worker, [(d, scenario, r, run_id, mods, use_calendar, dcfg)
                                                for d, r in zip(dlist, rngs)]))
    else:
        results = [simulate_day(d, scenario, r, run_id, mods, use_calendar, dcfg) for d, r in zip(dlist, rngs)]
    events = pd.concat([r[0] for r in results], ignore_index=True)
    unmet = pd.concat([r[1] for r in results], ignore_index=True)
    trips = pd.concat([r[2].pop("_trips") for r in results], ignore_index=True)
    summary = summarize(events, unmet, [r[2] for r in results])
    summary["_trips"] = trips
    summary.update({"run_id": run_id, "scenario_id": scenario, "seed": seed, "start_date": start_date.isoformat(),
                    "days": days, "elapsed_s": round(time.time() - t0, 1)})
    summary["_unmet"] = unmet
    return events, summary


def summarize(events: pd.DataFrame, unmet: pd.DataFrame, day_stats: list) -> dict:
    net = load_network()
    routes = net.routes.set_index("route_id")
    ev = events.copy()
    ev["mode"] = ev.route_id.map(routes["mode"])
    ev["lf"] = ev.onboard_load / ev.route_id.map(routes.capacity_total)
    ev["level"] = ev.lf.map(crowd_level)
    ev["hour"] = ev.ts.dt.hour
    ndays = max(1, len(day_stats))
    boardings = float(ev.boardings.sum())
    lf_by_hour = ev.groupby("hour").lf.describe(percentiles=[0.5, 0.9])[["mean", "50%", "90%", "max"]].round(3)
    stats = pd.DataFrame(day_stats)
    wait = stats.wait_min.sum() / max(1, stats.boardings.sum())
    return {
        "per_day": day_stats,
        "boardings_total": int(boardings),
        "boardings_per_day": round(boardings / ndays),
        "by_mode_per_day": (ev.groupby("mode").boardings.sum() / ndays).round().astype(int).to_dict(),
        "by_route_per_day": (ev.groupby("route_id").boardings.sum() / ndays).round().astype(int).to_dict(),
        "crowded_vehicle_stops": int((ev.level == "CROWDED").sum()),
        "level_counts": ev.level.value_counts().to_dict(),
        "left_behind_total": int(ev.left_behind.sum()),
        "unmet_demand": int(len(unmet)),
        "unmet_by_reason": unmet.reason.value_counts().to_dict() if len(unmet) else {},
        "avg_wait_min": round(float(wait), 2),
        "peak_lf": round(float(ev.lf.max()), 3),
        "lf_by_hour": {int(h): r.to_dict() for h, r in lf_by_hour.iterrows()},
    }


def to_db(events: pd.DataFrame, summary: dict, params: dict | None = None, replace_run: bool = False):
    from db.database import engine, execute, write_events
    from common.config import iso

    ev = events.copy()
    ev["ts"] = ev.ts.map(iso)
    ev["slot_15"] = ev.slot_15.map(iso)
    n = write_events(ev)
    s = {k: v for k, v in summary.items() if not k.startswith("_")}
    execute("INSERT OR REPLACE INTO twin_run(run_id, scenario_id, created_at, status, params, summary) "
            "VALUES (:r,:s,:c,'done',:p,:m)",
            {"r": summary["run_id"], "s": summary["scenario_id"], "c": iso(pd.Timestamp.now(tz=IST)),
             "p": json.dumps(params or {}), "m": json.dumps(s, default=str)})
    trips = summary.get("_trips")
    if trips is not None and len(trips):
        t = trips.copy()
        t["scheduled_start"] = t.scheduled_start.map(iso)
        # a simulated day's trips replace that day's vehicle-less template trips written by db.seed
        for d in sorted({x[:10] for x in t.scheduled_start}):
            execute("DELETE FROM trip WHERE vehicle_id IS NULL AND scheduled_start >= :a AND scheduled_start < :b",
                    {"a": f"{d}T00:00:00", "b": f"{d}T99"})
        t[["trip_id"]].to_sql("_trip_ids", engine(), if_exists="replace", index=False)
        execute("DELETE FROM trip WHERE trip_id IN (SELECT trip_id FROM _trip_ids)")
        execute("DROP TABLE IF EXISTS _trip_ids")
        t.to_sql("trip", engine(), if_exists="append", index=False, chunksize=20000)
    um = summary.get("_unmet")
    if um is not None and len(um):
        u = um.copy()
        base = pd.to_datetime(u.date).dt.tz_localize(IST)
        u["slot_15"] = (base + pd.to_timedelta(u.t_min, unit="m")).dt.floor("15min").map(iso)
        agg = u.groupby(["date", "slot_15", "stop_id", "route_id", "reason"], dropna=False).size().reset_index(name="n")
        agg["run_id"] = summary["run_id"]
        agg.to_sql("unmet_demand", engine(), if_exists="append", index=False)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="baseline")
    ap.add_argument("--start", default=None)
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--no-calendar", action="store_true", help="ignore observed weather/events/holidays")
    ap.add_argument("--to-db", action="store_true")
    ap.add_argument("--parquet", action="store_true")
    a = ap.parse_args()
    ev, s = run(scenario=a.scenario, start_date=a.start, days=a.days, seed=a.seed, workers=a.workers,
                use_calendar=not a.no_calendar)
    printable = {k: v for k, v in s.items() if k not in ("lf_by_hour", "per_day") and not k.startswith("_")}
    print(json.dumps(printable, indent=1, default=str))
    print(f"events: {len(ev):,}")
    if a.parquet:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        p = PROCESSED_DIR / f"events_{s['run_id']}.parquet"
        ev.to_parquet(p, index=False)
        print("wrote", p)
    if a.to_db:
        print("db rows:", to_db(ev, s, vars(a)))


if __name__ == "__main__":
    main()
