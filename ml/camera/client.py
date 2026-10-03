"""Edge client: posts counts to POST /ingest/events. Buffers in a local SQLite file when the network
is down and flushes in order with exponential back-off; every event carries a client_event_id so
retries are idempotent. Sends POST /ingest/heartbeat every 60 s. Never sends images or video."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

IST = timezone(timedelta(hours=5, minutes=30))
log = logging.getLogger("camera.client")


class EdgeClient:
    def __init__(self, api: str | None = None, key: str | None = None, node_id: str = "node", kind: str = "",
                 buffer_path: str | Path | None = None):
        self.api = (api or os.environ.get("TRANSIT_API", "http://127.0.0.1:8000/api/v1")).rstrip("/")
        self.key = key or os.environ.get("CAMERA_API_KEY", "dev-key")
        self.node_id, self.kind = node_id, kind
        self.db = sqlite3.connect(str(buffer_path or Path(__file__).with_name(f"buffer_{node_id}.sqlite")),
                                  check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT)")
        self.db.commit()
        self._lock = threading.Lock()
        self.fps = None
        self._backoff = 1.0
        self._next_try = 0.0
        self._last_hb = 0.0

    def post_event(self, **ev):
        ev.setdefault("ts", datetime.now(IST).isoformat(timespec="seconds"))
        ev.setdefault("client_event_id", f"{self.node_id}-{uuid.uuid4().hex}")
        ev.setdefault("node_id", self.node_id)
        with self._lock:
            self.db.execute("INSERT INTO outbox(body) VALUES (?)", (json.dumps(ev),))
            self.db.commit()
        log.info("count %s", {k: v for k, v in ev.items() if k not in ("client_event_id", "node_id")})
        self.flush()

    def flush(self) -> int:
        if time.monotonic() < self._next_try:
            return 0
        with self._lock:
            rows = self.db.execute("SELECT id, body FROM outbox ORDER BY id LIMIT 500").fetchall()
        if not rows:
            return 0
        try:
            r = requests.post(f"{self.api}/ingest/events", json=[json.loads(b) for _, b in rows],
                              headers={"X-API-Key": self.key}, timeout=5)
            if r.status_code in (200, 201):
                with self._lock:
                    self.db.execute("DELETE FROM outbox WHERE id <= ?", (rows[-1][0],))
                    self.db.commit()
                res = r.json()
                if res.get("rejected"):
                    log.warning("server rejected %d events: %s", res["rejected"], res.get("errors"))
                self._backoff = 1.0
                return len(rows)
            if r.status_code in (400, 401, 413, 422):
                log.error("server refused batch (%s): %s", r.status_code, r.text[:200])
            raise RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:
            self._next_try = time.monotonic() + self._backoff
            log.warning("offline (%s); %d buffered; retry in %.0fs", e, len(rows), self._backoff)
            self._backoff = min(self._backoff * 2, 300)
            return 0

    def heartbeat(self, force: bool = False):
        if not force and time.monotonic() - self._last_hb < 60:
            return
        self._last_hb = time.monotonic()
        try:
            requests.post(f"{self.api}/ingest/heartbeat", json={"node_id": self.node_id, "fps": self.fps, "kind": self.kind},
                          headers={"X-API-Key": self.key}, timeout=5)
        except Exception as e:
            log.warning("heartbeat failed: %s", e)

    def pending(self) -> int:
        with self._lock:
            return self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
