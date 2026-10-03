"""Depot tools: fleet plans, scenario builder, hold-for-train rule and the fleet heatmap API."""
import pandas as pd
import pytest

from common.config import IST, iso
from tests.conftest import SIM_START


def test_buses_to_trips_merges_hours_and_counts_round_trips(seeded_db):
    from twin.fleet import buses_to_trips, round_trip_minutes
    from twin.network import load_network

    net = load_network()
    cyc = round_trip_minutes(net, "BUS_95")
    fleet = [{"route": "BUS_95", "hour": 8, "buses": 2}, {"route": "BUS_95", "hour": 9, "buses": 2},
             {"route": "BUS_51R", "direction": 0, "hour": 18, "buses": 1}]
    trips, s = buses_to_trips(net, fleet)
    t95 = [t for t in trips if t["route"] == "BUS_95"]
    assert {t["direction"] for t in t95} == {0, 1}
    assert all(t["start"] == "08:00" and t["end"] == "10:00" for t in t95)            # 08 and 09 merged
    assert t95[0]["n"] == max(1, round(4 * 60 / cyc))
    assert [t["direction"] for t in trips if t["route"] == "BUS_51R"] == [0]
    assert s["bus_hours"] == 5 and s["by_route"]["BUS_95"]["peak_buses"] == 2


def test_builder_conditions_and_fleet(seeded_db):
    from twin.simulate import run

    sat = SIM_START + pd.Timedelta(days=(5 - SIM_START.weekday()) % 7)
    kw = dict(start_date=sat, days=1, seed=21, workers=1, use_calendar=False)
    wk_ev, wk = run(scenario="builder", mods={"day_type": "weekday"}, **kw)
    we_ev, we = run(scenario="builder", mods={"day_type": "weekend"}, **kw)
    assert wk["boardings_per_day"] > we["boardings_per_day"]          # weekday forced on a Saturday
    cy_ev, _ = run(scenario="builder", mods={"day_type": "weekday", "weather": "cyclone"}, **kw)
    assert not cy_ev.route_id.str.startswith("MRTS").any()
    fl_ev, fl = run(scenario="builder", mods={"day_type": "weekday", "fleet": [{"route": "BUS_95", "hour": 8, "buses": 3}]}, **kw)
    assert fl["per_day"][0]["trips_run"] > wk["per_day"][0]["trips_run"]


def test_hold_for_train_rule(seeded_db):
    from advisory import rules
    from db.database import query

    st = query("SELECT rs.stop_id, s.station_id FROM route_stop rs JOIN stop s ON s.stop_id = rs.stop_id "
               "WHERE rs.route_id = 'BUS_S97' AND rs.direction = 0 ORDER BY rs.seq")
    rail = set(query("SELECT DISTINCT station_id FROM stop WHERE mode IN ('mrts','metro')").station_id)
    i = next(k for k in range(1, len(st) - 1) if st.station_id.iloc[k] in rail)
    now = pd.Timestamp(SIM_START, tz=IST) + pd.Timedelta(hours=8)
    rows = []
    for h in range(1, 7):
        slot = now + pd.Timedelta(minutes=15 * h)
        for k, s in enumerate(st.stop_id):
            lf = 0.95 if (k == i and 2 <= h <= 4) else 0.3
            rows.append({"route_id": "BUS_S97", "direction": 0, "stop_id": s, "slot": slot, "pred_lf": lf, "data_source": "twin"})
    out = rules.hold_for_train(pd.DataFrame(rows), now, {"BUS_S97": "Velachery"})
    assert len(out) == 1 and out[0]["kind"] == "hold_for_train" and out[0]["depot"] == "Velachery"
    assert out[0]["slot_end"] == iso(now + pd.Timedelta(minutes=75))
    flat = pd.DataFrame([{**r, "pred_lf": 0.3} for r in rows])
    assert rules.hold_for_train(flat, now, {}) == []


@pytest.fixture(scope="module")
def client(seeded_db):
    from fastapi.testclient import TestClient

    from api.deps import clear_caches
    from api.main import app
    from predictor.serve import run_forecast

    run_forecast(pd.Timestamp(SIM_START, tz=IST) + pd.Timedelta(days=1, hours=8))
    clear_caches()
    return TestClient(app)


def test_fleet_heatmap_api(client):
    o = client.get("/api/v1/fleet/heatmap").json()
    assert len(o["slots"]) == 12 and o["rows"] and o["data_source"] == "twin"
    assert all(len(r["cells"]) == 12 for r in o["rows"])
    s = client.get("/api/v1/fleet/heatmap/BUS_95", params={"view": "stops"}).json()
    n_stops = next(r["stops"] for r in client.get("/api/v1/routes").json() if r["route_id"] == "BUS_95")   # direction 0
    assert len(s["rows"]) == n_stops and s["route"] == "95"
    b = client.get("/api/v1/fleet/heatmap/BUS_95", params={"view": "buses"}).json()
    assert len(b["stops"]) == len(s["rows"]) and all(len(r["cells"]) == len(b["stops"]) for r in b["rows"])
    assert client.get("/api/v1/fleet/heatmap/NOPE").status_code == 404


def test_builder_plan_validation(client):
    assert client.post("/api/v1/twin/run", json={"scenario": "builder", "mods": {}}).status_code == 400
    assert client.post("/api/v1/twin/run", json={"scenario": "builder", "mods": {"weather": "snow"}}).status_code == 422
    assert client.post("/api/v1/twin/run", json={"scenario": "builder", "mods": {"fleet": [{"route": "BUS_95", "hour": 2, "buses": 1}]}}).status_code == 422
