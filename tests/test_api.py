"""API contract tests (FastAPI TestClient, scheduler disabled)."""
from datetime import datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from common.config import IST

H = {"X-API-Key": "dev-key"}


@pytest.fixture(scope="module")
def client(seeded_db):
    from api.deps import clear_caches
    from api.main import app

    clear_caches()
    return TestClient(app)


def test_health(client):
    r = client.get("/api/v1/health").json()
    assert r["ok"] and r["sources"]["twin"] > 0 and r["data_source"] == "twin" and r["simulated"] is True


def test_routes_and_stops(client):
    routes = client.get("/api/v1/routes").json()
    assert {r["route_id"] for r in routes} >= {"BUS_51R", "BUS_95", "MRTS_BV", "METRO_BLUE_S"}
    assert all(r["stops"] > 1 for r in routes)
    s = client.get("/api/v1/stops", params={"q": "velachery"}).json()
    assert any(x["stop_id"] == "MRTS_VLCY" for x in s)


def test_ingest_validation_and_idempotency(client):
    now = datetime.now(IST)
    good = {"ts": now.isoformat(), "stop_id": "MRTS_VLCY", "source": "camera_stop", "waiting_count": 7, "client_event_id": "api-t1"}
    bad = [{"ts": now.isoformat(), "stop_id": "NOPE", "source": "camera_stop"},
           {"ts": now.isoformat(), "stop_id": "MRTS_VLCY", "source": "camera_stop", "alightings": -2},
           {"ts": (now + timedelta(minutes=30)).isoformat(), "stop_id": "MRTS_VLCY", "source": "camera_stop"}]
    r = client.post("/api/v1/ingest/events", json=[good] + bad, headers=H).json()
    assert r["accepted"] == 1 and r["rejected"] == 3
    r2 = client.post("/api/v1/ingest/events", json=[good], headers=H).json()
    assert r2["accepted"] == 0 and r2["rejected"] == 0
    assert client.post("/api/v1/ingest/events", json=[good]).status_code == 401
    assert client.post("/api/v1/ingest/events", json=[{**good, "frame_jpeg": "..."}], headers=H).status_code == 422
    assert client.post("/api/v1/ingest/events", json=[good] * 501, headers=H).status_code == 413
    assert client.post("/api/v1/ingest/heartbeat", json={"node_id": "t", "fps": 5}, headers=H).json()["ok"]


def test_occupancy_and_forecast_shape(client, seeded_db):
    from predictor.serve import run_forecast
    from tests.conftest import SIM_START

    at = pd.Timestamp(SIM_START, tz=IST) + pd.Timedelta(days=1, hours=9)
    run_forecast(at)
    from api import live

    live._cache.clear()
    r = client.get("/api/v1/occupancy/route/BUS_95", params={"direction": 0, "at": at.isoformat()})
    assert r.status_code == 200 and r.headers["cache-control"] == "max-age=30"
    j = r.json()
    assert j["data_source"] == "twin" and j["simulated"] is True
    assert len(j["stops"]) > 10 and {"stop_id", "seq", "level", "load_factor", "lo", "hi", "source", "stale"} <= set(j["stops"][0])
    f = client.get("/api/v1/forecast", params={"route_id": "BUS_95", "model": "baseline"}).json()
    assert f["rows"] and f["data_source"] == "twin"
    st = client.get("/api/v1/occupancy/stop/MRTS_VLCY", params={"at": at.isoformat()}).json()
    assert "vehicles" in st and st["data_source"] in ("twin", "mixed", "none")
    h = client.get("/api/v1/history", params={"stop_id": "MRTS_VLCY", "route_id": "MRTS_BV"}).json()
    assert len(h["lf"]) == 96
    w = client.get("/api/v1/wait-or-go", params={"stop_id": "MRTS_VLCY", "route_id": "MRTS_BV", "at": at.isoformat()}).json()
    assert isinstance(w["suggestion"], str)


def test_unknown_ids_404(client):
    assert client.get("/api/v1/occupancy/route/NOPE").status_code == 404
    assert client.get("/api/v1/occupancy/stop/NOPE").status_code == 404


def test_scenarios_listed(client):
    ids = {s["id"] for s in client.get("/api/v1/twin/scenarios").json()}
    assert {"baseline", "rain_heavy", "cricket_match", "metro_disruption", "extra_trips", "custom"} <= ids
