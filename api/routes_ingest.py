"""POST /ingest/events and /ingest/heartbeat (camera nodes or any feed).

Validation (section 9): unknown stop_id, negative counts and timestamps more than 10 minutes in
the future are rejected. client_event_id makes posts idempotent. Vehicle-camera rows are joined
to the nearest stop-camera waiting count by stop_id + time (section 11.4); raw rows are kept.
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
from fastapi import APIRouter, Body, Depends, HTTPException

from api.deps import require_api_key, routes_df, stop_ids
from api.models import EventIn, Heartbeat, IngestResult
from common import clock
from common.config import IST, floor_15, iso
from db.database import engine, execute, query

router = APIRouter(prefix="/ingest")
MAX_BATCH = 500
JOIN_WINDOW_S = 60
LEFT_BEHIND_LF = 0.9


def _validate(e: EventIn, now) -> str | None:
    if e.stop_id not in stop_ids():
        return f"unknown stop_id {e.stop_id!r}"
    for f in ("boardings", "alightings", "onboard_load", "waiting_count", "left_behind"):
        v = getattr(e, f)
        if v is not None and v < 0:
            return f"negative {f}"
    ts = e.ts if e.ts.tzinfo else e.ts.replace(tzinfo=IST)
    if ts > now + timedelta(minutes=10):
        return "timestamp more than 10 minutes in the future"
    if e.route_id is not None and e.route_id not in set(routes_df().route_id):
        return f"unknown route_id {e.route_id!r}"
    return None


def _waiting_near(stop_id: str, ts, before: bool) -> int | None:
    """Stop-camera waiting_count closest before (or after) ts within 60 s."""
    lo, hi = (ts - timedelta(seconds=JOIN_WINDOW_S), ts) if before else (ts, ts + timedelta(seconds=JOIN_WINDOW_S))
    order = "DESC" if before else "ASC"
    r = query(f"SELECT waiting_count FROM camera_raw WHERE source='camera_stop' AND stop_id=:s AND ts>=:lo AND ts<=:hi "
              f"ORDER BY ts {order} LIMIT 1", {"s": stop_id, "lo": iso(lo), "hi": iso(hi)})
    return int(r.waiting_count.iloc[0]) if len(r) and pd.notna(r.waiting_count.iloc[0]) else None


def _merge_vehicle(e: EventIn, ts) -> dict:
    row = e.model_dump(exclude={"node_id"})
    prev = None
    if e.vehicle_id:
        p = query("SELECT onboard_load FROM event WHERE source='camera_vehicle' AND vehicle_id=:v AND ts<:t "
                  "ORDER BY ts DESC LIMIT 1", {"v": e.vehicle_id, "t": iso(ts)})
        prev = int(p.onboard_load.iloc[0]) if len(p) and pd.notna(p.onboard_load.iloc[0]) else None
    if prev is not None:
        load_after = max(0, prev + e.boardings - e.alightings)
        # Cross-check with the node's own running count; keep the node's value if it reported one.
        row["onboard_load"] = e.onboard_load if e.onboard_load is not None else load_after
    elif e.onboard_load is None:
        row["onboard_load"] = max(0, e.boardings - e.alightings)
    waiting_before = _waiting_near(e.stop_id, ts, before=True)
    waiting_after = _waiting_near(e.stop_id, ts, before=False)
    cap = None
    if e.route_id:
        r = routes_df()
        cap = int(r.loc[r.route_id == e.route_id, "capacity_total"].iloc[0])
    lf = (row["onboard_load"] / cap) if cap else 0
    row["left_behind"] = max(0, waiting_before - e.boardings) if (waiting_before is not None and lf >= LEFT_BEHIND_LF) else 0
    row["waiting_count"] = waiting_after if waiting_after is not None else e.waiting_count
    return row


@router.post("/events", response_model=IngestResult)
def ingest_events(events: list[EventIn] = Body(...), _key: str = Depends(require_api_key)):
    if len(events) > MAX_BATCH:
        raise HTTPException(413, f"batch too large: max {MAX_BATCH} events")
    now = clock.now()
    errors, rows, raws = [], [], []
    ids = [e.client_event_id for e in events if e.client_event_id]
    seen = set()
    if ids:
        ph = ",".join(f":i{k}" for k in range(len(ids)))
        seen = set(query(f"SELECT client_event_id FROM event WHERE client_event_id IN ({ph})",
                         {f"i{k}": v for k, v in enumerate(ids)}).client_event_id)
    for i, e in enumerate(events):
        err = _validate(e, now)
        if err:
            errors.append(f"[{i}] {err}")
            continue
        if e.client_event_id and e.client_event_id in seen:
            continue  # duplicate: ignored, not an error (idempotent retry)
        if e.client_event_id:
            seen.add(e.client_event_id)
        ts = (e.ts if e.ts.tzinfo else e.ts.replace(tzinfo=IST)).astimezone(IST)
        if e.source.startswith("camera"):
            raws.append({"received_at": iso(now), "node_id": e.node_id, "source": e.source, "ts": iso(ts),
                         "stop_id": e.stop_id, "vehicle_id": e.vehicle_id, "route_id": e.route_id, "trip_id": e.trip_id,
                         "boardings": e.boardings, "alightings": e.alightings, "onboard_load": e.onboard_load,
                         "waiting_count": e.waiting_count, "client_event_id": e.client_event_id})
        rows.append((e, ts))
    if raws:
        pd.DataFrame(raws).to_sql("camera_raw", engine(), if_exists="append", index=False)
    out = []
    for e, ts in rows:
        row = _merge_vehicle(e, ts) if e.source == "camera_vehicle" else e.model_dump(exclude={"node_id"})
        row["ts"] = iso(ts)
        row["slot_15"] = iso(floor_15(ts))
        if row.get("payment_mode") is None and e.source.startswith("camera"):
            row["payment_mode"] = "unknown"
        out.append(row)
    if out:
        pd.DataFrame(out).to_sql("event", engine(), if_exists="append", index=False)
    return IngestResult(accepted=len(out), rejected=len(errors), errors=errors[:50])


@router.post("/heartbeat")
def heartbeat(hb: Heartbeat, _key: str = Depends(require_api_key)):
    execute("INSERT INTO node_heartbeat(node_id, last_seen, battery, fps, kind) VALUES (:n,:t,:b,:f,:k) "
            "ON CONFLICT(node_id) DO UPDATE SET last_seen=excluded.last_seen, battery=excluded.battery, "
            "fps=excluded.fps, kind=excluded.kind",
            {"n": hb.node_id, "t": iso(clock.now()), "b": hb.battery, "f": hb.fps, "k": hb.kind})
    return {"ok": True}
