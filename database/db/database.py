"""Database access. SQLite for the demo (DATABASE_URL overrides, e.g. a Postgres URL)."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

from common.config import DATA_DIR

SCHEMA = Path(__file__).with_name("schema.sql")
_engine: Engine | None = None


def db_url() -> str:
    return os.environ.get("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'transit.db').as_posix()}")


def engine() -> Engine:
    global _engine
    if _engine is None:
        url = db_url()
        _engine = create_engine(url, future=True, connect_args={"timeout": 30} if url.startswith("sqlite") else {})
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _pragmas(conn, _):
                cur = conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.close()
    return _engine


def reset_engine():
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def init_schema(drop: bool = False) -> None:
    eng = engine()
    sql = SCHEMA.read_text(encoding="utf8")
    with eng.begin() as c:
        if drop:
            for v in ("v_event_labelled", "v_stop_slot", "v_route_stop_slot"):
                c.exec_driver_sql(f"DROP VIEW IF EXISTS {v}")
            for t in ("stop", "route", "route_stop", "trip", "event", "camera_raw", "node_heartbeat", "weather_hourly",
                      "calendar_day", "city_event", "forecast", "advisory", "twin_run", "unmet_demand"):
                c.exec_driver_sql(f"DROP TABLE IF EXISTS {t}")
        raw = c.connection.dbapi_connection if hasattr(c.connection, "dbapi_connection") else c.connection
        if eng.url.get_backend_name() == "sqlite":
            raw.executescript(sql)
        else:
            for stmt in sql.split(";"):
                if stmt.strip():
                    c.exec_driver_sql(stmt)
    migrate()


# Columns added after the first release; init_schema/migrate add them to an existing database.
ADDED_COLUMNS = {"advisory": {"kind": "TEXT DEFAULT 'add_trips'"}}


def migrate() -> None:
    eng = engine()
    if eng.url.get_backend_name() != "sqlite":
        return
    with eng.begin() as c:
        for table, cols in ADDED_COLUMNS.items():
            have = {r[1] for r in c.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}
            if not have:
                continue
            for col, decl in cols.items():
                if col not in have:
                    c.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine().connect() as c:
        return pd.read_sql(text(sql), c, params=params or {})


def execute(sql: str, params: dict | list | None = None) -> None:
    with engine().begin() as c:
        c.execute(text(sql), params or {})


EVENT_COLS = ["ts", "slot_15", "route_id", "trip_id", "vehicle_id", "stop_id", "direction", "boardings", "alightings",
              "onboard_load", "waiting_count", "left_behind", "payment_mode", "fare_inr", "source", "scenario_id",
              "run_id", "client_event_id"]


def write_events(df: pd.DataFrame, chunksize: int = 50000) -> int:
    cols = [c for c in EVENT_COLS if c in df.columns]
    df[cols].to_sql("event", engine(), if_exists="append", index=False, chunksize=chunksize, method=None)
    return len(df)
