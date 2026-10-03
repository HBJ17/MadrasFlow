"""Stop graph for crowd-aware routing (section 8.1). Reads only from the database.

Nodes: ('S', station_id) per physical location, ('B', route_id, direction, seq) per boarding point.
Edges:
  board   S -> B : expected wait to the next departure (+ missed-vehicle penalty if it is CROWDED)
  ride    B -> B': scheduled run time (+ crowd penalty, added per query)
  alight  B -> S : 0
  walk    S -> S': walk time at 4.5 km/h (<= 400 m) + transfer penalty
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import networkx as nx
import numpy as np
import pandas as pd

from common.config import IST, corridor, haversine_m, iso
from db.database import query

DWELL_EST = {"bus": 0.5, "mrts": 0.6, "metro": 0.5}
CROWD_F = {"LOW": 0.0, "MEDIUM": 1.0, "HIGH": 3.0, "CROWDED": 8.0}   # minutes-equivalent
_STATIC: dict = {}


@dataclass
class Static:
    rs: pd.DataFrame          # route_stop + station, mode, cum minutes
    stations: pd.DataFrame    # station_id, name, lat, lon
    walks: pd.DataFrame       # a, b, walk_min
    routes: pd.DataFrame
    loaded: float


def static() -> Static:
    s = _STATIC.get("s")
    if s and time.time() - s.loaded < 600:
        return s
    rs = query("""SELECT rs.route_id, rs.direction, rs.seq, rs.stop_id, rs.run_min, st.station_id, st.name,
                         st.lat, st.lon, r.mode, r.short_name, r.capacity_total
                  FROM route_stop rs JOIN stop st ON st.stop_id = rs.stop_id JOIN route r ON r.route_id = rs.route_id
                  ORDER BY rs.route_id, rs.direction, rs.seq""")
    rs["cum"] = 0.0
    for (r, d), g in rs.groupby(["route_id", "direction"]):
        dw = DWELL_EST.get(g["mode"].iloc[0], 0.5)
        rs.loc[g.index, "cum"] = (g.run_min + np.where(np.arange(len(g)) > 0, dw, 0)).cumsum()
    stops = query("SELECT stop_id, name, lat, lon, station_id, mode FROM stop")
    stations = stops.groupby("station_id").agg(
        name=("name", lambda x: x.iloc[0]), lat=("lat", "mean"), lon=("lon", "mean")).reset_index()
    # prefer rail station names for mixed stations
    rail = stops[stops["mode"] != "bus"].groupby("station_id").name.first()
    stations["name"] = stations.station_id.map(rail).fillna(stations.name)
    cfg = corridor()
    walk_speed = cfg["walk_speed_kmh"] * 1000 / 60
    w = []
    la, lo = stations.lat.values, stations.lon.values
    for i in range(len(stations)):
        d = haversine_m(la[i], lo[i], la, lo)
        for j in np.where((d > 0) & (d <= cfg["transfer_radius_m"]))[0]:
            w.append((stations.station_id.iloc[i], stations.station_id.iloc[j], float(d[j]) / walk_speed))
    routes = query("SELECT * FROM route")
    s = Static(rs, stations, pd.DataFrame(w, columns=["a", "b", "walk_min"]), routes, time.time())
    _STATIC["s"] = s
    return s


def departures(now: pd.Timestamp) -> pd.DataFrame:
    """Today's trips with scheduled start time (minutes since `now`)."""
    day0 = now.normalize()
    t = query("SELECT trip_id, route_id, direction, scheduled_start, vehicle_id FROM trip "
              "WHERE scheduled_start >= :a AND scheduled_start < :b",
              {"a": iso(day0 - pd.Timedelta(hours=3)), "b": iso(day0 + pd.Timedelta(days=1, hours=3))})
    t["start"] = (pd.to_datetime(t.scheduled_start, utc=True).dt.tz_convert(IST) - now).dt.total_seconds() / 60
    return t


def forecast_lf(now: pd.Timestamp) -> dict:
    """(route, dir, stop) -> (slot_start_minutes_from_now array, lf array) from the latest LSTM forecast."""
    m = query("SELECT MAX(made_at) m FROM forecast WHERE model='lstm'").m.iloc[0]
    model = "lstm"
    if m is None:
        m = query("SELECT MAX(made_at) m FROM forecast WHERE model='baseline'").m.iloc[0]
        model = "baseline"
    if m is None:
        return {}
    f = query("SELECT route_id, direction, stop_id, target_slot, pred_lf, data_source FROM forecast "
              "WHERE made_at = :m AND model = :mdl", {"m": m, "mdl": model})
    f["t"] = (pd.to_datetime(f.target_slot, utc=True).dt.tz_convert(IST) - now).dt.total_seconds() / 60
    out = {}
    for k, g in f.groupby(["route_id", "direction", "stop_id"]):
        g = g.sort_values("t")
        out[k] = (g.t.values, g.pred_lf.values)
    out["_sources"] = set(f.data_source)
    return out


def level_of(lf: float) -> str:
    return "LOW" if lf < 0.4 else "MEDIUM" if lf < 0.75 else "HIGH" if lf < 1.0 else "CROWDED"


def lf_at(fc: dict, key, t_min: float) -> float:
    v = fc.get(key)
    if v is None:
        return 0.0
    ts, lf = v
    i = int(np.searchsorted(ts, t_min, side="right") - 1)
    return float(lf[min(max(i, 0), len(lf) - 1)])


def build(now: pd.Timestamp):
    """Base graph with time-independent edges; returns (G, static, departures, forecast)."""
    st = static()
    G = nx.DiGraph()
    for s in st.stations.itertuples(index=False):
        G.add_node(("S", s.station_id))
    tp = corridor()["transfer_penalty_min"]
    for w in st.walks.itertuples(index=False):
        G.add_edge(("S", w.a), ("S", w.b), kind="walk", time=w.walk_min + tp, walk=w.walk_min, crowd=0.0)
    for (r, d), g in st.rs.groupby(["route_id", "direction"]):
        g = g.sort_values("seq")
        rows = list(g.itertuples(index=False))
        for i, x in enumerate(rows):
            b = ("B", r, d, int(x.seq))
            G.add_node(b, stop_id=x.stop_id, station=x.station_id, cum=float(x.cum))
            if i < len(rows) - 1:
                G.add_edge(("S", x.station_id), b, kind="board", time=0.0, crowd=0.0)
            if i > 0:
                p = rows[i - 1]
                G.add_edge(("B", r, d, int(p.seq)), b, kind="ride", time=float(x.cum - p.cum), crowd=0.0)
                G.add_edge(b, ("S", x.station_id), kind="alight", time=0.0, crowd=0.0)
    return G, st, departures(now), forecast_lf(now)
