"""Scheduled forecast job (section 7.6): read the latest events, build features, run the models,
apply live correction, write rows to `forecast`. The API only reads these rows; it never runs a
model inside a request.

    python -m predictor.serve            # one run at the current (demo) clock
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from common import clock
from common.config import IST, MODELS_DIR, crowd_level, floor_15, iso, load_yaml
from db.database import engine, execute, query
from predictor import live_correction
from predictor.baseline import ProphetModel, b0_predict
from predictor.features import SLOTS_PER_DAY, build_panel, make_features
from predictor.lstm import HORIZON, load as load_lstm, predict as lstm_predict

_MODELS: dict = {}


def _models():
    if not _MODELS:
        if (MODELS_DIR / "lstm_v1.pt").exists():
            _MODELS["lstm"] = load_lstm()
        if (MODELS_DIR / "prophet_v1.pkl").exists():
            _MODELS["prophet"] = ProphetModel.load()
    return _MODELS


def _source_flag(srcs: set) -> str:
    srcs = {s for s in srcs if s}
    if not srcs:
        return "none"
    if "twin" in srcs and srcs - {"twin"}:
        return "mixed"
    return "twin" if srcs == {"twin"} else "camera"


def run_forecast(now: pd.Timestamp | None = None) -> dict:
    t0 = time.time()
    cfg = load_yaml("predictor.yaml")["serve"]
    now = pd.Timestamp(now or clock.now()).tz_convert(IST)
    origin = pd.Timestamp(floor_15(now.to_pydatetime())) - pd.Timedelta(minutes=15)  # last complete slot
    start = (origin - pd.Timedelta(days=cfg["history_days"])).normalize()
    end = origin + pd.Timedelta(minutes=15 * (HORIZON + 1))
    p = build_panel(start, end)
    # nothing after `now` may leak in: build_panel reads events by slot; drop slots after the origin
    t_o = p.times.get_loc(origin)
    p.lf[:, t_o + 1:] = np.nan
    p.board[:, t_o + 1:] = 0
    # scheduled supply for future slots: the timetable repeats weekly, so use the same slots last week
    fut = np.arange(t_o + 1, p.supply.shape[1])
    src = fut - 7 * SLOTS_PER_DAY
    p.supply[:, fut[src >= 0]] = p.supply[:, src[src >= 0]]
    X, names = make_features(p)
    S = len(p.series)
    target_idx = t_o + 1 + np.arange(HORIZON)
    slots = p.times[target_idx]
    cap = p.series.capacity.values.astype(float)

    srcs = query("SELECT route_id, source FROM event WHERE ts >= :a AND ts <= :b AND route_id IS NOT NULL GROUP BY route_id, source",
                 {"a": iso(now - pd.Timedelta(hours=6)), "b": iso(now)})
    route_src = srcs.groupby("route_id").source.agg(set).to_dict()

    models = _models()
    out = []
    base = pd.DataFrame({"route_id": np.repeat(p.series.route_id.values, HORIZON),
                         "direction": np.repeat(p.series.direction.values, HORIZON),
                         "stop_id": np.repeat(p.series.stop_id.values, HORIZON),
                         "seq": np.repeat(p.series.seq.values, HORIZON),
                         "cap": np.repeat(cap, HORIZON),
                         "target_slot": np.tile(slots, S),
                         "horizon": np.tile(np.arange(1, HORIZON + 1), S)})
    if "lstm" in models and "lstm" in cfg["models"]:
        m, ck = models["lstm"]
        if ck["n_stops"] == S and ck["features"] == names:
            q, b = lstm_predict(m, ck, X, p.series, np.arange(S), np.full(S, t_o))
            f = base.copy()
            f["model"] = "lstm"
            f["pred_lf"] = np.clip(q[..., 1].ravel(), 0, 2.0)
            f["lo"] = np.clip(q[..., 0].ravel(), 0, 2.0)
            f["hi"] = np.clip(q[..., 2].ravel(), 0, 2.0)
            f["pred_boardings"] = b.ravel()
            out.append(f)
    if "baseline" in cfg["models"]:
        b0 = b0_predict(p, np.array([t_o]), np.arange(1, HORIZON + 1))[:, 0, :]
        f = base.copy()
        f["model"] = "baseline"
        f["pred_lf"] = b0.ravel()
        f["lo"] = f["hi"] = np.nan
        wk = p.board[:, np.clip(target_idx - 7 * SLOTS_PER_DAY, 0, None)]
        f["pred_boardings"] = wk.ravel()
        out.append(f)
    if "prophet" in models and "prophet" in cfg["models"]:
        q50, lo, hi = models["prophet"].predict_slots(p, target_idx)
        f = base.copy()
        f["model"] = "prophet"
        f["pred_lf"], f["lo"], f["hi"] = q50.ravel(), lo.ravel(), hi.ravel()
        f["pred_boardings"] = np.nan
        out.append(f)
    fc = pd.concat(out, ignore_index=True)

    # live correction from observations in the current (incomplete) slot
    obs = query("""SELECT e.route_id, e.direction, e.stop_id, rs.seq, e.ts, e.source,
                          (e.onboard_load + COALESCE(e.left_behind, 0)) * 1.0 / r.capacity_total AS lf
                   FROM event e JOIN route r ON r.route_id = e.route_id
                   JOIN route_stop rs ON rs.route_id = e.route_id AND rs.direction = e.direction AND rs.stop_id = e.stop_id
                   WHERE e.ts > :a AND e.ts <= :b AND e.onboard_load IS NOT NULL""",
                {"a": iso(now - pd.Timedelta(minutes=30)), "b": iso(now)})
    obs["ts"] = pd.to_datetime(obs.ts, utc=True).dt.tz_convert(IST)
    last_seq = p.series.groupby(["route_id", "direction"]).seq.max().to_dict()
    fc = pd.concat([live_correction.apply(g, obs, now, last_seq) for _, g in fc.groupby("model")], ignore_index=True)

    made_at = iso(now.floor("min"))
    fc["made_at"] = made_at
    fc["target_slot"] = fc.target_slot.map(iso)
    fc["pred_load"] = fc.pred_lf * fc.cap
    fc["level"] = fc.pred_lf.map(crowd_level)
    fc["data_source"] = fc.route_id.map(lambda r: _source_flag(route_src.get(r, set())))
    cols = ["made_at", "target_slot", "stop_id", "route_id", "direction", "model", "pred_load", "pred_boardings",
            "level", "lo", "hi", "pred_lf", "stale", "data_source", "horizon"]
    execute("DELETE FROM forecast WHERE made_at = :m", {"m": made_at})
    fc[cols].to_sql("forecast", engine(), if_exists="append", index=False, chunksize=5000)
    # retention: keep recent runs, plus 1-hour-ahead rows for the accuracy panel
    execute("DELETE FROM forecast WHERE made_at < :a AND NOT (horizon = 4 AND made_at >= :b)",
            {"a": iso(now - pd.Timedelta(hours=cfg["keep_hours"])), "b": iso(now - pd.Timedelta(hours=cfg["keep_eval_hours"]))})
    return {"made_at": made_at, "origin": iso(origin), "rows": len(fc), "models": sorted(fc.model.unique()),
            "elapsed_s": round(time.time() - t0, 2)}


if __name__ == "__main__":
    print(json.dumps(run_forecast(), indent=1))
