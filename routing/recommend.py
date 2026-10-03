"""Crowd-aware multimodal trip planning (section 8.1).

1. Earliest-arrival Dijkstra from the origin (time-dependent waits from today's timetable) gives
   an estimated pass time at every node; crowd penalties use the forecast at that time.
2. For each option (fastest w=0, balanced w=1, least crowded w=3; prefer_low_crowd -> w=5) the top
   3 simple paths under cost = time + w * crowd are enumerated (Yen's algorithm via NetworkX).
3. Every candidate path is re-timed exactly against the timetable, then each option picks its best
   candidate under its own cost. Because 'least crowded' minimises time + 3*crowd over the same
   candidates in which 'fastest' minimises time, its total crowd score can never be worse.
"""
from __future__ import annotations

import heapq
import itertools
from collections import defaultdict

import networkx as nx
import numpy as np
import pandas as pd

from common import clock
from common.config import IST, iso
from routing.graph import CROWD_F, build, level_of, lf_at

OPTIONS = {"fastest": 0.0, "balanced": 1.0, "least_crowded": 3.0}
PREFER_LOW_W = 5.0
MISS_PROB = 0.5             # chance of being left behind by a CROWDED vehicle
LOW_CROWD_WAIT_MAX = 15.0   # prefer_low_crowd: skip a CROWDED vehicle if a better one comes within 15 min
K_PATHS = 3


