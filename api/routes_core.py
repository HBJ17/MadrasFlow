"""/health, /routes, /stops."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Query

from api.deps import data_source_of, route_stops_df, routes_df
from common import clock
from common.config import iso
from db.database import query

router = APIRouter()


@router.get("/health")
def health():
    src = query("SELECT source, COUNT(*) n, MAX(ts) last_ts FROM event GROUP BY source")
    fc = query("SELECT MAX(made_at) m, COUNT(*) n FROM forecast")
    nodes = query("SELECT node_id, last_seen, fps, kind FROM node_heartbeat ORDER BY last_seen DESC")
    sources = dict(zip(src.source, src.n.astype(int)))
    now = clock.now()
    cam = query("SELECT ts, source, stop_id, vehicle_id, boardings, alightings, onboard_load, waiting_count FROM event "
                "WHERE source IN ('camera_stop','camera_vehicle') AND ts >= :a ORDER BY event_id DESC LIMIT 10",
                {"a": iso(now - timedelta(minutes=10))})
    return {
        "camera_recent": cam.astype(object).where(cam.notna(), None).to_dict("records"),
        "ok": True,
        "now": iso(now),
        "last_event_ts": src.last_ts.max() if len(src) else None,
        "sources": sources,
        "data_source": data_source_of(sources),
        "simulated": "twin" in sources,
        "last_forecast_at": fc.m.iloc[0],
        "forecast_rows": int(fc.n.iloc[0]),
        "camera_nodes": nodes.to_dict("records"),
    }


@router.get("/routes")
def routes(mode: str | None = None):
    r = routes_df()
    rs = route_stops_df()
    counts = rs[rs.direction == 0].groupby("route_id").size()
    ends = rs.sort_values("seq").groupby(["route_id", "direction"]).name.agg(["first", "last"])
    if mode:
        r = r[r["mode"] == mode]
    out = []
    for _, x in r.iterrows():
        out.append({"route_id": x.route_id, "short_name": x.short_name, "long_name": x.long_name, "mode": x["mode"],
                    "operator": x.operator, "depot": x.depot, "capacity_total": int(x.capacity_total),
                    "stops": int(counts.get(x.route_id, 0)),
                    "directions": [{"direction": d, "from": ends.loc[(x.route_id, d), "first"],
                                    "to": ends.loc[(x.route_id, d), "last"]} for d in (0, 1) if (x.route_id, d) in ends.index]})
    return out


@router.get("/stops")
def stops(route_id: str | None = None, q: str | None = Query(default=None, max_length=60)):
    rs = route_stops_df()
    if route_id:
        s = rs[rs.route_id == route_id]
        s = s.drop_duplicates("stop_id")
    else:
        s = query("SELECT stop_id, name, lat, lon, mode, stop_type, station_id FROM stop")
    if q:
        s = s[s.name.str.contains(q, case=False, regex=False)]
    served = rs.groupby("stop_id").route_id.agg(lambda x: sorted(set(x)))
    return [{"stop_id": x.stop_id, "name": x["name"], "lat": round(float(x.lat), 5), "lon": round(float(x.lon), 5),
             "mode": x["mode"], "stop_type": x.stop_type, "station_id": x.station_id,
             "routes": served.get(x.stop_id, [])} for _, x in s.iterrows()]
