"""Advisory logic: a forced overload is detected, remedied, and verified by the twin what-if."""
import pandas as pd

from advisory import headway
from common.config import IST, iso
from db.database import engine, execute, query
from tests.conftest import SIM_START


def _force_overload(now):
    """Overwrite the latest LSTM forecast for BUS_95 dir 0 with LF 1.3 for 3 slots."""
    made = iso(now)
    execute("DELETE FROM forecast WHERE model = 'lstm'")
    rs = query("SELECT stop_id, seq FROM route_stop WHERE route_id='BUS_95' AND direction=0")
    rows = []
    for h in range(1, 13):
        slot = now.floor("15min") + pd.Timedelta(minutes=15 * h)
        for s in rs.itertuples():
            lf = 1.3 if (3 <= h <= 5 and 5 <= s.seq <= 15) else 0.5
            rows.append({"made_at": made, "target_slot": iso(slot), "stop_id": s.stop_id, "route_id": "BUS_95",
                         "direction": 0, "model": "lstm", "pred_lf": lf, "lo": lf - 0.1, "hi": lf + 0.1,
                         "pred_load": lf * 70, "level": "CROWDED" if lf >= 1 else "MEDIUM", "stale": 0,
                         "data_source": "twin", "horizon": h})
    pd.DataFrame(rows).to_sql("forecast", engine(), if_exists="append", index=False)


def test_detect_window(seeded_db):
    now = pd.Timestamp(SIM_START, tz=IST) + pd.Timedelta(days=1, hours=7, minutes=30)
    _force_overload(now)
    w = headway.detect(now)
    assert len(w) == 1 and w[0]["route_id"] == "BUS_95" and w[0]["minutes"] == 45
    p = headway.propose(w[0])
    assert p["extra_trips"] >= 1 and p["new_headway"] < p["headway"]


def test_advisory_verified_by_whatif(seeded_db):
    now = pd.Timestamp(SIM_START, tz=IST) + pd.Timedelta(days=1, hours=7, minutes=30)
    _force_overload(now)
    execute("DELETE FROM advisory")
    out = headway.run_advisories(now, seed=123)
    assert len(out) == 1
    a = out[0]
    assert a["expected_lf_after"] is not None and a["expected_lf_before"] is not None
    if a["status"] == "active":
        assert a["expected_lf_after"] < 1.0
    assert a["expected_lf_after"] <= a["expected_lf_before"]
    assert query("SELECT COUNT(*) n FROM advisory").n[0] == 1
