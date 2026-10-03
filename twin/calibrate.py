"""Calibrate the twin to published totals (section 6).

    python -m twin.calibrate [--trials 14]

Free parameters: base_mode (per-mode production scale), beta (gravity), peak_width_scale.
Each candidate runs 7 simulated weekdays + 2 weekend days (+ 1 event day), with calendar effects
(weather, holidays, events) switched off so the shape is fitted on 'normal' days.

Objective: weighted sum of squared relative errors on
  (a) daily boardings per mode vs config/calibration_targets.yaml,
  (b) weekday/weekend ratio,
  (c) peak-hour share (08-10 + 17-20) vs the middle of the target band,
  (d) event-day multiplier (cricket_match day vs a baseline weekday).
Stage A fits base_mode by proportional updates; stage B runs Nelder-Mead on (beta,
peak_width_scale); stage A runs again at the end. Writes config/demand_fitted.yaml.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import yaml
from scipy.optimize import minimize

from common.config import CONFIG_DIR, load_yaml
from twin.simulate import run

WEEKDAY0 = date(2026, 9, 14)   # a Monday; 7 weekdays from here (calendar effects are off)
WEIGHTS = {"total": 1.0, "ratio": 0.5, "peak": 1.0, "event": 0.5}


def service_date(ev: pd.DataFrame) -> pd.Series:
    """Operating day of each event: trips that finish after midnight belong to the previous day."""
    return (ev.ts - pd.Timedelta(hours=3)).dt.date


def targets():
    t = load_yaml("calibration_targets.yaml")["corridor"]
    return {"bus": t["bus_daily_boardings"], "metro": t["metro_daily_boardings"], "mrts": t["mrts_daily_boardings"]}, t


def _weekdays(n=7):
    out, d = [], WEEKDAY0
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def evaluate(params: dict, seed: int = 11, quick: bool = False) -> dict:
    """Run the calibration day set for one parameter vector and return the metrics."""
    tmode, t = targets()
    wd = _weekdays(2 if quick else 7)
    ev_wd, s_wd = run(config=params, start_date=wd[0], days=(wd[-1] - wd[0]).days + 1, seed=seed, use_calendar=False)
    ev_wd = ev_wd[pd.to_datetime(service_date(ev_wd)).dt.weekday < 5]
    n_wd = service_date(ev_wd).nunique()
    sat = WEEKDAY0 + timedelta(days=(5 - WEEKDAY0.weekday()) % 7)
    ev_we, _ = run(config=params, start_date=sat, days=1 if quick else 2, seed=seed + 1, use_calendar=False)
    from twin.network import load_network

    modes = load_network().routes.set_index("route_id")["mode"]
    by_mode = (ev_wd.groupby(ev_wd.route_id.map(modes)).boardings.sum() / n_wd).to_dict()
    wd_total = ev_wd.boardings.sum() / n_wd
    we_total = ev_we.boardings.sum() / service_date(ev_we).nunique()
    h = ev_wd.ts.dt.hour
    peak_share = ev_wd.boardings[(h.between(8, 9)) | (h.between(17, 19))].sum() / ev_wd.boardings.sum()
    out = {"by_mode": {k: round(float(v)) for k, v in by_mode.items()}, "weekday_total": round(float(wd_total)),
           "weekend_total": round(float(we_total)), "ratio": float(wd_total / max(1, we_total)),
           "peak_share": float(peak_share), "unmet_per_day": s_wd["unmet_demand"] / n_wd,
           "crowded_vs_per_day": s_wd["crowded_vehicle_stops"] / n_wd}
    if not quick:
        ev_ev, _ = run(config=params, scenario="cricket_match", start_date=wd[0], days=1, seed=seed, use_calendar=False)
        base_day = ev_wd[service_date(ev_wd) == wd[0]].boardings.sum()
        out["event_ratio"] = float(ev_ev.boardings.sum() / max(1, base_day))
    return out


def objective(m: dict) -> float:
    tmode, t = targets()
    err = sum(((m["by_mode"].get(k, 0) - v) / v) ** 2 for k, v in tmode.items()) / len(tmode)
    ratio_err = ((m["ratio"] - t["weekday_weekend_ratio"]) / t["weekday_weekend_ratio"]) ** 2
    lo, hi = t["peak_hour_share"]
    peak_err = ((m["peak_share"] - (lo + hi) / 2) / ((lo + hi) / 2)) ** 2
    ev_err = ((m.get("event_ratio", t["event_day_ratio"]) - t["event_day_ratio"]) / t["event_day_ratio"]) ** 2
    return WEIGHTS["total"] * err + WEIGHTS["ratio"] * ratio_err + WEIGHTS["peak"] * peak_err + WEIGHTS["event"] * ev_err


def fit_base_mode(params: dict, iters: int = 5, tol: float = 0.03, log=print) -> dict:
    tmode, _ = targets()
    for i in range(iters):
        m = evaluate(params, quick=True)
        rel = {k: m["by_mode"].get(k, 1) / v for k, v in tmode.items()}
        log(f"  [base_mode iter {i}] {json.dumps(params['base_mode'])} -> by_mode {m['by_mode']} rel "
            f"{ {k: round(v, 3) for k, v in rel.items()} }")
        if all(abs(r - 1) < tol for r in rel.values()):
            break
        # damped proportional update; saturated modes respond less than linearly, so overshoot a bit
        params["base_mode"] = {k: float(params["base_mode"][k] * (1 / rel[k]) ** 1.1) for k in tmode}
    return params


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=14, help="Nelder-Mead evaluations in stage B")
    ap.add_argument("--stage-a-only", action="store_true",
                    help="keep the fitted beta/peak width from demand_fitted.yaml; refit base_mode only")
    a = ap.parse_args()
    dcfg = load_yaml("demand.yaml")
    params = {"base_mode": dict(dcfg["base_mode"]), "beta_per_km": dcfg["beta_per_km"],
              "peak_width_scale": dcfg.get("peak_width_scale", 1.0)}
    log_lines = []

    def log(s):
        print(s, flush=True)
        log_lines.append(s)

    if a.stage_a_only:
        prev = yaml.safe_load((CONFIG_DIR / "demand_fitted.yaml").read_text(encoding="utf8"))["params"]
        params.update(prev)
        log(f"Stage A only, starting from {json.dumps(params)}")
        a.trials = 0

    log("Stage A: base_mode")
    params = fit_base_mode(params, log=log)
    if a.trials == 0:
        return _finish(params, log, log_lines)

    log("Stage B: Nelder-Mead on (beta_per_km, peak_width_scale)")
    cache = {}

    def f(x):
        beta, width = float(np.clip(x[0], 0.02, 0.4)), float(np.clip(x[1], 0.6, 1.6))
        p = {**params, "beta_per_km": beta, "peak_width_scale": width}
        m = evaluate(p)
        val = objective(m)
        cache[(round(beta, 4), round(width, 4))] = (val, m)
        log(f"  beta={beta:.3f} width={width:.2f} obj={val:.4f} peak={m['peak_share']:.3f} ratio={m['ratio']:.2f} "
            f"event={m.get('event_ratio', 0):.2f} by_mode={m['by_mode']}")
        return val

    res = minimize(f, x0=[params["beta_per_km"], params["peak_width_scale"]], method="Nelder-Mead",
                   options={"maxfev": a.trials, "xatol": 0.01, "fatol": 0.002,
                            "initial_simplex": [[params["beta_per_km"], params["peak_width_scale"]],
                                                [params["beta_per_km"] * 1.5, params["peak_width_scale"]],
                                                [params["beta_per_km"], params["peak_width_scale"] * 0.8]]})
    params["beta_per_km"] = float(np.clip(res.x[0], 0.02, 0.4))
    params["peak_width_scale"] = float(np.clip(res.x[1], 0.6, 1.6))

    log("Stage A (final): base_mode with fitted shape parameters")
    params = fit_base_mode(params, log=log)
    _finish(params, log, log_lines)


def _finish(params, log, log_lines):
    final = evaluate(params)
    obj = objective(final)
    log(f"Final objective {obj:.4f}: {json.dumps(final)}")

    out = {"fitted_at": datetime.now().isoformat(timespec="seconds"), "objective": round(obj, 5),
           "metrics": final, "params": params,
           "note": "Generated by twin/calibrate.py. Overrides demand.yaml keys of the same name."}
    with open(CONFIG_DIR / "demand_fitted.yaml", "w", encoding="utf8") as fh:
        yaml.safe_dump(json.loads(json.dumps(out)), fh, sort_keys=False)
    from common.config import REPORTS_DIR

    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "calibration_log.txt").write_text("\n".join(log_lines), encoding="utf8")
    print("wrote config/demand_fitted.yaml")


if __name__ == "__main__":
    main()
