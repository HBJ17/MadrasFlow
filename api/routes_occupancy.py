"""Occupancy and forecast reads (section 9): /occupancy/route, /occupancy/stop, /vehicle, /forecast,
/history, /wait-or-go. Every response carries data_source so the UI can show the simulated badge."""
from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from api.deps import route_stops_df, stop_ids
from api.live import cum_minutes, flag, forecast_at, latest_forecast, route_meta, upcoming
from common import clock
from common.config import IST, crowd_level, iso
from db.database import query

router = APIRouter()


def _now(at: str | None) -> pd.Timestamp:
    if at:
        t = pd.Timestamp(at)
        return (t.tz_localize(IST) if t.tzinfo is None else t).tz_convert(IST)
    return pd.Timestamp(clock.now()).tz_convert(IST)


def _check_route(route_id: str):
    if route_id not in route_meta():
        raise HTTPException(404, f"unknown route_id {route_id!r}")


def _envelope(fc: pd.DataFrame, **kw) -> dict:
    ds = flag(fc)
    return {"made_at": fc.made_at.iloc[0] if len(fc) else None, "model": fc.model.iloc[0] if len(fc) else None,
            "data_source": ds, "simulated": ds in ("twin", "mixed"), **kw}


@router.get("/occupancy/route/{route_id}")
def occupancy_route(route_id: str, direction: int = Query(0, ge=0, le=1), at: str | None = None,
                    horizon_slots: int = Query(12, ge=1, le=12), model: str = "lstm"):
    _check_route(route_id)
    now = _now(at)
    fc = latest_forecast(model)
    g = cum_minutes(route_id, direction)
    f = fc[(fc.route_id == route_id) & (fc.direction == direction)] if len(fc) else fc
    slots = sorted(f.slot.unique())[:horizon_slots] if len(f) else []
    stops = []
    for s in g.itertuples(index=False):
        nxt = upcoming(route_id, direction, s.stop_id, now, n=1)
        when = nxt[0]["eta"] if nxt else now
        cur = forecast_at(f, route_id, direction, s.stop_id, when) or {}
        fs = f[f.stop_id == s.stop_id].set_index("slot").reindex(slots) if len(f) else pd.DataFrame()
        stops.append({
            "stop_id": s.stop_id, "name": s.name, "seq": int(s.seq),
            "eta_min": nxt[0]["eta_min"] if nxt else None, "vehicle_id": nxt[0]["vehicle_id"] if nxt else None,
            "level": cur.get("level"), "load_factor": cur.get("load_factor"), "lo": cur.get("lo"), "hi": cur.get("hi"),
            "source": cur.get("source"), "stale": cur.get("stale"),
            "f": [[round(float(x), 2) if pd.notna(x) else None for x in (r.pred_lf, r.lo, r.hi)] for r in fs.itertuples()]
            if len(fs) else [],
        })
    meta = route_meta()[route_id]
    return _envelope(f, route_id=route_id, short_name=meta["short_name"], mode=meta["mode"], direction=direction,
                     now=iso(now), slots=[iso(x) for x in slots], stops=stops)


@router.get("/occupancy/stop/{stop_id}")
def occupancy_stop(stop_id: str, n: int = Query(5, ge=1, le=20), at: str | None = None, model: str = "lstm"):
    if stop_id not in stop_ids():
        raise HTTPException(404, f"unknown stop_id {stop_id!r}")
    now = _now(at)
    fc = latest_forecast(model)
    rs = route_stops_df()
    here = rs[rs.stop_id == stop_id]
    name = here.name.iloc[0] if len(here) else stop_id
    vehicles = []
    for r in here.itertuples(index=False):
        last_seq = rs[(rs.route_id == r.route_id) & (rs.direction == r.direction)].seq.max()
        if r.seq == last_seq:
            continue  # terminus for this direction: nobody boards here
        to = rs[(rs.route_id == r.route_id) & (rs.direction == r.direction) & (rs.seq == last_seq)].name.iloc[0]
        for v in upcoming(r.route_id, int(r.direction), stop_id, now, n=n):
            fct = forecast_at(fc, r.route_id, int(r.direction), stop_id, v["eta"]) or {}
            vehicles.append({"route_id": r.route_id, "route": route_meta()[r.route_id]["short_name"],
                             "mode": route_meta()[r.route_id]["mode"], "direction": int(r.direction), "to": to,
                             "eta_min": v["eta_min"], "vehicle_id": v["vehicle_id"], "trip_id": v["trip_id"],
                             "level": fct.get("level"), "load_factor": fct.get("load_factor"),
                             "lo": fct.get("lo"), "hi": fct.get("hi"), "stale": fct.get("stale")})
    vehicles.sort(key=lambda x: x["eta_min"])
    f = fc[fc.stop_id == stop_id] if len(fc) else fc
    return _envelope(f, stop_id=stop_id, name=name, now=iso(now), vehicles=vehicles[:n])


