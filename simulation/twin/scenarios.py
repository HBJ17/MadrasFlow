"""Scenarios (section 5.5): rain, events, college reopening, metro disruption, extra trips, custom.

A Scenario is resolved per simulated day: the named scenario's effects are combined with what the
calendar says about that day (weekend/holiday, observed rain, events in data/events.csv)."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import pandas as pd

from common.config import hhmm_to_min, load_yaml

SCENARIO_IDS = ["baseline", "weekend", "rain_heavy", "cricket_match", "college_reopening",
                "metro_disruption", "cyclone", "extra_trips", "builder", "custom"]


@dataclass
class Scenario:
    scenario_id: str = "baseline"
    day_type: str | None = None                      # override (weekend)
    demand_mult: dict = field(default_factory=lambda: {"bus": 1.0, "metro": 1.0, "mrts": 1.0})
    run_time_mult: float = 1.0
    dispatch_delay_mult: dict = field(default_factory=dict)
    day_total_mult: float = 1.0
    stop_type_mult: dict = field(default_factory=dict)
    surges: list = field(default_factory=list)       # {station, from_min, to_min, factor, kind}
    headway_changes: list = field(default_factory=list)  # {modes, from_min, to_min, mult}; mult=inf suspends
    extra_trips: list = field(default_factory=list)  # {route, direction, start, end, n}
    tags: list = field(default_factory=list)

    @property
    def max_mode_mult(self) -> float:
        return max(self.demand_mult.values())


def list_scenarios() -> list[dict]:
    cfg = load_yaml("scenarios.yaml")
    return [{"id": k, "label": v.get("label", k), "params": {kk: vv for kk, vv in v.items() if kk != "label"}}
            for k, v in cfg.items()]


def _apply_rain(s: Scenario, rc: dict):
    for m, v in rc.get("demand_mult", {}).items():
        s.demand_mult[m] = s.demand_mult.get(m, 1.0) * v
    s.run_time_mult *= rc.get("run_time_mult", 1.0)
    for m, v in rc.get("dispatch_delay_mult", {}).items():
        s.dispatch_delay_mult[m] = s.dispatch_delay_mult.get(m, 1.0) * v


def _apply_builder(s: Scenario, sc: dict, cfg: dict, dcfg: dict, add_event, net) -> None:
    """Scenario builder: combine any subset of day type, weather, events, disruptions, demand and fleet."""
    if sc.get("day_type") in ("weekend", "holiday"):
        s.day_type = "weekend"   # holidays use the weekend profile
        s.tags.append(sc["day_type"])
    w = sc.get("weather") or "dry"
    if w == "light":
        lm = dcfg["weather"]["light_mult"]
        _apply_rain(s, {"demand_mult": {k: lm[k] for k in ("bus", "metro", "mrts")}, "run_time_mult": lm["run_time"]})
    elif w == "heavy":
        _apply_rain(s, cfg["rain_heavy"])
    elif w == "cyclone":
        cy = cfg["cyclone"]
        _apply_rain(s, cy)
        s.day_total_mult *= cy["day_total_mult"]
        w0, w1 = (hhmm_to_min(x) for x in cy["window"])
        for m, mult in cy["headway_mult"].items():
            s.headway_changes.append({"modes": [m], "from_min": w0, "to_min": w1, "mult": float(mult)})
        s.headway_changes.append({"modes": cy["suspend_modes"], "from_min": w0, "to_min": w1, "mult": float("inf")})
    if w != "dry":
        s.tags.append(f"weather_{w}")
    ev_cfg, cat = sc.get("event_defaults", {}), cfg["cricket_match"]["catchment_capacity"]
    for e in sc.get("events") or []:
        att = int(e["attendance"])
        add_event(e["venue_stop"], hhmm_to_min(e["start"]), hhmm_to_min(e["end"]), att, cat,
                  ev_cfg.get("before_h", 2), ev_cfg.get("after_h", 1), 1.0 + 0.2 * min(att, 60000) / 35000)
        s.tags.append("event")
    for dsr in sc.get("disruptions") or []:
        a, b = hhmm_to_min(dsr["from"]), hhmm_to_min(dsr["to"])
        mult, modes = {"metro_delay": (sc.get("metro_delay_headway_mult", 2.0), ["metro"]),
                       "mrts_suspended": (float("inf"), ["mrts"]),
                       "bus_cut": (sc.get("bus_cut_headway_mult", 1.35), ["bus"])}[dsr["kind"]]
        s.headway_changes.append({"modes": modes, "from_min": a, "to_min": b, "mult": float(mult)})
        s.tags.append(dsr["kind"])
    pct = float(sc.get("demand_pct") or 0)
    if pct:
        s.day_total_mult *= 1 + max(-50.0, min(50.0, pct)) / 100
    if sc.get("fleet"):
        from twin.fleet import buses_to_trips

        trips, _ = buses_to_trips(net, sc["fleet"])
        s.extra_trips = s.extra_trips + trips
        s.tags.append("fleet_plan")


def resolve(scenario_id: str, ctx, net, dcfg: dict, mods: dict | None = None, use_calendar: bool = True) -> Scenario:
    """Combine the named scenario with the day's calendar/weather/events context."""
    cfg = load_yaml("scenarios.yaml")
    if scenario_id not in cfg:
        raise ValueError(f"unknown scenario {scenario_id!r}; choose from {list(cfg)}")
    sc = copy.deepcopy(cfg[scenario_id])
    if mods:
        sc.update(mods)
    s = Scenario(scenario_id=scenario_id)
    st_of_stop = net.stops.set_index("stop_id").station_id
    st_idx = {sid: i for i, sid in enumerate(net.stations.station_id)}

    def station(stop_id):
        sid = st_of_stop.get(stop_id)
        return st_idx.get(sid) if sid else None

    if sc.get("day_type"):
        s.day_type = sc["day_type"]

    # Weather: the named scenario, or the observed rain on that date
    if scenario_id == "rain_heavy":
        _apply_rain(s, sc)
        s.tags.append("rain_heavy")
    elif use_calendar and ctx.weather == "heavy":
        _apply_rain(s, cfg["rain_heavy"])
        s.tags.append("rain_observed_heavy")
    elif use_calendar and ctx.weather == "light":
        lm = dcfg["weather"]["light_mult"]
        _apply_rain(s, {"demand_mult": {k: lm[k] for k in ("bus", "metro", "mrts")}, "run_time_mult": lm["run_time"]})
        s.tags.append("rain_observed_light")

    def add_event(venue_stop, start_min, end_min, attendance, catchment, before_h, after_h, day_mult):
        f = 1 + attendance / catchment
        stn = station(venue_stop)
        s.surges.append({"station": stn, "from_min": start_min - before_h * 60, "to_min": start_min,
                         "factor": f, "kind": "attract"})
        s.surges.append({"station": stn, "from_min": end_min, "to_min": end_min + after_h * 60,
                         "factor": f, "kind": "produce"})
        s.day_total_mult *= day_mult

    if scenario_id == "cricket_match":
        add_event(sc["venue_stop"], hhmm_to_min(sc["match_start"]), hhmm_to_min(sc["match_end"]),
                  sc["attendance"], sc["catchment_capacity"], sc["before_h"], sc["after_h"], sc["day_total_mult"])
        s.tags.append("event")
    if scenario_id == "college_reopening":
        s.stop_type_mult.update(sc["stop_type_mult"])
    if scenario_id == "metro_disruption":
        w0, w1 = sc["window"]
        s.headway_changes.append({"modes": sc["modes"], "from_min": hhmm_to_min(w0), "to_min": hhmm_to_min(w1),
                                  "mult": sc["headway_mult"]})
    if scenario_id == "cyclone":
        _apply_rain(s, sc)
        s.day_total_mult *= sc["day_total_mult"]
        w0, w1 = (hhmm_to_min(x) for x in sc["window"])
        for m, mult in sc["headway_mult"].items():
            s.headway_changes.append({"modes": [m], "from_min": w0, "to_min": w1, "mult": float(mult)})
        s.headway_changes.append({"modes": sc["suspend_modes"], "from_min": w0, "to_min": w1, "mult": float("inf")})
        s.tags.append("cyclone")
    if scenario_id == "builder":
        _apply_builder(s, sc, cfg, dcfg, add_event, net)
    if sc.get("extra_trips"):
        s.extra_trips = s.extra_trips + list(sc["extra_trips"])
    if scenario_id == "custom":
        for k in ("demand_mult", "dispatch_delay_mult", "stop_type_mult"):
            if k in sc:
                getattr(s, k).update(sc[k])
        for k in ("run_time_mult", "day_total_mult"):
            if k in sc:
                setattr(s, k, float(sc[k]))

    # Calendar events on this date (data/events.csv)
    if use_calendar:
        cat = load_yaml("scenarios.yaml")["cricket_match"]["catchment_capacity"]
        for e in ctx.events:
            st, en = pd.Timestamp(e["start_ts"]), pd.Timestamp(e["end_ts"])
            if int(e["expected_attendance"]) > 0:
                if st.date() == ctx.date.date():
                    add_event(e["stop_id"], st.hour * 60 + st.minute, en.hour * 60 + en.minute,
                              int(e["expected_attendance"]), cat, 2, 1, float(e["multiplier"]))
                    s.tags.append("event")
            else:  # multi-day stop-type effect (college reopening, exams)
                s.stop_type_mult["college"] = s.stop_type_mult.get("college", 1.0) * float(e["multiplier"])
                s.tags.append("college")
    return s
