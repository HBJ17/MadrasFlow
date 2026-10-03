"""Phase 6: generate the simulated training history (default 90 days ending yesterday).

    python -m twin.generate --days 90 [--end 2026-10-01] [--seed 42] [--verify]

Runs days in parallel processes, writes data/processed/twin_history_*.parquet and the event,
trip, twin_run and unmet_demand tables. Existing history rows (run_id 'history-*') are replaced.
Reproducible: the same seed gives identical events (--verify re-runs two days and compares).
"""
from __future__ import annotations

import argparse
import hashlib
import time
from datetime import date, timedelta

import pandas as pd

from common.config import PROCESSED_DIR
from db.database import execute, query
from twin.simulate import run, to_db


def events_hash(ev: pd.DataFrame) -> str:
    cols = ["ts", "route_id", "trip_id", "stop_id", "boardings", "alightings", "onboard_load", "left_behind"]
    return hashlib.sha256(pd.util.hash_pandas_object(ev[cols], index=False).values.tobytes()).hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--end", default=None, help="last simulated date (default: yesterday)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--no-db", action="store_true")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    end = date.fromisoformat(a.end) if a.end else date.today() - timedelta(days=1)
    start = end - timedelta(days=a.days - 1)
    run_id = f"history-{start:%Y%m%d}-{end:%Y%m%d}-s{a.seed}"
    t0 = time.time()
    ev, s = run(scenario="baseline", start_date=start, days=a.days, seed=a.seed, workers=a.workers, run_id=run_id)
    print(f"simulated {a.days} days in {time.time() - t0:.0f}s: {len(ev):,} events, "
          f"{s['boardings_per_day']:,} boardings/day, by mode {s['by_mode_per_day']}")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pq = PROCESSED_DIR / f"twin_history_{start:%Y%m%d}_{end:%Y%m%d}_s{a.seed}.parquet"
    ev.to_parquet(pq, index=False)
    h = events_hash(ev)
    print(f"wrote {pq} (hash {h})")
    if a.verify:
        ev2, _ = run(scenario="baseline", start_date=start, days=2, seed=a.seed, workers=2, run_id=run_id)
        first2 = ev[ev.trip_id.str.contains(f"_{start:%Y%m%d}_|_{start + timedelta(days=1):%Y%m%d}_")]
        same = events_hash(first2.reset_index(drop=True)) == events_hash(ev2.reset_index(drop=True))
        print(f"reproducibility (first 2 days re-run, same seed): {'IDENTICAL' if same else 'DIFFERENT'}")
    if not a.no_db:
        t1 = time.time()
        old = query("SELECT run_id FROM twin_run WHERE run_id LIKE 'history-%'").run_id.tolist()
        for r in old:
            execute("DELETE FROM event WHERE run_id = :r", {"r": r})
            execute("DELETE FROM unmet_demand WHERE run_id = :r", {"r": r})
            execute("DELETE FROM twin_run WHERE run_id = :r", {"r": r})
        n = to_db(ev, s, {"days": a.days, "start": str(start), "end": str(end), "seed": a.seed, "hash": h})
        total = query("SELECT COUNT(*) n FROM event WHERE source = 'twin'").n.iloc[0]
        print(f"db: {n:,} event rows in {time.time() - t1:.0f}s; total twin rows {total:,}")


if __name__ == "__main__":
    main()