@router.get("/vehicle/{vehicle_id}")
def vehicle(vehicle_id: str, at: str | None = None, model: str = "lstm"):
    now = _now(at)
    ev = query("""SELECT * FROM event WHERE vehicle_id = :v AND ts <= :t AND ts >= :a ORDER BY ts DESC LIMIT 1""",
               {"v": vehicle_id, "t": iso(now), "a": iso(now - pd.Timedelta(hours=3))})
    if not len(ev):
        raise HTTPException(404, f"no recent reports for vehicle {vehicle_id!r}")
    e = ev.iloc[0]
    meta = route_meta()[e.route_id]
    g = cum_minutes(e.route_id, int(e.direction))
    seq_now = int(g.loc[g.stop_id == e.stop_id, "seq"].iloc[0])
    cum_now = float(g.loc[g.stop_id == e.stop_id, "cum"].iloc[0])
    ts = pd.Timestamp(e.ts).tz_convert(IST)
    fc = latest_forecast(model)
    nxt = []
    for s in g[g.seq > seq_now].head(8).itertuples(index=False):
        eta = ts + pd.Timedelta(minutes=float(s.cum) - cum_now)
        fct = forecast_at(fc, e.route_id, int(e.direction), s.stop_id, eta) or {}
        nxt.append({"stop_id": s.stop_id, "name": s.name, "eta_min": max(0, round((eta - now).total_seconds() / 60)),
                    "level": fct.get("level"), "load_factor": fct.get("load_factor")})
    load = int(e.onboard_load) if pd.notna(e.onboard_load) else None
    lf = load / meta["capacity"] if load is not None else None
    ds = "twin" if e.source == "twin" else "camera"
    return {"vehicle_id": vehicle_id, "route_id": e.route_id, "route": meta["short_name"], "direction": int(e.direction),
            "last_stop": g.loc[g.stop_id == e.stop_id, "name"].iloc[0], "last_report": iso(ts), "load": load,
            "capacity": meta["capacity"], "load_factor": round(lf, 3) if lf is not None else None, "level": crowd_level(lf),
            "next_stops": nxt, "data_source": ds, "simulated": ds == "twin"}


@router.get("/vehicles")
def vehicles_active(route_id: str | None = None, at: str | None = None):
    """Vehicles that reported in the last 10 minutes (helper for the vehicle view)."""
    now = _now(at)
    q = """SELECT vehicle_id, route_id, direction, stop_id, MAX(ts) ts, onboard_load, source FROM event
           WHERE ts >= :a AND ts <= :b AND vehicle_id IS NOT NULL {r} GROUP BY vehicle_id ORDER BY route_id, vehicle_id"""
    ev = query(q.format(r="AND route_id = :rid" if route_id else ""),
               {"a": iso(now - pd.Timedelta(minutes=10)), "b": iso(now), "rid": route_id})
    return [{"vehicle_id": x.vehicle_id, "route_id": x.route_id, "direction": int(x.direction),
             "stop_id": x.stop_id, "load": int(x.onboard_load) if pd.notna(x.onboard_load) else None,
             "source": x.source} for x in ev.itertuples(index=False)]


@router.get("/forecast")
def forecast(stop_id: str | None = None, route_id: str | None = None, direction: int | None = None,
             from_: str | None = Query(None, alias="from"), to: str | None = None, model: str = "lstm",
             latest: bool = True, limit: int = Query(2000, le=20000)):
    cond, params = ["model = :m"], {"m": model, "lim": limit}
    if latest:
        cond.append("made_at = (SELECT MAX(made_at) FROM forecast WHERE model = :m)")
    for k, v in (("stop_id", stop_id), ("route_id", route_id), ("direction", direction)):
        if v is not None:
            cond.append(f"{k} = :{k}")
            params[k] = v
    if from_:
        cond.append("target_slot >= :f")
        params["f"] = iso(_now(from_))
    if to:
        cond.append("target_slot <= :t")
        params["t"] = iso(_now(to))
    rows = query(f"SELECT made_at, target_slot, stop_id, route_id, direction, model, pred_lf, pred_load, pred_boardings, "
                 f"level, lo, hi, stale, data_source, horizon FROM forecast WHERE {' AND '.join(cond)} "
                 f"ORDER BY route_id, direction, stop_id, target_slot LIMIT :lim", params)
    num = ["pred_lf", "pred_load", "pred_boardings", "lo", "hi"]
    rows[num] = rows[num].round(3)
    rows = rows.astype(object).where(rows.notna(), None)
    return {"data_source": flag(rows), "simulated": flag(rows) in ("twin", "mixed"), "rows": rows.to_dict("records")}


