"""Demand totals track the calibration targets."""
import pandas as pd
import yaml

from common.config import CONFIG_DIR, load_yaml
from twin.network import load_network
from twin.simulate import _holidays


def test_weekday_totals_near_targets(seeded_db):
    ev = seeded_db["events"]
    modes = load_network().routes.set_index("route_id")["mode"]
    day = (ev.ts - pd.Timedelta(hours=3)).dt.date
    # holidays run as holiday days even with use_calendar=False (the fixture uses the last 2 days)
    wk = ev[(pd.to_datetime(day).dt.weekday < 5) & ~day.isin(set(_holidays()))]
    if wk.empty:
        return
    nd = day[wk.index].nunique()
    per_mode = wk.groupby(wk.route_id.map(modes)).boardings.sum() / nd
    t = load_yaml("calibration_targets.yaml")["corridor"]
    for m, k in (("bus", "bus_daily_boardings"), ("metro", "metro_daily_boardings"), ("mrts", "mrts_daily_boardings")):
        assert abs(per_mode[m] / t[k] - 1) < 0.15, (m, per_mode[m], t[k])


def test_fitted_parameters_recorded():
    p = CONFIG_DIR / "demand_fitted.yaml"
    assert p.exists(), "run python -m twin.calibrate"
    d = yaml.safe_load(p.read_text())
    assert d["objective"] < 0.05 and "fitted_at" in d
