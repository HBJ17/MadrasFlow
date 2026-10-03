"""Baselines (section 7.3).

B0: same slot one week earlier (filled value: the level of the last vehicle before that slot);
    fallback when the week-ago value is missing: mean of the same slot on same day-type days.
B1: Prophet, one model per (route_id, direction) on the route-mean load factor, with daily and
    weekly seasonality, Tamil Nadu holidays, and precipitation + event flag as extra regressors.
    Stop-level forecasts = route forecast x the stop's share profile (slot-of-day, weekday/weekend)
    learned on the training period.
"""
from __future__ import annotations

import logging
import pickle
import warnings

import numpy as np
import pandas as pd

from common.config import MODELS_DIR
from predictor.features import SLOTS_PER_DAY, WEEK, Panel, ffill_rows

logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)


def b0_predict(p: Panel, origins: np.ndarray, horizons: np.ndarray) -> np.ndarray:
    """Same-time-last-week. Returns S x len(origins) x len(horizons)."""
    lf_f = ffill_rows(p.lf)
    tgt = origins[:, None] + horizons[None, :] - WEEK
    out = lf_f[:, np.clip(tgt, 0, None)]
    # fallback for the first week: same slot-of-day mean over available history of the same day type
    bad = tgt < 0
    if bad.any():
        wk = p.exo.is_weekend.values
        for j, (o, h) in enumerate(zip(*np.nonzero(bad))):
            t = origins[o] + horizons[h]
            same = np.arange(t % SLOTS_PER_DAY, origins[o] + 1, SLOTS_PER_DAY)
            same = same[wk[same] == wk[t]] if len(same) else same
            out[:, o, h] = lf_f[:, same].mean(axis=1) if len(same) else 0.0
    return out


class ProphetModel:
    def __init__(self):
        self.models = {}       # (route, dir) -> fitted Prophet
        self.share = {}        # series idx -> array[2, 96] (weekday/weekend) of stop / route-mean ratio
        self.groups = None

    @staticmethod
    def _frame(times, y=None, exo=None, ev=None):
        df = pd.DataFrame({"ds": times.tz_localize(None)})
        if y is not None:
            df["y"] = y
        df["precip"] = exo.precip.values
        df["event_flag"] = ev
        return df

    def fit(self, p: Panel, t_end: int, holidays: pd.DataFrame | None = None):
        from prophet import Prophet

        lf_f = ffill_rows(p.lf)
        S = len(p.series)
        self.groups = p.series.groupby(["route_id", "direction"]).indices
        wk = p.exo.is_weekend.values[:t_end].astype(int)
        slot = np.arange(t_end) % SLOTS_PER_DAY
        evr = p.ev["event_active"]
        for key, idx in self.groups.items():
            y = lf_f[idx, :t_end].mean(axis=0)
            ev = evr[idx, :t_end].max(axis=0)
            m = Prophet(daily_seasonality=False, weekly_seasonality=False, yearly_seasonality=False,
                        holidays=holidays, interval_width=0.8, changepoint_prior_scale=0.02)
            m.add_seasonality("daily", period=1, fourier_order=20)
            m.add_seasonality("weekly", period=7, fourier_order=4)
            m.add_regressor("precip")
            m.add_regressor("event_flag")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                m.fit(self._frame(p.times[:t_end], y, p.exo.iloc[:t_end], ev))
            self.models[key] = m
            denom = np.maximum(y, 1e-3)
            for s in idx:
                r = lf_f[s, :t_end] / denom
                sh = np.ones((2, SLOTS_PER_DAY))
                for w in (0, 1):
                    for k in range(SLOTS_PER_DAY):
                        sel = (wk == w) & (slot == k) & (y > 0.01)
                        if sel.any():
                            sh[w, k] = np.clip(np.median(r[sel]), 0, 5)
                self.share[s] = sh
        return self

    def predict_slots(self, p: Panel, t_idx: np.ndarray):
        """q50/lo/hi for every series at panel slots t_idx. Returns 3 arrays S x len(t_idx)."""
        S = len(p.series)
        q50 = np.zeros((S, len(t_idx)), np.float32)
        lo, hi = q50.copy(), q50.copy()
        times = p.times[t_idx]
        wk = p.exo.is_weekend.values[t_idx].astype(int)
        slot = t_idx % SLOTS_PER_DAY if p.times[0].hour == 0 and p.times[0].minute == 0 else (
            (times.hour * 4 + times.minute // 15).values)
        evr = p.ev["event_active"]
        for key, idx in self.groups.items():
            m = self.models[key]
            f = m.predict(self._frame(times, None, p.exo.iloc[t_idx], evr[idx][:, t_idx].max(axis=0)))
            for s in idx:
                sh = self.share[s][wk, slot]
                q50[s] = np.clip(f.yhat.values * sh, 0, 2.0)
                lo[s] = np.clip(f.yhat_lower.values * sh, 0, 2.0)
                hi[s] = np.clip(f.yhat_upper.values * sh, 0, 2.0)
        return q50, lo, hi

    def save(self, path=None):
        path = path or MODELS_DIR / "prophet_v1.pkl"
        MODELS_DIR.mkdir(exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"models": self.models, "share": self.share, "groups": self.groups}, f)

    @classmethod
    def load(cls, path=None):
        path = path or MODELS_DIR / "prophet_v1.pkl"
        with open(path, "rb") as f:
            d = pickle.load(f)
        m = cls()
        m.models, m.share, m.groups = d["models"], d["share"], d["groups"]
        return m


def tn_holidays(p: Panel) -> pd.DataFrame | None:
    from db.database import query

    h = query("SELECT date, note FROM calendar_day WHERE is_holiday = 1")
    if not len(h):
        return None
    return pd.DataFrame({"holiday": "tn_holiday", "ds": pd.to_datetime(h.date), "lower_window": 0, "upper_window": 0})