@router.get("/history")
def history(stop_id: str, route_id: str, direction: int | None = None,
            day_type: str = Query("weekday", pattern="^(weekday|weekend|holiday)$"), weeks: int = Query(8, le=20)):
    _check_route(route_id)
    now = _now(None)
    cond = "AND e.direction = :d" if direction is not None else ""
    ev = query(f"""SELECT e.slot_15, MAX(e.onboard_load + COALESCE(e.left_behind,0)) * 1.0 / r.capacity_total AS lf,
                          SUM(e.boardings) AS boardings, MAX(e.source) AS source
                   FROM event e JOIN route r ON r.route_id = e.route_id
                   WHERE e.stop_id = :s AND e.route_id = :r {cond} AND e.slot_15 >= :a
                   GROUP BY e.slot_15""",
               {"s": stop_id, "r": route_id, "d": direction, "a": iso(now - pd.Timedelta(weeks=weeks))})
    if not len(ev):
        return {"stop_id": stop_id, "route_id": route_id, "day_type": day_type, "lf": [None] * 96,
                "boardings": [None] * 96, "days": 0, "data_source": "none", "simulated": False}
    ev["t"] = pd.to_datetime(ev.slot_15, utc=True).dt.tz_convert(IST)
    cal = query("SELECT date, day_type FROM calendar_day")
    dt = dict(zip(cal.date, cal.day_type))
    ev["day_type"] = ev.t.dt.strftime("%Y-%m-%d").map(dt).fillna(ev.t.dt.dayofweek.map(lambda d: "weekend" if d >= 5 else "weekday"))
    ev = ev[ev.day_type == day_type]
    ev["k"] = ev.t.dt.hour * 4 + ev.t.dt.minute // 15
    prof = ev.groupby("k").agg(lf=("lf", "mean"), b=("boardings", "mean")).reindex(range(96))
    srcs = set(ev.source)
    ds = "mixed" if "twin" in srcs and srcs - {"twin"} else ("twin" if "twin" in srcs else "camera")
    return {"stop_id": stop_id, "route_id": route_id, "day_type": day_type, "days": int(ev.t.dt.date.nunique()),
            "lf": [None if pd.isna(x) else round(float(x), 3) for x in prof.lf],
            "boardings": [None if pd.isna(x) else round(float(x), 1) for x in prof.b],
            "data_source": ds, "simulated": ds in ("twin", "mixed")}


@router.get("/wait-or-go")
def wait_or_go(stop_id: str, route_id: str, direction: int | None = None, at: str | None = None, model: str = "lstm"):
    _check_route(route_id)
    now = _now(at)
    rs = route_stops_df()
    dirs = [direction] if direction is not None else sorted(rs[(rs.route_id == route_id) & (rs.stop_id == stop_id)].direction.unique())
    if not dirs:
        raise HTTPException(404, f"route {route_id} does not serve stop {stop_id}")
    d = int(dirs[0])
    fc = latest_forecast(model)
    vs = []
    for v in upcoming(route_id, d, stop_id, now, n=3):
        f = forecast_at(fc, route_id, d, stop_id, v["eta"]) or {}
        vs.append({"eta_min": v["eta_min"], "vehicle_id": v["vehicle_id"], "level": f.get("level"),
                   "load_factor": f.get("load_factor")})
    meta = route_meta()[route_id]
    noun = {"bus": "bus", "metro": "train", "mrts": "train"}[meta["mode"]]
    rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CROWDED": 3, None: 1}
    if not vs:
        msg = f"No more {meta['short_name']} departures expected today from this stop."
    else:
        first = vs[0]
        better = [v for v in vs[1:] if rank[v["level"]] < rank[first["level"]] and v["eta_min"] - first["eta_min"] <= 15]
        if rank[first["level"]] >= 2 and better:
            b = better[0]
            msg = (f"Next {noun} in {first['eta_min']} min is {first['level']}; the one after in {b['eta_min']} min is "
                   f"{b['level']}. Worth waiting {b['eta_min'] - first['eta_min']} min.")
        elif rank[first["level"]] >= 2:
            msg = f"Next {noun} in {first['eta_min']} min is {first['level']}, and the following ones are no better. Take it."
        else:
            msg = f"Next {noun} in {first['eta_min']} min is {first['level'] or 'unknown'}. Go."
    f = fc[(fc.route_id == route_id) & (fc.stop_id == stop_id)] if len(fc) else fc
    return _envelope(f, stop_id=stop_id, route_id=route_id, direction=d, suggestion=msg, vehicles=vs)
