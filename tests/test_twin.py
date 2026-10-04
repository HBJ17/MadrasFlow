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
    lf = lambda e: ((e.onboard_load + e.left_behind) / 83).mean()  # noqa: E731
    assert lf(m(more)) < lf(m(base))
    assert m(more).trip_id.nunique() > m(base).trip_id.nunique()


def test_cyclone_halts_mrts_and_thins_buses():
    base, _ = run(start_date="2026-09-15", days=1, seed=4, workers=1, use_calendar=False)
    cy, _ = run(scenario="cyclone", start_date="2026-09-15", days=1, seed=4, workers=1, use_calendar=False)
    assert not cy.route_id.str.startswith("MRTS").any()
    bus_trips = lambda e: e[e.route_id.str.startswith("BUS")].trip_id.nunique()  # noqa: E731
    assert bus_trips(cy) < 0.85 * bus_trips(base)


def _day(**mods):
    scen = "extra_trips" if mods else "baseline"
    return run(scenario=scen, start_date="2026-09-15", days=1, seed=4, workers=1, use_calendar=False, mods=mods or None)[0]


def test_short_turn_trips_end_at_the_turn():
    ev = _day(extra_trips=[{"route": "BUS_95", "direction": 0, "start": "08:00", "end": "10:00", "n": 3, "turn_idx": 8}])
    stops = load_network().route_stops("BUS_95", 0).stop_id.tolist()
    st = ev[(ev.route_id == "BUS_95") & ev.trip_id.str.contains("x")]
    assert st.trip_id.nunique() == 3
    assert set(st.stop_id) <= set(stops[:9])                       # never runs past the turn
    assert (st.sort_values("ts").groupby("trip_id").onboard_load.last() == 0).all()   # everyone off at the turn


def test_remove_trips_and_hold():
    base = _day()
    fewer = _day(remove_trips=[{"route": "BUS_51R", "start": "08:00", "end": "10:00", "n": 2}])
    trips = lambda e: e[e.route_id == "BUS_51R"].groupby("direction").trip_id.nunique()  # noqa: E731
    assert (trips(base) - trips(fewer) == 2).all()
    stop = load_network().route_stops("BUS_S97", 0).stop_id.iloc[5]
    held = _day(holds=[{"route": "BUS_S97", "direction": 0, "stop_id": stop, "start": "08:00", "end": "10:00", "min": 2}])
    at = lambda e: e[(e.route_id == "BUS_S97") & (e.stop_id == stop) & e.ts.dt.hour.between(8, 9)].set_index("trip_id").ts  # noqa: E731
    delay = (at(held) - at(base)).dropna().dt.total_seconds() / 60
    assert len(delay) and delay.mean() >= 1.0      # 2 min hold; run times share one random stream
