"""Travel options between stations for the twin's mode/route choice.

An option is a list of legs (route, direction, board_seq, alight_seq): direct, or one transfer
(with a walk of up to transfer_radius_m between stations). Static attributes (in-vehicle time,
walk, fare, transfers) are precomputed; wait and crowding are added at choice time.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.config import corridor

DWELL_EST_MIN = {"bus": 0.5, "mrts": 0.6, "metro": 0.5}
MAX_OPTIONS = 6


@dataclass(frozen=True)
class Leg:
    route_id: str
    direction: int
    board_seq: int
    alight_seq: int
    mode: str
    km: float
    ivt: float


@dataclass
class Option:
    legs: tuple
    ivt: float
    walk: float
    fare: float              # transit fare only (what the event table records)
    transfers: int
    modes: tuple
    egress: float = 0.0      # minutes of off-network last mile (auto / share-auto / walk), not simulated
    egress_fare: float = 0.0

    @property
    def key(self):
        return tuple((l.route_id, l.direction, l.alight_seq) for l in self.legs) + (("egress",) if self.egress else ())

    @property
    def gen_time(self) -> float:
        return self.ivt + self.walk + self.egress


def fare_for(mode: str, km: float) -> float:
    f = corridor()["fares"][mode]
    if mode == "bus":
        return max(f["min_inr"], f["per_stage_inr"] * math.ceil(max(km, 0.1) / f["stage_km"]))
    return min(f["max_inr"], f["flat_inr"] + f["per_km_inr"] * km)


class PathIndex:
    """Options for every reachable (origin station, destination station) pair."""

    def __init__(self, net, min_km: float = 1.0):
        self.net = net
        cfg = corridor()
        self.transfer_penalty = cfg["transfer_penalty_min"]
        stops = net.stops.set_index("stop_id")
        self.st_ids = list(net.stations.station_id)
        self.st_idx = {s: i for i, s in enumerate(self.st_ids)}
        self.st_lat = net.stations.lat.values
        self.st_lon = net.stations.lon.values
        modes = net.routes.set_index("route_id")["mode"]

        # per (route, dir): ordered stops with cumulative minutes / km
        self.seqs: dict[tuple, pd.DataFrame] = {}
        by_station: dict[int, list] = {}
        for (rid, d), g in net.route_stop.groupby(["route_id", "direction"]):
            g = g.sort_values("seq").reset_index(drop=True)
            m = modes[rid]
            g["cum_min"] = (g.run_min + np.where(np.arange(len(g)) > 0, DWELL_EST_MIN[m], 0)).cumsum()
            g["cum_km"] = g.dist_from_prev_m.cumsum() / 1000
            g["station"] = g.stop_id.map(stops.station_id).map(self.st_idx)
            self.seqs[(rid, d)] = {k: g[k].to_numpy() for k in ("seq", "cum_min", "cum_km", "station", "stop_id")}
            for i, r in g.iterrows():
                if i < len(g) - 1:  # can board here
                    by_station.setdefault(int(r.station), []).append((rid, d, i))
        self.modes = modes.to_dict()
        walks: dict[int, list] = {}
        for _, t in net.transfers.iterrows():
            walks.setdefault(self.st_idx[t.from_station], []).append((self.st_idx[t.to_station], float(t.walk_min)))
        self.by_station = by_station
        self.walks = walks
        self.options: dict[tuple[int, int], list[Option]] = {}
        self._build(min_km)

    def _leg(self, rid, d, i, j) -> Leg:
        g = self.seqs[(rid, d)]
        return Leg(rid, d, int(g["seq"][i]), int(g["seq"][j]), self.modes[rid],
                   float(g["cum_km"][j] - g["cum_km"][i]), float(g["cum_min"][j] - g["cum_min"][i]))

    def _add(self, o, dst, legs, walk, egress=0.0, egress_fare=0.0):
        if o == dst:
            return
        ivt = sum(l.ivt for l in legs)
        fare = sum(fare_for(l.mode, l.km) for l in legs)
        opt = Option(tuple(legs), ivt, walk, fare, len(legs) - 1, tuple(l.mode for l in legs), egress, egress_fare)
        lst = self.options.setdefault((o, dst), [])
        for k, ex in enumerate(lst):
            if ex.key == opt.key:
                if opt.gen_time < ex.gen_time:
                    lst[k] = opt
                return
        lst.append(opt)

    def _build(self, min_km: float):
        for o, boards in self.by_station.items():
            for rid, d, i in boards:
                g = self.seqs[(rid, d)]
                for j in range(i + 1, len(g["seq"])):
                    leg1 = self._leg(rid, d, i, j)
                    t_st = int(g["station"][j])
                    self._add(o, t_st, [leg1], 0.0)
                    for t2, w in [(t_st, 0.0)] + self.walks.get(t_st, []):
                        for rid2, d2, i2 in self.by_station.get(t2, []):
                            if rid2 == rid:
                                continue
                            g2 = self.seqs[(rid2, d2)]
                            for j2 in range(i2 + 1, len(g2["seq"])):
                                dst = int(g2["station"][j2])
                                if dst == o:
                                    continue
                                self._add(o, dst, [leg1, self._leg(rid2, d2, i2, j2)], w)
        # straight-line distances between stations (for gravity, egress) and reachability
        n = len(self.st_ids)
        from common.config import haversine_m

        self.km = np.zeros((n, n))
        for i in range(n):
            self.km[i] = haversine_m(self.st_lat[i], self.st_lon[i], self.st_lat, self.st_lon) / 1000
        self._add_egress()
        # prune: drop options much slower than the best one; keep at most MAX_OPTIONS
        pen = lambda x: x.gen_time + self.transfer_penalty * x.transfers  # noqa: E731
        for k, lst in self.options.items():
            lst.sort(key=pen)
            best = lst[0].gen_time
            self.options[k] = [x for x in lst if pen(x) <= 1.8 * best + 10][:MAX_OPTIONS]
        self.reach = np.zeros((n, n), dtype=bool)
        for (o, dst) in self.options:
            self.reach[o, dst] = True
        self.reach &= self.km >= min_km

    def _add_egress(self):
        """Rail rider's last mile by auto / share-auto / walk (not simulated): one transit leg to a station
        within egress.max_km of the destination, then an off-network egress with its own time and cost.
        Without this, every rail rider bound for a bus-only area is forced onto the few modelled buses."""
        from common.config import demand_config

        e = demand_config().get("egress")
        if not e:
            return
        direct = [(o, t, opt) for (o, t), lst in list(self.options.items()) for opt in lst
                  if opt.transfers == 0 and not opt.egress and opt.legs[0].mode in e["modes"]]
        for o, t, opt in direct:
            near = np.nonzero((self.km[t] > 0) & (self.km[t] <= e["max_km"]))[0]
            for d in near:
                if d == o:
                    continue
                km = float(self.km[t, d]) * e["detour"]
                mins = e["wait_min"] + km / e["speed_kmh"] * 60
                self._add(o, int(d), list(opt.legs), 0.0, egress=mins, egress_fare=e["fare_base"] + e["fare_per_km"] * km)
