"""Trip filters for the commuter planner: modes, walking, fare, transfers, step-free access and the
women's option (free MTC ordinary buses; short walks and waits after dark). Rules and assumptions
live in config/accessibility.yaml."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from functools import lru_cache

import pandas as pd

from common.config import IST, hhmm_to_min, load_yaml

MODES = ("bus", "mrts", "metro")


@dataclass
class TripFilters:
    modes: set = field(default_factory=lambda: set(MODES))
    max_walk_min: float | None = None
    max_fare: float | None = None
    max_transfers: int | None = None
    step_free: bool = False
    women: bool = False
    access_walk_min: float = 0.0      # walk from the user's location to the first stop

    @classmethod
    def from_dict(cls, d: dict | None) -> "TripFilters":
        d = dict(d or {})
        modes = set(d.pop("modes", None) or MODES) & set(MODES)
        return cls(modes=modes or set(MODES), **{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@lru_cache(maxsize=1)
def rules() -> dict:
    return load_yaml("accessibility.yaml")


def stop_step_free(stop_id: str, mode: str) -> bool:
    r = rules()["step_free"]
    if stop_id in (r.get("stop_overrides") or {}):
        return bool(r["stop_overrides"][stop_id])
    return bool(r.get(mode, False))


def low_floor(route_id: str):
    lf = rules()["low_floor_bus"]
    return (lf.get("routes") or {}).get(route_id, lf.get("default", "unknown"))


def after_dark(ts: str) -> bool:
    w = rules()["women"]
    t = pd.Timestamp(ts).tz_convert(IST)
    m = t.hour * 60 + t.minute
    a, b = hhmm_to_min(w["after_dark_from"]), hhmm_to_min(w["after_dark_to"])
    return m >= a or m < b


def apply(it: dict, f: TripFilters) -> dict | None:
    """Returns the itinerary (copied, with fare concessions and notes applied) or None if filtered out."""
    rides = [l for l in it["legs"] if l["kind"] == "ride"]
    if any(l["mode"] not in f.modes for l in rides):
        return None
    if f.max_transfers is not None and it["transfers"] > f.max_transfers:
        return None
    it = copy.deepcopy(it)
    notes = []
    it["walk_min"] = round(it["walk_min"] + (f.access_walk_min or 0), 1)
    if f.max_walk_min is not None and it["walk_min"] > f.max_walk_min:
        return None
    if f.women:
        free = set(rules()["women"]["free_bus_routes"])
        for l in it["legs"]:
            if l["kind"] == "ride" and l["route_id"] in free:
                l["fare"] = 0.0
        if any(l["kind"] == "ride" and l["route_id"] in free for l in it["legs"]):
            notes.append("free_bus_women")
        it["fare"] = round(sum(l["fare"] for l in it["legs"] if l["kind"] == "ride"), 1)
        if after_dark(rides[0]["board_at"]):
            w = rules()["women"]
            if it["walk_min"] > w["after_dark_max_walk_min"] or any(l["wait_min"] > w["after_dark_max_wait_min"] for l in rides):
                return None
            notes.append("after_dark_short_walks_waits")
    if f.max_fare is not None and it["fare"] > f.max_fare:
        return None
    if f.step_free:
        for l in rides:
            if l["mode"] == "bus":
                lfb = low_floor(l["route_id"])
                if lfb is False:
                    return None
                if lfb == "unknown":
                    notes.append(f"low_floor_not_guaranteed:{l['route']}")
            elif not (stop_step_free(l["from_stop"], l["mode"]) and stop_step_free(l["to_stop"], l["mode"])):
                return None
    it["notes"] = notes
    return it
