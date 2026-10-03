"""Build the corridor network (stops, routes, route_stop, timetable) from GTFS + config/corridor.yaml.

The Chennai unified GTFS feed is a community merge with ragged rows (CMRL rows have a different
column order), so files are read with a tolerant CSV reader. Routes marked `source: manual` in
the config (MRTS, metro segments) are built from the config, with metro coordinates taken from
the feed's stops.txt.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from common.config import RAW_DIR, corridor, demand_config, haversine_m, hhmm_to_min

BUS_SPEED_KMH = 18.0          # fallback when GTFS run times are missing/zero (ASSUMPTION)
ROAD_DETOUR = 1.25            # straight-line -> road distance factor (ASSUMPTION)
STATION_RADIUS_M = 150        # stops closer than this are the same physical place


def _read_csv(path: Path) -> pd.DataFrame:
    with open(path, encoding="utf8", newline="") as f:
        rows = list(csv.reader(f))
    h = [c.strip() for c in rows[0]]
    n = len(h)
    data = [(r[:n] + [""] * (n - len(r))) for r in rows[1:] if r]
    return pd.DataFrame(data, columns=h)


def _gtfs_dir() -> Path:
    return RAW_DIR / "gtfs"


def _time_to_min(s: str) -> float:
    try:
        h, m, sec = s.split(":")
        return int(h) * 60 + int(m) + int(sec) / 60
    except Exception:
        return np.nan


@dataclass
class Network:
    stops: pd.DataFrame            # stop_id, name, lat, lon, mode, stop_type, demand_weight, station_id
    routes: pd.DataFrame           # route_id, short_name, long_name, mode, operator, capacity_*, depot, vehicle_type
    route_stop: pd.DataFrame       # route_id, direction, seq, stop_id, dist_from_prev_m, run_min
    timetable: pd.DataFrame        # route_id, direction, start_min (minutes after midnight), origin
    stations: pd.DataFrame         # station_id, name, lat, lon, modes, stop_type, weight
    transfers: pd.DataFrame        # from_station, to_station, walk_m, walk_min
    notes: list = field(default_factory=list)

    def route_stops(self, route_id: str, direction: int) -> pd.DataFrame:
        rs = self.route_stop
        return rs[(rs.route_id == route_id) & (rs.direction == direction)].sort_values("seq")


# ---------------------------------------------------------------------------------------------
# Stop typing and demand weights
# ---------------------------------------------------------------------------------------------
_TYPE_PATTERNS = [
    ("interchange", r"bus stand|b\.?\s?t\b|b\.s\b|terminus|railway|metro|station|depot|airport|junction|jn\b"),
    ("college", r"college|univ|iit\b|institute|polytechnic|school|engg|engineering|kotturpuram"),
    ("hospital", r"hospital|medical|clinic|health|\bgh\b"),
    ("office", r"tidel|\bit\b|tech|estate|sidco|industrial|olympia|dlf|perungudi|taramani|guindy|ascendas|park\b|race course|secretariat|fort|high court"),
    ("market", r"market|bazaar|mall|phoenix|shopping|bazar|beach|t\.?nagar|marina|light house|lighthouse|chepauk|thiruvallikeni|mylai|thirumylai"),
]
# Manual weights by stop type (fallback for OSM POI counts, section 3 row 12)
MANUAL_WEIGHT = {"interchange": 4.0, "office": 3.0, "college": 3.0, "market": 2.5, "hospital": 2.0, "residential": 1.5}


def classify_stop(name: str) -> str:
    n = name.lower()
    for t, pat in _TYPE_PATTERNS:
        if re.search(pat, n):
            return t
    return "residential"


def _poi_weights(stops: pd.DataFrame) -> pd.Series | None:
    """POI-count weights within 500 m from OSM, if fetch_data managed to download them."""
    path = RAW_DIR / "osm_poi.json"
    if not path.exists():
        return None
    cfgw = demand_config()["poi_weights"]
    els = json.loads(path.read_text(encoding="utf8")).get("elements", [])
    pts = []
    for e in els:
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        if lat is None:
            continue
        t = e.get("tags", {})
        kind = ("office" if "office" in t else t.get("amenity") or ("mall" if t.get("shop") == "mall" else None)
                or ("railway_station" if t.get("railway") == "station" else None))
        if kind in cfgw:
            pts.append((lat, lon, cfgw[kind]))
    if not pts:
        return None
    p = np.array(pts)
    w = []
    for _, s in stops.iterrows():
        d = haversine_m(s.lat, s.lon, p[:, 0], p[:, 1])
        w.append(p[d <= 500, 2].sum())
    return pd.Series(w, index=stops.index)


# ---------------------------------------------------------------------------------------------
# GTFS route extraction
# ---------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _gtfs():
    g = _gtfs_dir()
    if not (g / "stops.txt").exists():
        raise FileNotFoundError(f"GTFS not found in {g}. Run: python data/fetch_data.py")
    stops = _read_csv(g / "stops.txt")
    trips = _read_csv(g / "trips.txt")
    trips = trips[~trips.trip_id.str.startswith("CMRL")]  # CMRL rows are column-shifted; metro is manual
    return stops.set_index("stop_id"), trips


def _gtfs_pattern(gtfs_route_id: str, stop_times: pd.DataFrame):
    """Most common stop pattern for a GTFS route, median run times, and trip start times."""
    _, trips = _gtfs()
    tids = set(trips.loc[trips.route_id == gtfs_route_id, "trip_id"])
    st = stop_times[stop_times.trip_id.isin(tids)].copy()
    if st.empty:
        raise ValueError(f"GTFS route {gtfs_route_id} has no stop_times")
    st["q"] = st.stop_sequence.astype(int)
    st["t"] = st.arrival_time.map(_time_to_min)
    st = st.sort_values(["trip_id", "q"])
    pat = st.groupby("trip_id").stop_id.apply(tuple)
    best = pat.value_counts().index[0]
    same = pat[pat == best].index
    s2 = st[st.trip_id.isin(same)].copy()
    s2["dt"] = s2.groupby("trip_id").t.diff()
    run = s2.groupby("q").dt.median().values  # first is NaN
    starts = st.groupby("trip_id").t.min().dropna().sort_values().values
    return list(best), run, starts


def _profile_starts(profile, service_start: int, service_end: int) -> list[float]:
    starts = []
    for a, b, h in profile:
        t, end = hhmm_to_min(a), hhmm_to_min(b)
        while t < end:
            if service_start <= t <= service_end:
                starts.append(float(t))
            t += h
    return sorted(set(starts))


def build_network() -> Network:
    cfg = corridor()
    gstops, _ = _gtfs()
    svc_start, svc_end = hhmm_to_min(cfg["service_day"]["start"]), hhmm_to_min(cfg["service_day"]["end"])
    notes = []

    gtfs_ids = {str(v) for r in cfg["routes"] if r["source"] == "gtfs" for v in r["gtfs_route_ids"].values() if v}
    _, trips = _gtfs()
    tids = set(trips.loc[trips.route_id.isin(gtfs_ids), "trip_id"])
    stop_times = pd.read_csv(_gtfs_dir() / "stop_times.txt", dtype=str, usecols=[0, 1, 3, 4])
    stop_times = stop_times[stop_times.trip_id.isin(tids)]

    stop_rows: dict[str, dict] = {}
    rs_rows, tt_rows, route_rows = [], [], []
    for r in cfg["routes"]:
        vt = cfg["vehicle_types"][r["vehicle_type"]]
        route_rows.append({
            "route_id": r["route_id"], "short_name": r["short_name"], "long_name": r["long_name"],
            "mode": r["mode"], "operator": r["operator"], "vehicle_type": r["vehicle_type"],
            "capacity_seated": vt["capacity_seated"], "capacity_total": vt["capacity_total"],
            "depot": r.get("depot"),
        })
        speed = r.get("run_speed_kmh", BUS_SPEED_KMH)
        per_dir: dict[int, tuple[list, np.ndarray, np.ndarray | None]] = {}

        if r["source"] == "gtfs":
            for d in (0, 1):
                gid = r["gtfs_route_ids"].get(d)
                if gid:
                    per_dir[d] = _gtfs_pattern(str(gid), stop_times)
            for d in (0, 1):
                if d not in per_dir:  # reverse the other direction
                    s, run, _ = per_dir[1 - d]
                    rr = np.concatenate([[np.nan], run[1:][::-1]])
                    per_dir[d] = (s[::-1], rr, None)
                    notes.append(f"{r['route_id']} dir {d}: not in GTFS; reversed dir {1-d} pattern")
            for sid in {s for v in per_dir.values() for s in v[0]}:
                g = gstops.loc[sid]
                stop_rows.setdefault(sid, {"stop_id": sid, "name": g.stop_name.strip(), "lat": float(g.stop_lat),
                                           "lon": float(g.stop_lon), "mode": "bus"})
        else:
            if "stops" in r:
                lst = r["stops"]
            else:
                lst = [{"stop_id": s, "name": gstops.loc[s].stop_name, "lat": float(gstops.loc[s].stop_lat),
                        "lon": float(gstops.loc[s].stop_lon)} for s in r["gtfs_stop_ids"]]
            for s in lst:
                stop_rows.setdefault(s["stop_id"], {**s, "mode": r["mode"]})
            ids = [s["stop_id"] for s in lst]
            per_dir[0] = (ids, None, None)
            per_dir[1] = (ids[::-1], None, None)

        for d, (sids, run, starts) in per_dir.items():
            prev = None
            for i, sid in enumerate(sids):
                s = stop_rows[sid]
                dist = 0.0 if prev is None else float(haversine_m(prev["lat"], prev["lon"], s["lat"], s["lon"])) * (
                    ROAD_DETOUR if r["mode"] == "bus" else 1.1)
                rm = 0.0
                if i > 0:
                    rm = float(run[i]) if run is not None and i < len(run) and np.isfinite(run[i]) and run[i] > 0 else (
                        dist / 1000 / speed * 60)
                    rm = max(rm, 0.5)
                rs_rows.append({"route_id": r["route_id"], "direction": d, "seq": i + 1, "stop_id": sid,
                                "dist_from_prev_m": round(dist, 1), "run_min": round(rm, 2)})
                prev = s
            use_gtfs = starts is not None and len([t for t in starts if svc_start <= t <= svc_end]) >= r.get("gtfs_min_trips", 20)
            if use_gtfs:
                st_list = sorted({float(round(t)) for t in starts if svc_start <= t <= svc_end})
                origin = "gtfs"
            else:
                st_list = _profile_starts(r["headway_profile"], svc_start, svc_end)
                origin = "headway_profile"
                if r["source"] == "gtfs":
                    notes.append(f"{r['route_id']} dir {d}: GTFS trips below gtfs_min_trips; timetable from headway_profile")
            tt_rows += [{"route_id": r["route_id"], "direction": d, "start_min": t, "origin": origin} for t in st_list]

    stops = pd.DataFrame(stop_rows.values())
    for sid, o in (cfg.get("stop_overrides") or {}).items():
        for k, v in o.items():
            stops.loc[stops.stop_id == sid, k] = v
    route_stop = pd.DataFrame(rs_rows)
    timetable = pd.DataFrame(tt_rows)
    routes = pd.DataFrame(route_rows)

    # Stations: union stops within STATION_RADIUS_M
    n = len(stops)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    lat, lon = stops.lat.values, stops.lon.values
    for i in range(n):
        d = haversine_m(lat[i], lon[i], lat, lon)
        for j in np.where(d < STATION_RADIUS_M)[0]:
            if j > i:
                parent[find(j)] = find(i)
    roots = [find(i) for i in range(n)]
    stops["station_id"] = [f"ST_{stops.stop_id.iloc[r]}" for r in roots]

    # Stop types and demand weights
    modes_at = stops.groupby("station_id").mode.agg(lambda m: sorted(set(m)))
    routes_at = route_stop.merge(stops[["stop_id", "station_id"]]).groupby("station_id").route_id.nunique()
    types = []
    for _, s in stops.iterrows():
        t = classify_stop(s["name"])
        if len(modes_at[s.station_id]) > 1 or routes_at.get(s.station_id, 1) >= 3:
            t = "interchange"
        types.append(t)
    stops["stop_type"] = types
    for sid, t in (cfg.get("stop_type_overrides") or {}).items():
        stops.loc[stops.stop_id == sid, "stop_type"] = t
    dcfg = demand_config()
    poi = _poi_weights(stops)
    if poi is not None:
        stops["demand_weight"] = np.maximum(poi.values, dcfg["demand_weight_floor"])
    else:
        stops["demand_weight"] = stops.stop_type.map(MANUAL_WEIGHT)
        # Rail stations draw from a wider catchment than a single bus stop (ASSUMPTION)
        stops.loc[stops["mode"] != "bus", "demand_weight"] *= 2.0
        notes.append("OSM POIs unavailable: demand_weight from manual weights by stop type (x2 for rail)")
    for r in cfg["routes"]:
        for b in r.get("boundary_stops", []):
            stops.loc[stops.stop_id == b, "demand_weight"] *= dcfg.get("boundary_weight", 1.0)
            stops.loc[stops.stop_id == b, "stop_type"] = "interchange"

    g = stops.groupby("station_id")
    stations = pd.DataFrame({
        "name": g.apply(lambda x: x.loc[x["mode"] != "bus", "name"].iloc[0] if (x["mode"] != "bus").any() else x["name"].iloc[0]), "lat": g.lat.mean(), "lon": g.lon.mean(),
        "modes": modes_at.map(lambda m: ",".join(m)), "weight": g.demand_weight.sum(),
        "stop_type": g.stop_type.agg(lambda t: "interchange" if "interchange" in set(t) else t.mode().iloc[0]),
    }).reset_index()

    # Walking transfers between stations
    radius = cfg["transfer_radius_m"]
    walk = cfg["walk_speed_kmh"] * 1000 / 60
    tr = []
    sl, so = stations.lat.values, stations.lon.values
    for i in range(len(stations)):
        d = haversine_m(sl[i], so[i], sl, so)
        for j in np.where((d <= radius) & (d > 0))[0]:
            tr.append({"from_station": stations.station_id.iloc[i], "to_station": stations.station_id.iloc[j],
                       "walk_m": round(float(d[j]), 1), "walk_min": round(float(d[j]) / walk, 2)})
    transfers = pd.DataFrame(tr, columns=["from_station", "to_station", "walk_m", "walk_min"])
    return Network(stops, routes, route_stop, timetable, stations, transfers, notes)


@lru_cache(maxsize=1)
def load_network() -> Network:
    """Cached network; rebuilt from GTFS on first use in a process."""
    from common.config import PROCESSED_DIR

    cache = PROCESSED_DIR / "network.pkl"
    cfg_mtime = max(p.stat().st_mtime for p in (Path(__file__).parents[1] / "config").glob("*.yaml"))
    if cache.exists() and cache.stat().st_mtime > max(cfg_mtime, Path(__file__).stat().st_mtime):
        return pd.read_pickle(cache)
    net = build_network()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pd.to_pickle(net, cache)
    return net


if __name__ == "__main__":
    net = build_network()
    print(net.routes.to_string())
    for (rid, d), g in net.route_stop.groupby(["route_id", "direction"]):
        tt = net.timetable[(net.timetable.route_id == rid) & (net.timetable.direction == d)]
        print(f"{rid} d{d}: {len(g)} stops, {g.run_min.sum():.0f} min, {len(tt)} trips ({tt.origin.iloc[0]}) "
              f"{net.stops.set_index('stop_id').loc[g.stop_id.iloc[0], 'name']} -> {net.stops.set_index('stop_id').loc[g.stop_id.iloc[-1], 'name']}")
    print(net.stops.stop_type.value_counts().to_string())
    print(f"stations {len(net.stations)}, transfers {len(net.transfers)}")
    multi = net.stations[net.stations.modes.str.contains(",")]
    print("multimodal stations:", multi[["name", "modes"]].to_string())
    print("\n".join(net.notes))
