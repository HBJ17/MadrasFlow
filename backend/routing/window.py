"""Trip planning over a departure window (commuter planner): one ranked list of itineraries per
15-minute departure slot, e.g. 08:30 +/- 15 -> slots 08:15, 08:30 and 08:45.

The graph, timetable and forecast are built once for the earliest slot; every slot then runs the
earliest-arrival search from its own start offset, enumerates candidate paths under a few crowd
weights (Yen's k-shortest paths) and re-times each candidate exactly against the timetable.
"""
from __future__ import annotations

import itertools

import networkx as nx
import pandas as pd

from common import clock
from common.config import IST, iso
from routing.filters import TripFilters, apply
from routing.ranking import criteria_of, mark_best_overall, rank
from routing.recommend import Planner

SLOT_MIN = 15
MAX_WINDOW_MIN = 120
WEIGHTS = (0.0, 1.0, 3.0)   # crowd weight per candidate search: fastest .. least crowded
K_PATHS = 4
MAX_PER_SLOT = 6
MAX_TRANSFERS = 2


def slot_times(center: pd.Timestamp, window_min: int) -> list[pd.Timestamp]:
    k = max(0, min(MAX_WINDOW_MIN, int(window_min))) // SLOT_MIN
    return [center + pd.Timedelta(minutes=SLOT_MIN * i) for i in range(-k, k + 1)]


def _routes_of(it: dict) -> tuple:
    return tuple(l["route_id"] for l in it["legs"] if l["kind"] == "ride")


def slot_itineraries(P: Planner, o, dst, t0: float, prefer_low: bool = False) -> list[dict]:
    """All distinct itineraries leaving at offset t0 (minutes after P.now), best per route sequence."""
    eta = P.earliest(o, t0)
    if dst not in eta:
        return []
    seen, its = set(), []
    for w in WEIGHTS:
        P.weights(eta, w)
        try:
            paths = list(itertools.islice(nx.shortest_simple_paths(P.G, o, dst, weight="w"), K_PATHS))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            break
        for path in paths:
            it = P.retime(path, prefer_low, t0)
            if not it or it["transfers"] > MAX_TRANSFERS or len(set(_routes_of(it))) < len(_routes_of(it)):
                continue  # no re-boarding a route already used, at most two transfers
            if it["signature"] not in seen:
                seen.add(it["signature"])
                its.append(it)
    best: dict[tuple, dict] = {}
    for it in its:
        k = _routes_of(it)
        if k not in best or (it["total_min"], it["crowd_total"]) < (best[k]["total_min"], best[k]["crowd_total"]):
            best[k] = it
    cand = list(best.values())
    # drop an option another one beats outright: no slower, no more crowded, fewer transfers
    keep = [it for it in cand if not any(o is not it and o["total_min"] <= it["total_min"] and o["crowd_total"] <= it["crowd_total"]
                                         and o["transfers"] < it["transfers"] for o in cand)]
    return [{k: v for k, v in it.items() if k != "signature"} for it in keep]


def plan_window(from_stop: str, to_stop: str, center=None, window_min: int = 15, filters: dict | TripFilters | None = None,
                rank_by: list[str] | None = None) -> dict:
    f = filters if isinstance(filters, TripFilters) else TripFilters.from_dict(filters)
    center = pd.Timestamp(center or clock.now())
    center = (center.tz_localize(IST) if center.tzinfo is None else center).tz_convert(IST).floor("min")
    slots = slot_times(center, window_min)
    P = Planner(slots[0])
    if from_stop not in P.station_of_stop or to_stop not in P.station_of_stop:
        raise ValueError("unknown stop id")
    o, dst = ("S", P.station_of_stop[from_stop]), ("S", P.station_of_stop[to_stop])
    if o == dst:
        raise ValueError("origin and destination are the same place")
    out = []
    for s in slots:
        t0 = (s - slots[0]).total_seconds() / 60
        raw = slot_itineraries(P, o, dst, t0)
        its = [x for x in (apply(it, f) for it in raw) if x is not None]
        its = rank(its, rank_by)[:MAX_PER_SLOT]
        out.append({"depart_at": iso(s), "itineraries": its, "filtered_out": len(raw) - len(its)})
    mark_best_overall(out, rank_by)
    srcs = P.fc.get("_sources", set())
    ds = "mixed" if "mixed" in srcs or {"twin", "camera"} <= srcs else ("camera" if "camera" in srcs else ("twin" if "twin" in srcs else "none"))
    return {"from_stop": from_stop, "to_stop": to_stop, "from": P.names[from_stop], "to": P.names[to_stop],
            "center": iso(center), "window_min": int(window_min), "rank_by": criteria_of(rank_by), "slots": out,
            "data_source": ds, "simulated": ds in ("twin", "mixed")}
