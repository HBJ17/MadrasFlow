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


class TwinRunRequest(BaseModel):
    scenario: str = "baseline"
    start_date: str | None = None
    days: int = Field(default=1, ge=1, le=7)
    seed: int = 42
    mods: dict | None = None
