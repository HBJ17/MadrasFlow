"""Test fixtures: an isolated SQLite DB seeded from the GTFS-derived network, with two simulated
days (twin data, calendar effects off) written to it. Requires data/raw (python data/fetch_data.py)."""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = [ROOT / d for d in ("backend", "database", "ml", "simulation")]   # Python package roots
sys.path[:0] = [str(p) for p in SRC]
os.environ["PYTHONPATH"] = os.pathsep.join([*map(str, SRC), os.environ.get("PYTHONPATH", "")])   # for subprocesses
TEST_DB = ROOT / "data" / "test_transit.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["DISABLE_SCHEDULER"] = "1"
SIM_START = date.today() - timedelta(days=2)


@pytest.fixture(scope="session")
def seeded_db():
    from db import database

    for suffix in ("", "-wal", "-shm"):
        p = Path(str(TEST_DB) + suffix)
        if p.exists():
            p.unlink()
    database.reset_engine()
    from db.seed import main as seed_main

    assert seed_main() == 0
    from twin.simulate import run, to_db

    ev, s = run(start_date=SIM_START, days=2, seed=123, workers=2, use_calendar=False, run_id="test-2d")
    to_db(ev, s)
    return {"events": ev, "summary": s}
