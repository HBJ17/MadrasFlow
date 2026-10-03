"""Train B0 / Prophet / LSTM on the DB and evaluate on the held-out period (section 7.5).

    python -m predictor.evaluate            # train + evaluate, writes reports/forecast_eval.md
    python -m predictor.evaluate --no-train # evaluate saved models

Time-based split over the data in the DB: first 60 days train (the first 7 only warm up lags),
next 15 validation (early stopping), last 15 test. Never random.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

import numpy as np
import pandas as pd

from common.config import IST, LEVELS, MODELS_DIR, REPORTS_DIR, crowd_level
from db.database import query
from predictor import lstm as L
from predictor.baseline import ProphetModel, b0_predict, tn_holidays
from predictor.features import SLOTS_PER_DAY, WEEK, build_panel, make_features

HORIZONS = {"15 min": 1, "1 h": 4, "3 h": 12}


def data_range():
    r = query("SELECT MIN(slot_15) a, MAX(slot_15) b FROM event WHERE source='twin'")
    a = pd.Timestamp(r.a.iloc[0]).tz_convert(IST).normalize()
    # trips finishing after midnight belong to the previous service day
    b = (pd.Timestamp(r.b.iloc[0]).tz_convert(IST) - pd.Timedelta(hours=3)).normalize() + pd.Timedelta(days=1)
    return a, b


def levels(x):
    x = np.asarray(x, dtype=float)
    out = np.full(x.shape, 0)
    out[x >= 0.40] = 1
    out[x >= 0.75] = 2
    out[x >= 1.00 - 1e-9] = 3
    return out


def macro_f1(cm):
    f1 = []
    for k in range(len(cm)):
        tp = cm[k, k]
        p = tp / max(cm[:, k].sum(), 1)
        r = tp / max(cm[k, :].sum(), 1)
        f1.append(0 if p + r == 0 else 2 * p * r / (p + r))
    return float(np.mean(f1))


def day_kinds(p) -> dict:
    """normal | rain | event per date, from context tables only."""
    w = p.exo.precip.groupby(p.times.date).sum() / 4.0  # hourly values repeated per 15-min slot
    ev = query("SELECT start_ts, end_ts FROM city_event WHERE expected_attendance > 0")
    ev_days = {pd.Timestamp(s).date() for s in ev.start_ts}
    out = {}
    for d, mm in w.items():
        out[d] = "event" if d in ev_days else ("rain" if mm >= 5 else "normal")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-train", action="store_true")
    ap.add_argument("--train-only", action="store_true")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--samples", type=int, default=120_000)
    a = ap.parse_args(argv)
    log_lines = []

    def log(s):
        print(s, flush=True)
        log_lines.append(str(s))

    start, end = data_range()
    n_days = (end - start).days
    log(f"data: {start.date()} .. {end.date()} ({n_days} days)")
    p = build_panel(start, end, sources=("twin",))
    X, names = make_features(p)
    log(f"panel: {len(p.series)} series x {len(p.times)} slots x {len(names)} features")
    T = len(p.times)
    if n_days >= 10:
        test_days = val_days = 15 if n_days >= 45 else max(2, n_days // 6)
        t_val_end = (n_days - test_days) * SLOTS_PER_DAY
        t_train_end = t_val_end - val_days * SLOTS_PER_DAY
    else:  # tiny datasets (smoke test): split by slots 60/20/20
        t_train_end, t_val_end = int(T * 0.6), int(T * 0.8)
    split = {"train": [str(p.times[0].date()), str(p.times[t_train_end - 1].date())],
             "val": [str(p.times[t_train_end].date()), str(p.times[t_val_end - 1].date())],
             "test": [str(p.times[t_val_end].date()), str(p.times[-1].date())]}
    log(f"split: {split}")

    if not a.no_train:
        model, mean, std, routes, best = L.train(X, p.lf, p.board, p.series, p.times, t_train_end, t_val_end,
                                                 epochs=a.epochs, samples_per_epoch=a.samples, log=log)
        L.save(model, mean, std, routes, names, p.series, meta={"trained_at": datetime.now().isoformat(),
                                                               "split": split, "best_val_mae": best,
                                                               "data_source": "twin"})
        log("Fitting Prophet per (route, direction)...")
        pm = ProphetModel().fit(p, t_val_end, tn_holidays(p))
        pm.save()
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (REPORTS_DIR / "training_log.txt").write_text("\n".join(log_lines), encoding="utf8")
    if a.train_only:
        return 0
    model, ck = L.load()
    pm = ProphetModel.load()

    # ---------------- test predictions
    s_idx, t_idx = L.origins_for(p.times, t_val_end, T, p.lf)
    if len(s_idx) == 0:  # e.g. the smoke test's half-elapsed single day
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (REPORTS_DIR / "forecast_eval.md").write_text(
            f"# Forecast evaluation\n\nNo test windows with observed targets in {split['test']}: dataset too small "
            "to evaluate. Models were trained and saved.\n", encoding="utf8")
        log("no test windows: evaluation skipped")
        return 1
    q, bpred = L.predict(model, ck, X, p.series, s_idx, t_idx)
    hz = np.array(list(HORIZONS.values()))
    origins_u = np.unique(t_idx)
    b0 = b0_predict(p, origins_u, hz)                       # S x O x H
    o_pos = np.searchsorted(origins_u, t_idx)
    test_slots = np.arange(t_val_end, T)
    pq50, plo, phi = pm.predict_slots(p, test_slots)
    cap = p.series.capacity.values
    kinds = day_kinds(p)
    rows = []
    for name, h in HORIZONS.items():
        tt = t_idx + h
        ok = tt < T
        s, o, tt, hi_ = s_idx[ok], o_pos[ok], tt[ok], h - 1
        y = p.lf[s, tt]
        m = ~np.isnan(y)
        s, o, tt, y = s[m], o[m], tt[m], y[m]
        qq = q[ok][m]
        pb = bpred[ok][m][:, hi_]
        hj = list(hz).index(h)
        pr = tt - t_val_end
        hrs = p.times.hour.values[tt]
        df = pd.DataFrame({
            "horizon": name, "s": s, "y": y, "board": p.board[s, tt],
            "lstm": qq[:, hi_, 1], "lstm_lo": qq[:, hi_, 0], "lstm_hi": qq[:, hi_, 2], "lstm_board": pb,
            "b0": b0[s, o, hj], "b0_board": p.board[s, np.clip(tt - WEEK, 0, None)],
            "prophet": pq50[s, pr], "prophet_lo": plo[s, pr], "prophet_hi": phi[s, pr],
            "peak": ((hrs >= 8) & (hrs < 10)) | ((hrs >= 17) & (hrs < 20)),
            "kind": [kinds[d] for d in p.times.date[tt]], "mode": p.series["mode"].values[s],
        })
        rows.append(df)
    R = pd.concat(rows, ignore_index=True)

    def metrics(d: pd.DataFrame, model: str) -> dict:
        e = d[model] - d.y
        out = {"n": len(d), "MAE_LF": e.abs().mean(), "RMSE_LF": np.sqrt((e ** 2).mean())}
        if f"{model}_board" in d:
            eb = d[f"{model}_board"] - d.board
            out.update({"MAE_board": eb.abs().mean(), "RMSE_board": np.sqrt((eb ** 2).mean())})
        yl, pl = levels(d.y), levels(d[model])
        cm = np.zeros((4, 4), int)
        np.add.at(cm, (yl, pl), 1)
        out.update({"level_acc": (yl == pl).mean(), "macro_F1": macro_f1(cm),
                    "CROWDED_recall": cm[3, 3] / max(cm[3].sum(), 1), "CROWDED_precision": cm[3, 3] / max(cm[:, 3].sum(), 1),
                    "cm": cm})
        if f"{model}_lo" in d:
            out["coverage_80"] = ((d.y >= d[f"{model}_lo"]) & (d.y <= d[f"{model}_hi"])).mean()
        return out

    models = ["b0", "prophet", "lstm"]
    table = []
    for (hname, seg), d in [((h, "all"), R[R.horizon == h]) for h in HORIZONS] + \
                           [((h, "peak"), R[(R.horizon == h) & R.peak]) for h in HORIZONS] + \
                           [((h, "off-peak"), R[(R.horizon == h) & ~R.peak]) for h in HORIZONS] + \
                           [((h, k), R[(R.horizon == h) & (R.kind == k)]) for h in ("1 h",) for k in ("normal", "rain", "event")]:
        if not len(d):
            continue
        for mdl in models:
            mm = metrics(d, mdl)
            table.append({"horizon": hname, "segment": seg, "model": mdl, **{k: v for k, v in mm.items() if k != "cm"}})
    T_ = pd.DataFrame(table)

    def get(h, seg, mdl, col):
        x = T_[(T_.horizon == h) & (T_.segment == seg) & (T_.model == mdl)]
        return float(x[col].iloc[0]) if len(x) else np.nan

    acc_lstm, acc_b0 = get("1 h", "peak", "lstm", "MAE_LF"), get("1 h", "peak", "b0", "MAE_LF")
    passed = acc_lstm < acc_b0
    cm_l = metrics(R[R.horizon == "1 h"], "lstm")["cm"]

    # ---------------- report
    def fmt(v, pct=False):
        if isinstance(v, (int, np.integer)):
            return f"{v:,}"
        return "-" if pd.isna(v) else (f"{v:.1%}" if pct else f"{v:.4f}")

    L_ = ["# Forecast evaluation",
          "",
          f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python -m predictor.evaluate` on the held-out test period.",
          "",
          "> **Results are on twin (simulated) data.** They show how well the models learn the simulator and that "
          "the pipeline works end to end, not real-world accuracy. Real accuracy needs real AFC or sensor data, "
          "which the schema is built to accept.",
          "",
          f"Split (time-based): train {split['train'][0]} .. {split['train'][1]} (first 7 days warm up lags), "
          f"validation {split['val'][0]} .. {split['val'][1]}, test {split['test'][0]} .. {split['test'][1]}.",
          f"Target: max demand load factor per (route, direction, stop, 15-min slot), evaluated only on slots where a "
          f"vehicle departed. {len(p.series)} series. Models: B0 = same time last week; Prophet = per route-direction "
          f"with stop share profiles; LSTM = 2x128, 24-slot window, 12-slot quantile head.",
          "",
          f"## Acceptance: LSTM beats B0 on 1-hour MAE at peak slots: **{'PASS' if passed else 'FAIL'}** "
          f"(LSTM {acc_lstm:.4f} vs B0 {acc_b0:.4f}, {1 - acc_lstm / acc_b0:+.1%})",
          "",
          "## Load factor and boardings",
          "",
          "| Horizon | Segment | Model | n | MAE LF | RMSE LF | MAE board | RMSE board | Level acc | Macro-F1 | CROWDED recall | CROWDED precision | 80% band coverage |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in T_.iterrows():
        L_.append(f"| {r.horizon} | {r.segment} | {r.model} | {int(r.n):,} | {fmt(r.MAE_LF)} | {fmt(r.RMSE_LF)} | "
                  f"{fmt(r.get('MAE_board'))} | {fmt(r.get('RMSE_board'))} | {fmt(r.level_acc, True)} | {fmt(r.macro_F1)} | "
                  f"{fmt(r.CROWDED_recall, True)} | {fmt(r.CROWDED_precision, True)} | {fmt(r.get('coverage_80'), True)} |")
    L_ += ["", "## Improvement of the LSTM (MAE on load factor)", "", "| Horizon | Segment | vs B0 | vs Prophet |", "|---|---|---|---|"]
    for h in HORIZONS:
        for seg in ("all", "peak", "off-peak"):
            l, b, pr = get(h, seg, "lstm", "MAE_LF"), get(h, seg, "b0", "MAE_LF"), get(h, seg, "prophet", "MAE_LF")
            L_.append(f"| {h} | {seg} | {1 - l / b:+.1%} | {1 - l / pr:+.1%} |")
    L_ += ["", "## Crowd-level confusion matrix (LSTM, 1-hour horizon; rows = actual, columns = predicted)", "",
           "| actual \\ predicted | " + " | ".join(LEVELS) + " |", "|---" * 5 + "|"]
    for i, lv in enumerate(LEVELS):
        L_.append(f"| {lv} | " + " | ".join(f"{v:,}" for v in cm_l[i]) + " |")
    L_ += ["",
           f"CROWDED recall (LSTM, 1 h, all slots): {cm_l[3, 3] / max(cm_l[3].sum(), 1):.1%}. Reported as measured.",
           "",
           "Load factor here is the *demand* load factor, (onboard + left behind) / capacity, so CROWDED (>= 1.0) "
           "means the vehicle left full with people still waiting.",
           "",
           "Scenario types are assigned per test day from context tables only: event = a city_event with attendance "
           "that day; rain = >= 5 mm of precipitation in the recorded weather; otherwise normal. Segments with few days "
           "are noisy.",
           "",
           "Notes: weather-forecast features use recorded weather (a perfect forecast) for twin data; in deployment "
           "they come from the Open-Meteo forecast API. Prophet has no boardings model, so its boardings columns are empty."]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "forecast_eval.md").write_text("\n".join(L_), encoding="utf8")
    T_.to_csv(REPORTS_DIR / "forecast_eval_table.csv", index=False)
    print("\n".join(L_[:20]))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
