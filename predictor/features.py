"""Feature panel for forecasting (section 7.2). Reads only from the database.

A series is one (route_id, direction, stop_id). The panel is a dense grid of series x 15-minute
slots (96 per day). The target is the max *demand* load factor of vehicles departing the stop in
the slot, (onboard_load + left_behind) / capacity_total (NaN when no vehicle departed). Onboard
load alone is capped at capacity, so it cannot show how far demand exceeds supply; adding the
passengers left behind gives values above 1.0 (CROWDED) that an advisory can act on ("LF 1.3").
Inputs use a forward-filled copy plus an 'observed' mask.

Leakage rule: a feature at origin slot t uses only data with timestamps <= end of slot t.
Exceptions, by design and listed in FORECAST_FEATURES: the timetable (scheduled supply), the
event calendar and the weather forecast for the next 3 h are known in advance. With twin data the
'forecast' is the recorded weather, i.e. a perfect forecast (documented in KNOWN_LIMITS.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from common.config import IST, haversine_m, iso
from db.database import query

SLOTS_PER_DAY = 96
WEEK = 7 * SLOTS_PER_DAY
STOP_TYPES = ["office", "college", "market", "residential", "hospital", "interchange"]
MODES = ["bus", "mrts", "metro"]
FORECAST_FEATURES = {"precip_next3h", "sched_trips", "sched_trips_next", "event_active", "hours_to_event",
                     "hours_from_event", "event_attendance", "holiday_in_days", "is_holiday"}


@dataclass
class Panel:
    series: pd.DataFrame          # route_id, direction, stop_id, seq, capacity, mode, stop_type, demand_weight, up, down
    times: pd.DatetimeIndex       # slot starts (tz IST), length T
    lf: np.ndarray                # S x T observed max LF (NaN = no vehicle)
    board: np.ndarray             # S x T boardings (0 when none)
    sources: np.ndarray           # S x T bool: any non-twin source in slot
    exo: pd.DataFrame             # T x E time-level exogenous variables
    ev: dict = field(default_factory=dict)       # S x T event arrays
    supply: np.ndarray | None = None              # S x T scheduled trips in slot (route-dir level)


def _series_meta() -> pd.DataFrame:
    s = query("""SELECT rs.route_id, rs.direction, rs.stop_id, rs.seq, r.capacity_total AS capacity, r.mode,
                        st.stop_type, st.demand_weight, st.lat, st.lon
                 FROM route_stop rs JOIN route r ON r.route_id = rs.route_id JOIN stop st ON st.stop_id = rs.stop_id
                 ORDER BY rs.route_id, rs.direction, rs.seq""")
    s = s.reset_index(drop=True)
    key = {(r, d, q): i for i, (r, d, q) in enumerate(zip(s.route_id, s.direction, s.seq))}
    s["up"] = [key.get((r, d, q - 1), -1) for r, d, q in zip(s.route_id, s.direction, s.seq)]
    s["down"] = [key.get((r, d, q + 1), -1) for r, d, q in zip(s.route_id, s.direction, s.seq)]
    return s


def build_panel(start: pd.Timestamp, end: pd.Timestamp, sources: tuple[str, ...] | None = None,
                scenario_id: str | None = None) -> Panel:
    """Dense panel for slots in [start, end) (both tz-aware, day-aligned recommended)."""
    start, end = pd.Timestamp(start).tz_convert(IST), pd.Timestamp(end).tz_convert(IST)
    series = _series_meta()
    times = pd.date_range(start, end, freq="15min", inclusive="left")
    T, S = len(times), len(series)
    where = ""
    if sources:
        where += " AND e.source IN (" + ",".join(f"'{s}'" for s in sources) + ")"
    if scenario_id:
        where += f" AND (e.scenario_id = '{scenario_id}' OR e.source != 'twin')"
    ev = query(f"""SELECT e.route_id, e.direction, e.stop_id, e.slot_15,
                          MAX(e.onboard_load + COALESCE(e.left_behind, 0)) AS load,
                          SUM(e.boardings) AS boardings, MAX(CASE WHEN e.source != 'twin' THEN 1 ELSE 0 END) AS obs,
                          COUNT(DISTINCT e.trip_id) AS trips
                   FROM event e WHERE e.slot_15 >= :a AND e.slot_15 < :b AND e.route_id IS NOT NULL {where}
                   GROUP BY e.route_id, e.direction, e.stop_id, e.slot_15""", {"a": iso(start), "b": iso(end)})
    lf = np.full((S, T), np.nan, dtype=np.float32)
    board = np.zeros((S, T), dtype=np.float32)
    srcs = np.zeros((S, T), dtype=bool)
    supply = np.zeros((S, T), dtype=np.float32)
    if len(ev):
        key = {(r, int(d), s): i for i, (r, d, s) in enumerate(zip(series.route_id, series.direction, series.stop_id))}
        si = np.array([key.get((r, int(d) if pd.notna(d) else -1, s), -1)
                       for r, d, s in zip(ev.route_id, ev.direction, ev.stop_id)])
        ti = times.get_indexer(pd.to_datetime(ev.slot_15, utc=True).dt.tz_convert(IST))
        ok = (si >= 0) & (ti >= 0)
        cap = series.capacity.values[si[ok]]
        lf[si[ok], ti[ok]] = ev.load.values[ok] / cap
        board[si[ok], ti[ok]] = ev.boardings.values[ok]
        srcs[si[ok], ti[ok]] = ev.obs.values[ok] > 0
        supply[si[ok], ti[ok]] = ev.trips.values[ok]
    # scheduled supply proxy: trips through the route's first stop in the slot, shared by the whole route-dir
    first = series.groupby(["route_id", "direction"]).seq.transform("min") == series.seq
    for (r, d), g in series.groupby(["route_id", "direction"]):
        fi = g.index[first[g.index]][0]
        supply[g.index] = supply[fi]

    exo = _exogenous(times)
    evf = _event_features(series, times)
    return Panel(series, times, lf, board, srcs, exo, evf, supply)


def _exogenous(times: pd.DatetimeIndex) -> pd.DataFrame:
    w = query("SELECT ts, precip_mm, temp_c FROM weather_hourly")
    w["ts"] = pd.to_datetime(w.ts, utc=True).dt.tz_convert(IST)
    w = w.set_index("ts").sort_index()
    hourly = w.reindex(times.floor("h")).ffill().bfill()
    cal = query("SELECT date, day_type, is_holiday FROM calendar_day")
    cal["date"] = pd.to_datetime(cal.date).dt.date
    hol_dates = np.array(sorted(cal.loc[cal.is_holiday == 1, "date"]), dtype="datetime64[D]")
    day_type = dict(zip(cal.date, cal.day_type))
    d = times.date
    slot = (times.hour * 4 + times.minute // 15).values
    out = pd.DataFrame(index=times)
    out["slot_sin"] = np.sin(2 * np.pi * slot / SLOTS_PER_DAY)
    out["slot_cos"] = np.cos(2 * np.pi * slot / SLOTS_PER_DAY)
    for k in range(7):
        out[f"dow_{k}"] = (times.dayofweek == k).astype(np.float32)
    out["week_of_year"] = times.isocalendar().week.values.astype(np.float32) / 53.0
    out["is_weekend"] = (times.dayofweek >= 5).astype(np.float32)
    out["is_holiday"] = np.array([day_type.get(x) == "holiday" for x in d], dtype=np.float32)
    dd = np.array(d, dtype="datetime64[D]")
    if len(hol_dates):
        idx = np.searchsorted(hol_dates, dd)
        nxt = hol_dates[np.minimum(idx, len(hol_dates) - 1)]
        prv = hol_dates[np.maximum(idx - 1, 0)]
        out["holiday_in_days"] = np.clip((nxt - dd).astype(int), 0, 14) / 14.0
        out["days_since_holiday"] = np.clip((dd - prv).astype(int), 0, 14) / 14.0
    else:
        out["holiday_in_days"] = 1.0
        out["days_since_holiday"] = 1.0
    out["precip"] = hourly.precip_mm.values
    p = w.precip_mm
    nxt3 = p.rolling(3, min_periods=1).sum().shift(-3)  # sum of the next 3 h (forecast)
    out["precip_next3h"] = nxt3.reindex(times.floor("h")).fillna(0).values
    out["temp"] = (hourly.temp_c.values - 28.0) / 5.0
    return out.astype(np.float32)


def _event_features(series: pd.DataFrame, times: pd.DatetimeIndex) -> dict:
    ce = query("""SELECT ce.*, s.lat, s.lon FROM city_event ce JOIN stop s ON s.stop_id = ce.stop_id
                  WHERE ce.expected_attendance > 0""")
    S, T = len(series), len(times)
    active = np.zeros((S, T), np.float32)
    to_ev = np.full((S, T), 1.0, np.float32)
    from_ev = np.full((S, T), 1.0, np.float32)
    att = np.zeros((S, T), np.float32)
    tv = times.values.astype("datetime64[m]").astype(np.int64)
    for _, e in ce.iterrows():
        st = pd.Timestamp(e.start_ts).tz_convert(IST)
        en = pd.Timestamp(e.end_ts).tz_convert(IST)
        if en < times[0] - pd.Timedelta(hours=6) or st > times[-1] + pd.Timedelta(hours=6):
            continue
        dist = haversine_m(e.lat, e.lon, series.lat.values, series.lon.values) / 1000.0
        prox = np.clip(1 - dist / 5.0, 0, 1)[:, None]  # within 5 km
        s0 = np.int64(st.to_datetime64().astype("datetime64[m]").astype(np.int64))
        s1 = np.int64(en.to_datetime64().astype("datetime64[m]").astype(np.int64))
        h_to = (s0 - tv) / 60.0
        h_from = (tv - s1) / 60.0
        win = ((h_to <= 2) & (h_from <= 1)).astype(np.float32)[None, :]
        active = np.maximum(active, win * prox)
        to_ev = np.minimum(to_ev, np.where((h_to >= 0) & (h_to < 6), h_to / 6, 1.0)[None, :] * np.ones((S, 1)) * (prox > 0) + (prox == 0))
        from_ev = np.minimum(from_ev, np.where((h_from >= 0) & (h_from < 6), h_from / 6, 1.0)[None, :] * np.ones((S, 1)) * (prox > 0) + (prox == 0))
        att = np.maximum(att, win * prox * float(e.expected_attendance) / 40000.0)
    return {"event_active": active, "hours_to_event": to_ev, "hours_from_event": from_ev, "event_attendance": att}


def ffill_rows(a: np.ndarray, limit_slots: int = SLOTS_PER_DAY) -> np.ndarray:
    """Forward-fill NaNs along time (axis 1); remaining NaNs -> 0."""
    S, T = a.shape
    idx = np.where(~np.isnan(a), np.arange(T)[None, :], 0)
    np.maximum.accumulate(idx, axis=1, out=idx)
    out = a[np.arange(S)[:, None], idx]
    gap = np.arange(T)[None, :] - idx
    out[(gap > limit_slots) | np.isnan(out)] = 0.0
    return out


def _lag(a: np.ndarray, k: int) -> np.ndarray:
    out = np.zeros_like(a)
    if k < a.shape[1]:
        out[:, k:] = a[:, :-k]
    return out


def _roll(a: np.ndarray, w: int):
    c = np.cumsum(np.pad(a, ((0, 0), (1, 0))), axis=1)
    c2 = np.cumsum(np.pad(a * a, ((0, 0), (1, 0))), axis=1)
    T = a.shape[1]
    hi = np.arange(1, T + 1)
    lo = np.maximum(0, hi - w)
    n = (hi - lo)[None, :]
    m = (c[:, hi] - c[:, lo]) / n
    v = np.maximum((c2[:, hi] - c2[:, lo]) / n - m * m, 0)
    return m, np.sqrt(v)


def make_features(p: Panel) -> tuple[np.ndarray, list[str]]:
    """S x T x F float32 feature tensor (values at origin slot t use data <= end of slot t)."""
    S, T = p.lf.shape
    lf_f = ffill_rows(p.lf)
    obs = (~np.isnan(p.lf)).astype(np.float32)
    b = p.board / np.maximum(p.series.capacity.values[:, None], 1)
    feats, names = [], []

    def add(name, arr):
        names.append(name)
        feats.append(arr.astype(np.float32))

    add("lf", lf_f)
    add("observed", obs)
    add("board", b)
    for k in (1, 2, 4):
        add(f"lf_lag{k}", _lag(lf_f, k))
    add("lf_lag_day", _lag(lf_f, SLOTS_PER_DAY))
    add("lf_lag_week", _lag(lf_f, WEEK))
    add("lf_lag_week_next", _lag(lf_f, WEEK - 1))       # same slot last week, one step ahead
    add("board_lag_day", _lag(b, SLOTS_PER_DAY))
    add("board_lag_week", _lag(b, WEEK))
    for w in (4, 16):
        m, s = _roll(lf_f, w)
        add(f"lf_mean{w}", m)
        add(f"lf_std{w}", s)
    up = p.series.up.values
    down = p.series.down.values
    up_lf = np.where((up >= 0)[:, None], lf_f[np.maximum(up, 0)], 0)
    add("up_lf", up_lf)
    add("up_lf_lag1", _lag(up_lf, 1))
    dn = np.where((down >= 0)[:, None], lf_f[np.maximum(down, 0)], 0)
    add("down_lf_lag_week", _lag(dn, WEEK - 1))
    grp = p.series.groupby(["route_id", "direction"]).ngroup().values
    route_mean = np.zeros_like(lf_f)
    for g in np.unique(grp):
        route_mean[grp == g] = lf_f[grp == g].mean(axis=0)
    add("route_lf", route_mean)
    sup = p.supply
    add("sched_trips", sup / 4.0)
    add("sched_trips_next", np.concatenate([sup[:, 1:], sup[:, -1:]], axis=1) / 4.0)  # timetable: known ahead
    for k, v in p.ev.items():
        add(k, v)
    for c in p.exo.columns:
        add(c, np.broadcast_to(p.exo[c].values[None, :], (S, T)))
    for t in STOP_TYPES:
        add(f"type_{t}", np.broadcast_to((p.series.stop_type.values == t)[:, None], (S, T)))
    for m in MODES:
        add(f"mode_{m}", np.broadcast_to((p.series["mode"].values == m)[:, None], (S, T)))
    add("demand_weight", np.broadcast_to((p.series.demand_weight.values / 10.0)[:, None], (S, T)))
    return np.stack(feats, axis=2), names
