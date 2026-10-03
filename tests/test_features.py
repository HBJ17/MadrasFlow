"""Leakage check: a feature at origin slot t must not change when data after t changes
(except the declared forecast features: timetable, event calendar, weather forecast)."""
import numpy as np
import pandas as pd

from common.config import IST
from predictor.features import FORECAST_FEATURES, build_panel, make_features
from tests.conftest import SIM_START


def test_no_feature_uses_future_data(seeded_db):
    start = pd.Timestamp(SIM_START, tz=IST)
    p = build_panel(start, start + pd.Timedelta(days=2), sources=("twin",))
    X, names = make_features(p)
    t = 96 + 40  # day 2, 10:00
    rng = np.random.default_rng(0)
    p.lf[:, t + 1:] = rng.random(p.lf[:, t + 1:].shape)
    p.board[:, t + 1:] = rng.random(p.board[:, t + 1:].shape) * 50
    X2, _ = make_features(p)
    changed = [n for i, n in enumerate(names) if not np.allclose(X[:, t, i], X2[:, t, i])]
    assert not [n for n in changed if n not in FORECAST_FEATURES], changed


def test_target_is_demand_load_factor(seeded_db):
    start = pd.Timestamp(SIM_START, tz=IST)
    p = build_panel(start, start + pd.Timedelta(days=1), sources=("twin",))
    obs = p.lf[~np.isnan(p.lf)]
    assert obs.min() >= 0 and obs.max() > 0.3
