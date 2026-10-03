"""Ranking for the commuter planner.

Each ticked criterion is turned into a penalty on a fixed scale, so a score does not depend on which
other options happen to be listed, and the penalties are summed (lower is better):

  crowd      worst crowd level on the trip, LOW 0 .. CROWDED 1, plus a little for the average level
  eta        minutes after the earliest arrival among the options, 30 min = 1
  cost       rupees above the cheapest option, Rs 50 = 1
  walk       walking minutes, 15 min = 1
  transfers  number of transfers, 2 = 1

So one crowd level step weighs about as much as 10 minutes of travel. Crowd and arrival time are
ticked by default; ties go to the shorter trip.
"""
from __future__ import annotations

import pandas as pd

from routing.graph import CROWD_F

CRITERIA = ("crowd", "eta", "cost", "walk", "transfers")
DEFAULT = ("crowd", "eta")
LEVEL_IX = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CROWDED": 3}
SCALE = {"eta": 30.0, "cost": 50.0, "walk": 15.0, "transfers": 2.0}


def criteria_of(criteria) -> list[str]:
    crit = [c for c in (DEFAULT if criteria is None else criteria) if c in CRITERIA]
    return crit or ["eta"]


def score(its: list[dict], criteria, across_slots: bool = False) -> list[float]:
    """across_slots: compare journey time instead of arrival time (an earlier slot arrives earlier anyway)."""
    if not its:
        return []
    t = [it["total_min"] if across_slots else pd.Timestamp(it["arrive_at"]).timestamp() / 60 for it in its]
    t0, f0 = min(t), min(it["fare"] for it in its)
    tot = [0.0] * len(its)
    for c in criteria_of(criteria):
        for i, it in enumerate(its):
            if c == "crowd":
                tot[i] += LEVEL_IX[it["worst_level"]] / 3 + 0.1 * it["crowd_score"] / CROWD_F["CROWDED"]
            elif c == "eta":
                tot[i] += (t[i] - t0) / SCALE["eta"]
            elif c == "cost":
                tot[i] += (it["fare"] - f0) / SCALE["cost"]
            elif c == "walk":
                tot[i] += it["walk_min"] / SCALE["walk"]
            else:
                tot[i] += it["transfers"] / SCALE["transfers"]
    return tot


def rank(its: list[dict], criteria) -> list[dict]:
    s = score(its, criteria)
    order = sorted(range(len(its)), key=lambda i: (s[i], its[i]["total_min"]))
    return [{**its[i], "score": round(s[i], 3), "rank": n + 1} for n, i in enumerate(order)]


def mark_best_overall(slots: list[dict], criteria) -> None:
    """Tags the single best itinerary across all slots (scored together) with best_overall=True."""
    flat = [(si, ii) for si, s in enumerate(slots) for ii in range(len(s["itineraries"]))]
    if not flat:
        return
    its = [slots[si]["itineraries"][ii] for si, ii in flat]
    s = score(its, criteria, across_slots=True)
    best = min(range(len(its)), key=lambda i: (s[i], its[i]["total_min"]))
    for i, (si, ii) in enumerate(flat):
        slots[si]["itineraries"][ii]["best_overall"] = i == best
