"""Twin invariants: load conservation, capacity, determinism, scenario directions."""
import numpy as np
import pandas as pd

from twin.network import load_network
from twin.simulate import run


def test_load_conservation_and_capacity(seeded_db):
    ev = seeded_db["events"].sort_values(["trip_id", "ts"])
    prev = ev.groupby("trip_id").onboard_load.shift(1).fillna(0)
    assert (ev.onboard_load == prev + ev.boardings - ev.alightings).all()
    assert (ev.onboard_load >= 0).all()
    cap = load_network().routes.set_index("route_id").capacity_total
    assert (ev.onboard_load <= ev.route_id.map(cap)).all()
    assert (ev.groupby("trip_id").onboard_load.last() == 0).all()


def test_all_rows_tagged_twin(seeded_db):
    ev = seeded_db["events"]
    assert (ev.source == "twin").all() and ev.run_id.notna().all()


def test_deterministic_given_seed():
    a, _ = run(start_date="2026-09-15", days=1, seed=9, workers=1, use_calendar=False, run_id="x")
    b, _ = run(start_date="2026-09-15", days=1, seed=9, workers=1, use_calendar=False, run_id="x")
    c, _ = run(start_date="2026-09-15", days=1, seed=10, workers=1, use_calendar=False, run_id="x")
    cols = ["ts", "trip_id", "stop_id", "boardings", "alightings", "onboard_load", "left_behind"]
    pd.testing.assert_frame_equal(a[cols].reset_index(drop=True), b[cols].reset_index(drop=True))
    assert not a[cols].reset_index(drop=True).equals(c[cols].reset_index(drop=True))


def test_extra_trips_lower_load():
    xt = [{"route": "BUS_95", "direction": 0, "start": "07:30", "end": "10:30", "n": 6}]
    base, _ = run(start_date="2026-09-15", days=1, seed=4, workers=1, use_calendar=False)
    more, _ = run(scenario="extra_trips", start_date="2026-09-15", days=1, seed=4, workers=1, use_calendar=False,
                  mods={"extra_trips": xt})
    m = lambda e: e[(e.route_id == "BUS_95") & (e.direction == 0) & e.ts.dt.hour.between(7, 10)]  # noqa: E731
    lf = lambda e: ((e.onboard_load + e.left_behind) / 70).mean()  # noqa: E731
    assert lf(m(more)) < lf(m(base))
    assert m(more).trip_id.nunique() > m(base).trip_id.nunique()
