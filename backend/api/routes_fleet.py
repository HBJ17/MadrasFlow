"""/fleet/heatmap: crowd estimates for the depot dashboard from the latest LSTM forecast (built on the
digital twin's history), in 15-minute slots over the next 3 hours. Not live counts.

  GET /fleet/heatmap                          one row per route and direction (busiest stop per slot)
  GET /fleet/heatmap/{route_id}?view=stops    the route's stops in order x slots
  GET /fleet/heatmap/{route_id}?view=buses    each scheduled bus trip x the stops it passes
"""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from api.deps import routes_df
from api.live import cum_minutes, flag, latest_forecast, trips_today
from common import clock
from common.config import crowd_level, iso

router = APIRouter()


def _cell(r) -> dict:
    lf = float(r.pred_lf)
    return {"lf": round(lf, 3), "lo": None if pd.isna(r.lo) else round(float(r.lo), 3),
            "hi": None if pd.isna(r.hi) else round(float(r.hi), 3), "level": crowd_level(lf),
            "people": None if pd.isna(r.pred_load) else int(round(float(r.pred_load)))}


def _route_label(rid: str, d: int, rs: pd.DataFrame) -> dict:
    meta = routes_df().set_index("route_id").loc[rid]
    return {"route_id": rid, "direction": int(d), "route": meta.short_name, "mode": meta["mode"], "depot": meta.depot,
            "capacity": int(meta.capacity_total), "from": rs.name.iloc[0], "to": rs.name.iloc[-1]}


@router.get("/fleet/heatmap")
def fleet_overview():
    fc = latest_forecast("lstm")
    if not len(fc):
        return {"made_at": None, "slots": [], "rows": [], "data_source": "none", "simulated": False}
    slots = sorted(fc.slot.unique())
    rows = []
    for (rid, d), g in fc.groupby(["route_id", "direction"]):
        rs = cum_minutes(rid, int(d))
        stop_name = dict(zip(rs.stop_id, rs.name))
        top = g.loc[g.groupby("slot").pred_lf.idxmax()].set_index("slot")
        cells = []
        for s in slots:
            if s in top.index:
                r = top.loc[s]
                cells.append({**_cell(r), "stop": stop_name.get(r.stop_id, r.stop_id)})
            else:
                cells.append(None)
        rows.append({**_route_label(rid, d, rs), "cells": cells})
    return {"made_at": fc.made_at.iloc[0], "slots": [iso(pd.Timestamp(s)) for s in slots], "rows": rows,
            "data_source": flag(fc), "simulated": flag(fc) in ("twin", "mixed")}


@router.get("/fleet/heatmap/{route_id}")
def fleet_route(route_id: str, direction: int = Query(0, ge=0, le=1), view: str = Query("stops", pattern="^(stops|buses)$")):
    if route_id not in set(routes_df().route_id):
        raise HTTPException(404, "unknown route")
    fc = latest_forecast("lstm")
    rs = cum_minutes(route_id, direction)
    base = {"view": view, **_route_label(route_id, direction, rs)}
    if not len(fc):
        return {**base, "slots": [], "rows": [], "stops": [], "data_source": "none", "simulated": False}
    g = fc[(fc.route_id == route_id) & (fc.direction == direction)]
    slots = sorted(fc.slot.unique())
    key = {(r.stop_id, r.slot): r for r in g.itertuples(index=False)}
    stops = [{"stop_id": s, "name": n} for s, n in zip(rs.stop_id, rs.name)]
    env = {**base, "made_at": fc.made_at.iloc[0], "data_source": flag(g), "simulated": flag(g) in ("twin", "mixed")}
    if view == "stops":
        rows = [{"stop_id": s["stop_id"], "name": s["name"],
                 "cells": [_cell(key[(s["stop_id"], t)]) if (s["stop_id"], t) in key else None for t in slots]} for s in stops]
        return {**env, "slots": [iso(pd.Timestamp(s)) for s in slots], "rows": rows}

    # buses: each trip that runs during the forecast window, with the forecast at the slot it passes each stop
    now = pd.Timestamp(clock.now())
    t0, t1 = slots[0], slots[-1] + pd.Timedelta(minutes=15)
    trips = trips_today(now)
    trips = trips[(trips.route_id == route_id) & (trips.direction == direction)].copy()
    trips["start"] = pd.to_datetime(trips.scheduled_start, utc=True).dt.tz_convert(t0.tz)
    end_min = float(rs.cum.iloc[-1])
    trips = trips[(trips.start < t1) & (trips.start + pd.Timedelta(minutes=end_min) >= t0)].sort_values("start")
    rows = []
    for tr in trips.itertuples(index=False):
        cells = []
        for s, cum in zip(rs.stop_id, rs.cum):
            when = tr.start + pd.Timedelta(minutes=float(cum))
            slot = when.floor("15min")
            r = key.get((s, slot))
            cells.append({**_cell(r), "at": iso(when)} if r is not None else None)
        if any(cells):
            rows.append({"trip_id": tr.trip_id, "vehicle_id": tr.vehicle_id, "start": iso(tr.start), "cells": cells})
    return {**env, "stops": stops, "rows": rows}
