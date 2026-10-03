"""Window planner: slots, filters, ranking, nearest stop and the /plan/window endpoint."""
import pandas as pd
import pytest

from common.config import IST
from routing import ranking
from routing.window import MAX_PER_SLOT, plan_window
from tests.conftest import SIM_START

PAIR = ("CMRL_26", "MRTS_TVMR")   # Airport -> Thiruvanmiyur: metro, MRTS and bus options


@pytest.fixture(scope="module")
def t830(seeded_db):
    t = pd.Timestamp(SIM_START, tz=IST) + pd.Timedelta(days=1, hours=8, minutes=30)
    from predictor.serve import run_forecast

    run_forecast(t)
    return t


def _rides(it):
    return [l for l in it["legs"] if l["kind"] == "ride"]


def test_slots_follow_the_window(t830):
    p = plan_window(*PAIR, center=t830, window_min=30)
    starts = [pd.Timestamp(s["depart_at"]) for s in p["slots"]]
    assert len(starts) == 5 and starts[2] == t830
    assert all((b - a) == pd.Timedelta(minutes=15) for a, b in zip(starts, starts[1:]))
    assert any(s["itineraries"] for s in p["slots"])
    for s in p["slots"]:
        assert len(s["itineraries"]) <= MAX_PER_SLOT
        assert [it["rank"] for it in s["itineraries"]] == list(range(1, len(s["itineraries"]) + 1))
        for it in s["itineraries"]:
            routes = [l["route_id"] for l in _rides(it)]
            assert len(set(routes)) == len(routes) and it["transfers"] <= 2
            assert pd.Timestamp(_rides(it)[0]["board_at"]) >= pd.Timestamp(s["depart_at"])
            assert it["fare"] >= 0 and all(len(l["path"]) == len(l["levels"]) + 1 for l in _rides(it))
    assert sum(it.get("best_overall", False) for s in p["slots"] for it in s["itineraries"]) == 1


def test_filters(t830):
    no_bus = plan_window(*PAIR, center=t830, filters={"modes": ["mrts", "metro"]})
    assert all(l["mode"] != "bus" for s in no_bus["slots"] for it in s["itineraries"] for l in _rides(it))
    direct = plan_window(*PAIR, center=t830, filters={"max_transfers": 0})
    assert all(it["transfers"] == 0 for s in direct["slots"] for it in s["itineraries"])
    women = plan_window(*PAIR, center=t830, filters={"women": True})
    for s in women["slots"]:
        for it in s["itineraries"]:
            assert all(l["fare"] == 0 for l in _rides(it) if l["mode"] == "bus")
    sf = plan_window(*PAIR, center=t830, filters={"step_free": True})
    assert all(l["mode"] != "mrts" for s in sf["slots"] for it in s["itineraries"] for l in _rides(it))
    cheap = plan_window(*PAIR, center=t830, filters={"max_fare": 20})
    assert all(it["fare"] <= 20 for s in cheap["slots"] for it in s["itineraries"])


def test_ranking_by_single_criterion(t830):
    by_eta = plan_window(*PAIR, center=t830, rank_by=["eta"])
    by_crowd = plan_window(*PAIR, center=t830, rank_by=["crowd"])
    for s in by_eta["slots"]:
        if s["itineraries"]:
            first = pd.Timestamp(s["itineraries"][0]["arrive_at"])
            assert all(first <= pd.Timestamp(it["arrive_at"]) for it in s["itineraries"])
    for s in by_crowd["slots"]:
        if s["itineraries"]:
            lv = [ranking.LEVEL_IX[it["worst_level"]] for it in s["itineraries"]]
            assert lv[0] == min(lv)


def test_ranking_scale_prefers_a_quieter_trip():
    base = {"crowd_score": 0.0, "fare": 20.0, "walk_min": 0.0, "transfers": 0}
    crowded = {**base, "worst_level": "CROWDED", "crowd_score": 8.0, "total_min": 40, "arrive_at": "2026-10-03T09:10:00+05:30"}
    quiet = {**base, "worst_level": "LOW", "total_min": 46, "arrive_at": "2026-10-03T09:16:00+05:30"}
    assert ranking.rank([crowded, quiet], None)[0]["worst_level"] == "LOW"          # 6 min slower, 3 levels quieter
    assert ranking.rank([crowded, quiet], ["eta"])[0]["worst_level"] == "CROWDED"
    assert ranking.criteria_of([]) == ["eta"] and ranking.criteria_of(None) == ["crowd", "eta"]


def test_api_window_and_nearest(t830):
    from fastapi.testclient import TestClient

    from api.main import app

    c = TestClient(app)
    r = c.post("/api/v1/plan/window", json={"from_stop": PAIR[0], "to_stop": PAIR[1], "depart_at": t830.isoformat(),
                                             "window_min": 15, "filters": {"women": True}, "rank_by": ["crowd", "eta"]})
    assert r.status_code == 200 and len(r.json()["slots"]) == 3
    assert c.post("/api/v1/plan/window", json={"from_stop": PAIR[0], "to_stop": PAIR[1], "window_min": 20}).status_code == 422
    near = c.get("/api/v1/stops/nearest", params={"lat": 12.9792, "lon": 80.2205}).json()
    assert near[0]["stop_id"] == "MRTS_VLCY" and near[0]["walk_min"] < 2
    assert c.get("/api/v1/stops/nearest", params={"lat": 13.3, "lon": 79.9}).status_code == 404