class Planner:
    def __init__(self, now: pd.Timestamp):
        self.now = now
        self.G, self.st, dep, self.fc = build(now)
        self.starts = {k: np.sort(g.start.values) for k, g in dep.groupby(["route_id", "direction"])}
        self.trip_ids = {k: g.sort_values("start")[["trip_id", "vehicle_id"]].values for k, g in dep.groupby(["route_id", "direction"])}
        self.cum = {(n[1], n[2], n[3]): d["cum"] for n, d in self.G.nodes(data=True) if n[0] == "B"}
        self.stop_of = {(n[1], n[2], n[3]): d["stop_id"] for n, d in self.G.nodes(data=True) if n[0] == "B"}
        rs = self.st.rs
        self.meta = {r.route_id: r for r in self.st.routes.itertuples(index=False)}
        self.names = dict(zip(rs.stop_id, rs.name))
        self.station_of_stop = dict(zip(rs.stop_id, rs.station_id))
        self.station_name = dict(zip(self.st.stations.station_id, self.st.stations.name))

    # ---------------------------------------------------------------- timetable helpers
    def next_vehicles(self, r, d, seq, t, n=3):
        """Pass times (minutes from now) of the next n vehicles at (r, d, seq) at or after t."""
        s = self.starts.get((r, d))
        if s is None:
            return []
        c = self.cum[(r, d, seq)]
        i = int(np.searchsorted(s, t - c))
        return [(float(s[j] + c), j) for j in range(i, min(i + n, len(s)))]

    def level_at(self, r, d, seq, t):
        return level_of(lf_at(self.fc, (r, d, self.stop_of[(r, d, seq)]), t))

    def board_choice(self, r, d, seq, t, prefer_low):
        nv = self.next_vehicles(r, d, seq, t, n=4)
        if not nv:
            return None
        if prefer_low and self.level_at(r, d, seq, nv[0][0]) == "CROWDED":
            for pt, j in nv[1:]:
                if pt - nv[0][0] <= LOW_CROWD_WAIT_MAX and self.level_at(r, d, seq, pt) != "CROWDED":
                    return pt, j
        return nv[0]

    # ---------------------------------------------------------------- 1) earliest arrival
    def earliest(self, origin):
        best = {origin: 0.0}
        pq = [(0.0, 0, origin)]
        cnt = itertools.count(1)
        while pq:
            t, _, u = heapq.heappop(pq)
            if t > best.get(u, np.inf):
                continue
            for v, e in self.G[u].items():
                if e["kind"] == "board":
                    nv = self.next_vehicles(v[1], v[2], v[3], t, n=1)
                    if not nv:
                        continue
                    tv = nv[0][0]
                elif e["kind"] == "ride":
                    tv = t + e["time"]
                else:
                    tv = t + e["time"]
                if tv < best.get(v, np.inf):
                    best[v] = tv
                    heapq.heappush(pq, (tv, next(cnt), v))
        return best

    # ---------------------------------------------------------------- 2) candidate paths
    def weights(self, eta, w_crowd):
        for u, v, e in self.G.edges(data=True):
            t_u = eta.get(u)
            if t_u is None:
                e["w"] = 1e6
                continue
            if e["kind"] == "board":
                nv = self.next_vehicles(v[1], v[2], v[3], t_u, n=2)
                if not nv:
                    e["w"] = 1e6
                    continue
                wait = nv[0][0] - t_u
                if self.level_at(v[1], v[2], v[3], nv[0][0]) == "CROWDED" and len(nv) > 1:
                    wait += MISS_PROB * (nv[1][0] - nv[0][0])   # missed-vehicle penalty
                e["w"] = wait + 0.5  # small boarding cost discourages pointless re-boarding
            elif e["kind"] == "ride":
                lvl = self.level_at(u[1], u[2], u[3], t_u)
                e["w"] = e["time"] + w_crowd * CROWD_F[lvl]
            else:
                e["w"] = e["time"]

    def candidates(self, origin, dest, eta, prefer_low):
        cands = []
        ws = list(OPTIONS.values()) + ([PREFER_LOW_W] if prefer_low else [])
        for w in ws:
            self.weights(eta, w)
            try:
                gen = nx.shortest_simple_paths(self.G, origin, dest, weight="w")
                for path in itertools.islice(gen, K_PATHS):
                    cands.append(path)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                break
        return cands

    # ---------------------------------------------------------------- 3) exact re-timing
    def retime(self, path, prefer_low):
        t = 0.0
        legs, cur = [], None
        walk_min = 0.0
        for u, v in zip(path, path[1:]):
            e = self.G[u][v]
            if e["kind"] == "walk":
                walk_min += e["walk"]
                t += e["walk"]  # the transfer penalty is a cost, not time
                legs.append({"kind": "walk", "from": self.station_name[u[1]], "to": self.station_name[v[1]],
                             "minutes": round(e["walk"], 1)})
            elif e["kind"] == "board":
                ch = self.board_choice(v[1], v[2], v[3], t, prefer_low)
                if ch is None:
                    return None
                pt, j = ch
                trip_id, vid = self.trip_ids[(v[1], v[2])][j]
                start = self.starts[(v[1], v[2])][j]
                cur = {"kind": "ride", "route_id": v[1], "direction": int(v[2]), "trip_id": trip_id, "vehicle_id": vid,
                       "start": start, "from_seq": v[3], "wait_min": round(pt - t, 1), "board_t": pt, "segments": []}
                t = pt
            elif e["kind"] == "ride":
                lvl = self.level_at(u[1], u[2], u[3], t)
                t = cur["start"] + self.cum[(v[1], v[2], v[3])]
                cur["segments"].append(lvl)
                cur["to_seq"] = v[3]
            elif e["kind"] == "alight":
                if cur and cur["segments"]:
                    legs.append(cur)
                cur = None
        rides = [l for l in legs if l["kind"] == "ride"]
        if not rides or any(a["route_id"] == b["route_id"] for a, b in zip(rides, rides[1:])):
            return None
        out_legs = []
        for l in legs:
            if l["kind"] == "walk":
                out_legs.append(l)
                continue
            m = self.meta[l["route_id"]]
            r, d = l["route_id"], l["direction"]
            worst = max(l["segments"], key=lambda x: CROWD_F[x])
            fs, ts_ = self.stop_of[(r, d, l["from_seq"])], self.stop_of[(r, d, l["to_seq"])]
            out_legs.append({
                "kind": "ride", "mode": m.mode, "route_id": r, "route": m.short_name, "direction": d,
                "from_stop": fs, "from": self.names[fs], "to_stop": ts_, "to": self.names[ts_],
                "board_at": iso(self.now + pd.Timedelta(minutes=l["board_t"])),
                "alight_at": iso(self.now + pd.Timedelta(minutes=l["start"] + self.cum[(r, d, l["to_seq"])])),
                "wait_min": l["wait_min"], "minutes": round(l["start"] + self.cum[(r, d, l["to_seq"])] - l["board_t"], 1),
                "stops": l["to_seq"] - l["from_seq"], "vehicle_id": l["vehicle_id"], "trip_id": l["trip_id"],
                "level": worst, "levels": l["segments"],
            })
        segs = [s for l in rides for s in l["segments"]]
        crowd_total = float(sum(CROWD_F[s] for s in segs))
        return {
            "legs": out_legs, "total_min": round(t, 1), "transfers": len(rides) - 1,
            "worst_level": max(segs, key=lambda x: CROWD_F[x]), "crowd_score": round(crowd_total / max(len(segs), 1), 2),
            "crowd_total": round(crowd_total, 1), "walk_min": round(walk_min, 1),
            "arrive_at": iso(self.now + pd.Timedelta(minutes=t)),
            "signature": tuple((l["route_id"], l["from_seq"], l.get("to_seq")) for l in rides),
        }


