"""/plan and /plan/window (multimodal trip planning) and /advisories (depot dashboard)."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from api.models import PlanRequest, PlanWindowRequest
from db.database import execute, query

router = APIRouter()


@router.post("/plan")
async def plan(req: PlanRequest):
    from routing.recommend import plan as do_plan

    try:
        return await run_in_threadpool(do_plan, req.from_stop, req.to_stop, req.depart_at, req.prefer_low_crowd)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/plan/window")
async def plan_window(req: PlanWindowRequest):
    """Ranked itineraries for every 15-minute departure slot in depart_at +/- window_min."""
    from routing.window import plan_window as do_plan

    try:
        return await run_in_threadpool(do_plan, req.from_stop, req.to_stop, req.depart_at, req.window_min,
                                       req.filters.model_dump(), req.rank_by)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/advisories")
def advisories(depot: str | None = None, route_id: str | None = None, status: str | None = "active,accepted",
               current: bool = False, limit: int = 50):
    """current=true leaves out advisories whose window has already ended."""
    cond, p = [], {"lim": limit}
    if current:
        from common import clock
        from common.config import iso

        cond.append("slot_end > :now")
        p["now"] = iso(clock.now())
    if depot:
        cond.append("depot = :depot")
        p["depot"] = depot
    if route_id:
        cond.append("route_id = :r")
        p["r"] = route_id
    if status:
        sts = [s.strip() for s in status.split(",") if s.strip()]
        cond.append("status IN (" + ",".join(f":s{i}" for i in range(len(sts))) + ")")
        p.update({f"s{i}": s for i, s in enumerate(sts)})
    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    rows = query(f"SELECT a.*, r.short_name AS route FROM advisory a JOIN route r USING(route_id) {where} "
                 f"ORDER BY created_at DESC, advisory_id DESC LIMIT :lim", p).replace({np.nan: None})
    ds = set(rows.data_source) if len(rows) else set()
    flag = "mixed" if "mixed" in ds or {"twin", "camera"} <= ds else ("camera" if "camera" in ds else ("twin" if ds else "none"))
    return {"data_source": flag, "simulated": flag in ("twin", "mixed"), "advisories": rows.to_dict("records")}


@router.post("/advisories/{advisory_id}/{action}")
def advisory_action(advisory_id: int, action: str):
    """accept | dismiss | undo (an accepted advisory goes back to active). Accepting or undoing re-runs
    the twin with all accepted advisories in the background (GET /fleet/effect shows progress)."""
    if action not in ("accept", "dismiss", "undo"):
        raise HTTPException(400, "action must be accept, dismiss or undo")
    row = query("SELECT status FROM advisory WHERE advisory_id = :i", {"i": advisory_id})
    if not len(row):
        raise HTTPException(404, "no such advisory")
    if action == "undo" and row.status.iloc[0] != "accepted":
        raise HTTPException(400, "only an accepted advisory can be undone")
    status = {"accept": "accepted", "dismiss": "dismissed", "undo": "active"}[action]
    execute("UPDATE advisory SET status = :s WHERE advisory_id = :i", {"s": status, "i": advisory_id})
    from advisory.effect import ensure_current

    ensure_current()
    return {"ok": True, "advisory_id": advisory_id, "status": status}


@router.post("/advisories/run")
async def advisories_run():
    """Trigger detection + what-if verification now (normally run by the scheduler)."""
    from advisory.headway import run_advisories

    out = await run_in_threadpool(run_advisories)
    return {"created": len(out), "advisories": out}
