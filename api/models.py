"""Pydantic request/response models. Kept compact: the mobile client may be on a weak link."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Level = Literal["LOW", "MEDIUM", "HIGH", "CROWDED"]
DataSource = Literal["twin", "camera", "mixed", "none"]


class EventIn(BaseModel):
    """One event row as posted by a camera node or any feed. No binary fields by design:
    images and video are never accepted."""
    model_config = ConfigDict(extra="forbid")

    ts: datetime
    stop_id: str
    source: Literal["camera_stop", "camera_vehicle", "afc_real", "twin"]
    route_id: str | None = None
    trip_id: str | None = None
    vehicle_id: str | None = None
    direction: int | None = Field(default=None, ge=0, le=1)
    boardings: int = 0
    alightings: int = 0
    onboard_load: int | None = None
    waiting_count: int | None = None
    left_behind: int | None = None
    payment_mode: Literal["card", "qr", "cash", "unknown"] | None = None
    fare_inr: float | None = None
    client_event_id: str | None = Field(default=None, max_length=128)
    node_id: str | None = Field(default=None, max_length=64)


class IngestResult(BaseModel):
    accepted: int
    rejected: int
    errors: list[str]


class Heartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(max_length=64)
    battery: float | None = None
    fps: float | None = None
    kind: str | None = None


class PlanRequest(BaseModel):
    from_stop: str
    to_stop: str
    depart_at: datetime | None = None
    prefer_low_crowd: bool = False


class PlanFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modes: list[Literal["bus", "mrts", "metro"]] | None = None
    max_walk_min: float | None = Field(default=None, ge=0, le=60)
    max_fare: float | None = Field(default=None, ge=0, le=500)
    max_transfers: int | None = Field(default=None, ge=0, le=2)
    step_free: bool = False
    women: bool = False
    access_walk_min: float = Field(default=0, ge=0, le=60)   # walk from the user's location to the first stop


class PlanWindowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_stop: str
    to_stop: str
    depart_at: datetime | None = None               # centre of the window; default now
    window_min: int = Field(default=15, ge=0, le=120, multiple_of=15)
    filters: PlanFilters = PlanFilters()
    rank_by: list[Literal["crowd", "eta", "cost", "walk", "transfers"]] | None = None   # None = crowd + eta


class ExtraTrip(BaseModel):
    route: str
    direction: int | None = None
    start: str          # "HH:MM"
    end: str
    n: int = Field(ge=1, le=20)


class WhatIfRequest(BaseModel):
    base_scenario: str = "baseline"
    extra_trips: list[ExtraTrip] = []
    date: str | None = None
    seed: int = 7


HHMM = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class BuilderEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    venue_stop: str
    attendance: int = Field(ge=500, le=100000)
    start: str = HHMM
    end: str = HHMM


class BuilderDisruption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["metro_delay", "mrts_suspended", "bus_cut"]
    from_: str = Field(alias="from", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    to: str = HHMM


class FleetCell(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route: str
    direction: int | None = Field(default=None, ge=0, le=1)
    hour: int = Field(ge=4, le=23)
    buses: int = Field(ge=1, le=10)


class BuilderPlan(BaseModel):
    """Scenario builder: every part is optional, so a run can be conditions only, fleet only, or both."""
    model_config = ConfigDict(extra="forbid")
    day_type: Literal["weekday", "weekend", "holiday"] | None = None
    weather: Literal["dry", "light", "heavy", "cyclone"] | None = None
    events: list[BuilderEvent] = Field(default_factory=list, max_length=3)
    disruptions: list[BuilderDisruption] = Field(default_factory=list, max_length=4)
    demand_pct: float = Field(default=0, ge=-50, le=50)
    fleet: list[FleetCell] = Field(default_factory=list, max_length=200)

    def has_changes(self) -> bool:
        return bool((self.weather not in (None, "dry")) or self.events or self.disruptions or self.demand_pct or self.fleet
                    or self.day_type in ("weekend", "holiday"))


class TwinRunRequest(BaseModel):
    scenario: str = "baseline"
    start_date: str | None = None
    days: int = Field(default=1, ge=1, le=7)
    seed: int = 42
    mods: dict | None = None