def plan(from_stop: str, to_stop: str, depart_at=None, prefer_low_crowd: bool = False) -> dict:
    now = pd.Timestamp(depart_at or clock.now())
    now = (now.tz_localize(IST) if now.tzinfo is None else now).tz_convert(IST)
    P = Planner(now)
    if from_stop not in P.station_of_stop or to_stop not in P.station_of_stop:
        raise ValueError("unknown stop id")
    o, dst = ("S", P.station_of_stop[from_stop]), ("S", P.station_of_stop[to_stop])
    if o == dst:
        raise ValueError("origin and destination are the same place")
    eta = P.earliest(o)
    if dst not in eta:
        return {"itineraries": [], "message": "No connection on the modelled corridor at this time."}
    seen, its = set(), []
    for path in P.candidates(o, dst, eta, prefer_low_crowd):
        it = P.retime(path, prefer_low_crowd)
        if it and it["signature"] not in seen:
            seen.add(it["signature"])
            its.append(it)
    if not its:
        return {"itineraries": [], "message": "No connection found."}
    opts = dict(OPTIONS)
    if prefer_low_crowd:
        opts["least_crowded"] = PREFER_LOW_W
    labels = defaultdict(list)
    for name, w in opts.items():
        best = min(range(len(its)), key=lambda i: (its[i]["total_min"] + w * its[i]["crowd_total"], its[i]["total_min"]))
        labels[best].append(name)
    order = sorted(labels, key=lambda i: min(list(opts).index(n) for n in labels[i]))
    # unlabelled alternatives only if they use a different sequence of routes (not just another transfer stop)
    routes_of = lambda i: tuple(l["route_id"] for l in its[i]["legs"] if l["kind"] == "ride")  # noqa: E731
    shown = {routes_of(i) for i in order}
    rest = []
    for i in sorted((i for i in range(len(its)) if i not in labels), key=lambda i: its[i]["total_min"]):
        if routes_of(i) not in shown:
            shown.add(routes_of(i))
            rest.append(i)
    chosen = (order + rest)[:4]
    out = []
    for i in chosen:
        it = {k: v for k, v in its[i].items() if k != "signature"}
        it["labels"] = labels.get(i, ["alternative"])
        out.append(it)
    srcs = P.fc.get("_sources", set())
    ds = "mixed" if "mixed" in srcs or {"twin", "camera"} <= srcs else ("camera" if "camera" in srcs else ("twin" if "twin" in srcs else "none"))
    return {"from_stop": from_stop, "to_stop": to_stop, "from": P.names[from_stop], "to": P.names[to_stop],
            "depart_at": iso(now), "prefer_low_crowd": prefer_low_crowd, "itineraries": out,
            "data_source": ds, "simulated": ds in ("twin", "mixed")}
