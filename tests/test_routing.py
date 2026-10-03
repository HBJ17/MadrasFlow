"""Routing sanity: path continuity, options, crowd score ordering, transfer handling."""
import pandas as pd
import pytest

from common.config import IST
from routing.recommend import plan
from tests.conftest import SIM_START

PAIRS = [("6693", "8652"),         # Tambaram West -> Velachery (bus)
         ("MRTS_VLCY", "MRTS_BEACH"),  # MRTS end to end
         ("CMRL_26", "MRTS_TVMR"),     # Airport -> Thiruvanmiyur (metro + bus/MRTS)
         ("6662", "5908"),             # Tambaram East -> Thiruvanmiyur bus stand
         ("CMRL_20", "MRTS_PRGD")]     # Saidapet -> Perungudi


@pytest.fixture(scope="module")
def plans(seeded_db):
    t = pd.Timestamp(SIM_START, tz=IST) + pd.Timedelta(days=1, hours=8, minutes=30)
    from db.database import execute
    from predictor.serve import run_forecast  # baseline forecast rows exist even without a trained LSTM

    run_forecast(t)
    return {pair: plan(*pair, depart_at=t) for pair in PAIRS}


def test_itineraries_returned(plans):
    for pair, p in plans.items():
        assert 1 <= len(p["itineraries"]) <= 4, pair
        labels = {l for it in p["itineraries"] for l in it["labels"]}
        assert {"fastest", "balanced", "least_crowded"} <= labels, (pair, labels)


def test_least_crowded_not_worse_than_fastest(plans):
    for pair, p in plans.items():
        its = p["itineraries"]
        f = next(it for it in its if "fastest" in it["labels"])
        lc = next(it for it in its if "least_crowded" in it["labels"])
        assert lc["crowd_total"] <= f["crowd_total"] + 1e-9, pair
        assert f["total_min"] <= lc["total_min"] + 1e-9, pair


def test_path_continuity(plans):
    for pair, p in plans.items():
        for it in p["itineraries"]:
            rides = [l for l in it["legs"] if l["kind"] == "ride"]
            assert rides[0]["from_stop"] and rides[-1]["to_stop"]
            for a, b in zip(rides, rides[1:]):
                assert pd.Timestamp(b["board_at"]) >= pd.Timestamp(a["alight_at"]), pair
            assert it["transfers"] == len(rides) - 1


def test_prefer_low_crowd_runs(seeded_db):
    t = pd.Timestamp(SIM_START, tz=IST) + pd.Timedelta(days=1, hours=18)
    p = plan("6693", "8652", depart_at=t, prefer_low_crowd=True)
    assert p["itineraries"] and p["prefer_low_crowd"]
