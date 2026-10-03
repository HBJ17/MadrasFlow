"""Create the schema and load the corridor network + context tables.

    python -m db.seed            # (re)create data/transit.db and load static data

Phase 1 acceptance: prints row counts and checks every route_stop.stop_id exists in stop.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

import pandas as pd

from common.config import DATA_DIR, IST, RAW_DIR, iso
from db.database import engine, init_schema, query
from twin.network import load_network

HISTORY_DAYS = 100
FUTURE_DAYS = 14


def build_calendar(start: date, end: date) -> pd.DataFrame:
    hol = {}
    path = RAW_DIR / "holidays_tn.csv"
    if path.exists():
        h = pd.read_csv(path)
        hol = dict(zip(pd.to_datetime(h.date).dt.date, h.name))
    else:  # fallback: hand list of fixed-date public holidays (section 3 row 10)
        for y in {start.year, end.year}:
            for m, d, n in [(1, 26, "Republic Day"), (8, 15, "Independence Day"), (10, 2, "Gandhi Jayanti"),
                            (1, 15, "Pongal"), (5, 1, "May Day"), (12, 25, "Christmas")]:
                hol[date(y, m, d)] = n
    rows = []
    d = start
    while d <= end:
        if d in hol:
            rows.append((d.isoformat(), "holiday", 1, hol[d]))
        elif d.weekday() >= 5:
            rows.append((d.isoformat(), "weekend", 0, None))
        else:
            rows.append((d.isoformat(), "weekday", 0, None))
        d += timedelta(days=1)
    return pd.DataFrame(rows, columns=["date", "day_type", "is_holiday", "note"])


def template_trips(net, d: date) -> pd.DataFrame:
    tt = net.timetable.copy()
    base = pd.Timestamp(d, tz=IST)
    tt["scheduled_start"] = [iso(base + pd.Timedelta(minutes=m)) for m in tt.start_min]
    tt["trip_id"] = [f"{r}_{dr}_{d:%Y%m%d}_{int(m):04d}" for r, dr, m in zip(tt.route_id, tt.direction, tt.start_min)]
    tt["vehicle_id"] = None
    return tt[["trip_id", "route_id", "direction", "scheduled_start", "vehicle_id"]]


def main() -> int:
    DATA_DIR.mkdir(exist_ok=True)
    init_schema(drop=True)
    net = load_network()
    eng = engine()
    today = date.today()

    net.stops[["stop_id", "name", "lat", "lon", "mode", "stop_type", "demand_weight", "station_id"]].to_sql(
        "stop", eng, if_exists="append", index=False)
    net.routes[["route_id", "short_name", "mode", "operator", "capacity_seated", "capacity_total", "long_name", "depot"]].to_sql(
        "route", eng, if_exists="append", index=False)
    net.route_stop.to_sql("route_stop", eng, if_exists="append", index=False)
    template_trips(net, today).to_sql("trip", eng, if_exists="append", index=False)

    w = RAW_DIR / "weather_hourly.csv"
    if w.exists():
        wd = pd.read_csv(w)
        wd["ts"] = pd.to_datetime(wd.ts).map(iso)
        wd.to_sql("weather_hourly", eng, if_exists="append", index=False)
    build_calendar(today - timedelta(days=HISTORY_DAYS), today + timedelta(days=FUTURE_DAYS)).to_sql(
        "calendar_day", eng, if_exists="append", index=False)
    ev = pd.read_csv(DATA_DIR / "events.csv")
    ev[["event_name", "start_ts", "end_ts", "stop_id", "expected_attendance", "multiplier"]].to_sql(
        "city_event", eng, if_exists="append", index=False)

    for t in ("stop", "route", "route_stop", "trip", "weather_hourly", "calendar_day", "city_event"):
        print(f"{t:15s} {query(f'SELECT COUNT(*) n FROM {t}').n.iloc[0]:>7,} rows")
    orphans = query("SELECT rs.route_id, rs.stop_id FROM route_stop rs LEFT JOIN stop s ON s.stop_id = rs.stop_id "
                    "WHERE s.stop_id IS NULL")
    bad_ev = query("SELECT ce.stop_id FROM city_event ce LEFT JOIN stop s ON s.stop_id = ce.stop_id WHERE s.stop_id IS NULL")
    if len(orphans) or len(bad_ev):
        print(f"FAIL: route_stop rows without a stop: {len(orphans)}; city_event without a stop: {len(bad_ev)}")
        print(orphans.head().to_string(), bad_ev.head().to_string())
        return 1
    print("OK: every route_stop.stop_id and city_event.stop_id exists in stop")
    for n in net.notes:
        print("note:", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
