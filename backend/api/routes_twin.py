"""/twin/* endpoints: scenarios, async runs, what-if; /impact; /accuracy (data health)."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import date

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from api.models import BuilderPlan, TwinRunRequest, WhatIfRequest
from common import clock
from common.config import IST, REPORTS_DIR, crowd_level, iso
from db.database import execute, query

router = APIRouter(prefix="")
_RUNS: dict[str, dict] = {}


@router.get("/twin/scenarios")
def scenarios():
    from twin.scenarios import list_scenarios

    return list_scenarios()


def _run_job(run_id: str, req: TwinRunRequest):
    from twin.simulate import run, to_db

    try:
        _RUNS[run_id]["status"] = "running"
        if req.scenario == "builder":
            # compare against a normal day of the same kind, so only the plan's changes show
            dt = (req.mods or {}).get("day_type")
            others = {k: v for k, v in (req.mods or {}).items() if k != "day_type" and v}
            base_mods = {"day_type": dt if (others and dt) else "weekday"}
            base_ev, base_s = run(scenario="builder", start_date=req.start_date, days=req.days, seed=req.seed,
                                  workers=1, run_id=f"{run_id}-base", use_calendar=False, mods=base_mods)
        else:
            base_ev, base_s = run(scenario="baseline", start_date=req.start_date, days=req.days, seed=req.seed,
                                  workers=1, run_id=f"{run_id}-base", use_calendar=False)
        ev, s = run(scenario=req.scenario, start_date=req.start_date, days=req.days, seed=req.seed, mods=req.mods,
                    workers=1, run_id=run_id, use_calendar=False)
        caps = query("SELECT route_id, capacity_total FROM route").set_index("route_id").capacity_total

        def hourly(e):
            e = e.assign(lf=(e.onboard_load + e.left_behind) / e.route_id.map(caps), h=e.ts.dt.hour)
            g = e.groupby("h")
            return pd.DataFrame({"lf_p90": g.lf.quantile(0.9), "left_behind": g.left_behind.sum(),
                                 "crowded": g.lf.apply(lambda x: int((x >= 1.0).sum()))})

        hb, ha = hourly(base_ev), hourly(ev)
        hrs = sorted(set(hb.index) | set(ha.index))
        series = [{"hour": int(h), "lf_before": round(float(hb.lf_p90.get(h, 0)), 3), "lf_after": round(float(ha.lf_p90.get(h, 0)), 3),
                   "left_behind_before": int(hb.left_behind.get(h, 0)), "left_behind_after": int(ha.left_behind.get(h, 0)),
                   "crowded_before": int(hb.crowded.get(h, 0)), "crowded_after": int(ha.crowded.get(h, 0))} for h in hrs]
        clean = lambda x: {k: v for k, v in x.items() if not k.startswith("_") and k not in ("per_day",)}  # noqa: E731
        grid_b, grid_a = route_hour_grid(base_ev, caps), route_hour_grid(ev, caps)
        worse = worse_routes(grid_b, grid_a)
        fleet = None
        if req.scenario == "builder" and (req.mods or {}).get("fleet"):
            from twin.fleet import buses_to_trips
            from twin.network import load_network

            fleet = buses_to_trips(load_network(), req.mods["fleet"])[1]
        summary = {"scenario": clean(s), "baseline": clean(base_s), "hourly": series,
                   "grid": {"before": [{"route_id": r, "direction": d, "hour": h, "lf": v} for (r, d, h), v in sorted(grid_b.items())],
                            "after": [{"route_id": r, "direction": d, "hour": h, "lf": v} for (r, d, h), v in sorted(grid_a.items())]},
                   "worse_routes": worse, "fleet": fleet, "mods": req.mods,
                   "by_route": [{"route_id": r, "baseline": int(base_s["by_route_per_day"].get(r, 0)),
                                 "scenario": int(s["by_route_per_day"].get(r, 0))} for r in sorted(base_s["by_route_per_day"])]}
        _RUNS[run_id].update(status="done", summary=summary)
        execute("INSERT OR REPLACE INTO twin_run(run_id, scenario_id, created_at, status, params, summary) VALUES "
                "(:r, :s, :c, 'done', :p, :m)", {"r": run_id, "s": req.scenario, "c": iso(clock.now()),
                                                 "p": req.model_dump_json(), "m": json.dumps(summary, default=str)})
    except Exception as e:  # surfaced to the dashboard
        _RUNS[run_id].update(status="error", error=str(e))


def route_hour_grid(ev: pd.DataFrame, caps) -> dict:
    """(route, direction, hour) -> 90th percentile of the demand load factor over its vehicle-stops."""
    e = ev.assign(lf=(ev.onboard_load + ev.left_behind.fillna(0)) / ev.route_id.map(caps), h=ev.ts.dt.hour)
    q = e.groupby(["route_id", "direction", "h"]).lf.quantile(0.9)
    return {(r, int(d), int(h)): round(float(v), 3) for (r, d, h), v in q.items() if 5 <= h <= 23}


def worse_routes(before: dict, after: dict, margin: float = 0.08) -> list[str]:
    """Routes whose three busiest hours (either direction) got clearly fuller: robust to the cell-level
    noise of a single simulated day."""
    def top3(g, r):
        v = sorted((x for (rr, _, _), x in g.items() if rr == r), reverse=True)[:3]
        return sum(v) / len(v) if v else 0.0
    routes = {k[0] for k in after}
    return sorted(r for r in routes if top3(after, r) - top3(before, r) > margin and top3(after, r) >= 0.75)


@router.post("/twin/run")
def twin_run(req: TwinRunRequest):
    from twin.scenarios import SCENARIO_IDS

    if req.scenario not in SCENARIO_IDS:
        raise HTTPException(400, f"unknown scenario; choose from {SCENARIO_IDS}")
    if req.scenario == "builder":
        try:
            plan = BuilderPlan.model_validate(req.mods or {})
        except Exception as e:  # pydantic.ValidationError
            raise HTTPException(422, f"invalid plan: {e}")
        if not plan.has_changes():
            raise HTTPException(400, "add at least one condition or fleet change")
        req.mods = plan.model_dump(by_alias=True, exclude_defaults=True)
        req.mods.setdefault("day_type", "weekday")   # no day chosen = a normal weekday, whatever today's date is
    if sum(1 for r in _RUNS.values() if r["status"] in ("queued", "running")) >= 2:
        raise HTTPException(429, "two twin runs are already in progress")
    req.start_date = req.start_date or clock.now().date().isoformat()
    run_id = f"ui-{req.scenario}-{uuid.uuid4().hex[:8]}"
    _RUNS[run_id] = {"status": "queued", "scenario": req.scenario, "params": req.model_dump()}
    threading.Thread(target=_run_job, args=(run_id, req), daemon=True).start()
    return {"run_id": run_id}


@router.get("/twin/run/{run_id}")
def twin_run_status(run_id: str):
    r = _RUNS.get(run_id)
    if r is None:
        row = query("SELECT status, summary FROM twin_run WHERE run_id = :r", {"r": run_id})
        if not len(row):
            raise HTTPException(404, "unknown run_id")
        return {"run_id": run_id, "status": row.status.iloc[0], "summary": json.loads(row.summary.iloc[0] or "{}"),
                "simulated": True}
    return {"run_id": run_id, **r, "simulated": True}


@router.post("/twin/whatif")
async def twin_whatif(req: WhatIfRequest):
    from advisory.whatif import simulate_whatif

    if not req.extra_trips:
        raise HTTPException(400, "extra_trips must not be empty")
    d = req.date or clock.now().date().isoformat()
    return await run_in_threadpool(simulate_whatif, req.base_scenario, [x.model_dump() for x in req.extra_trips], d, req.seed)


@router.get("/impact")
def impact():
    p = REPORTS_DIR / "impact_summary.json"
    if not p.exists():
        raise HTTPException(404, "impact summary not computed yet: python -m advisory.impact")
    d = json.loads(p.read_text(encoding="utf8"))
    d.pop("per_day", None)
    return d


@router.get("/accuracy")
def accuracy(hours: int = 24):
    """Accuracy of 1-hour-ahead forecasts over the last `hours` versus what then happened."""
    now = pd.Timestamp(clock.now()).tz_convert(IST)
    f = query("""SELECT target_slot, route_id, direction, stop_id, model, pred_lf FROM forecast
                 WHERE horizon = 4 AND target_slot >= :a AND target_slot < :b""",
              {"a": iso(now - pd.Timedelta(hours=hours)), "b": iso(now - pd.Timedelta(minutes=15))})
    if not len(f):
        return {"n": 0, "models": {}, "note": "no matured 1-hour-ahead forecasts yet"}
    a = query("""SELECT e.slot_15 AS target_slot, e.route_id, e.direction, e.stop_id,
                        MAX(e.onboard_load + COALESCE(e.left_behind,0)) * 1.0 / r.capacity_total AS lf
                 FROM event e JOIN route r ON r.route_id = e.route_id WHERE e.slot_15 >= :a
                 GROUP BY e.slot_15, e.route_id, e.direction, e.stop_id""", {"a": f.target_slot.min()})
    m = f.merge(a, on=["target_slot", "route_id", "direction", "stop_id"])
    out = {}
    for mdl, g in m.groupby("model"):
        lv_ok = (g.pred_lf.map(crowd_level) == g.lf.map(crowd_level)).mean()
        out[mdl] = {"n": len(g), "mae_lf": round(float((g.pred_lf - g.lf).abs().mean()), 4), "level_acc": round(float(lv_ok), 3)}
    return {"hours": hours, "models": out, "n": len(m)}
