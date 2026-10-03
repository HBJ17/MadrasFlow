"""Schema constraints: the event table is the contract."""
import pytest
from sqlalchemy.exc import IntegrityError

from db.database import execute, query


def _ins(**kw):
    row = {"ts": "2026-10-01T08:00:00+05:30", "slot_15": "2026-10-01T08:00:00+05:30", "stop_id": "MRTS_VLCY",
           "boardings": 0, "alightings": 0, "onboard_load": 0, "source": "camera_stop", "client_event_id": None}
    row.update(kw)
    cols = ",".join(row)
    execute(f"INSERT INTO event ({cols}) VALUES ({','.join(':' + c for c in row)})", row)


def test_source_must_be_known(seeded_db):
    with pytest.raises(IntegrityError):
        _ins(source="made_up")


def test_negative_counts_rejected(seeded_db):
    for f in ("boardings", "alightings", "onboard_load"):
        with pytest.raises(IntegrityError):
            _ins(**{f: -1})


def test_client_event_id_unique(seeded_db):
    _ins(client_event_id="dup-1")
    with pytest.raises(IntegrityError):
        _ins(client_event_id="dup-1")


def test_simulated_rows_labelled(seeded_db):
    v = query("SELECT DISTINCT source, data_label FROM v_event_labelled WHERE source = 'twin'")
    assert list(v.data_label) == ["SIMULATED"]


def test_route_stop_refers_to_stops(seeded_db):
    assert query("SELECT COUNT(*) n FROM route_stop rs LEFT JOIN stop s USING(stop_id) WHERE s.stop_id IS NULL").n[0] == 0
