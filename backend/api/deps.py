"""Shared API helpers: API-key auth, rate limit, data-source flag, cached static lookups."""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from functools import lru_cache

from fastapi import Header, HTTPException

from db.database import query

RATE_LIMIT_PER_MIN = 60
_hits: dict[str, deque] = defaultdict(deque)


def api_keys() -> set[str]:
    # Camera nodes authenticate with a key from the environment. "dev-key" only if none set (demo).
    keys = os.environ.get("CAMERA_API_KEYS") or os.environ.get("CAMERA_API_KEY") or "dev-key"
    return {k.strip() for k in keys.split(",") if k.strip()}


def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    if not x_api_key or x_api_key not in api_keys():
        raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")
    now = time.monotonic()
    q = _hits[x_api_key]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="rate limit: 60 requests/min per key")
    q.append(now)
    return x_api_key


def data_source_of(sources) -> str:
    """Collapse row sources to the flag the UI uses for the 'Simulated data' badge."""
    s = {x for x in sources if x}
    if not s:
        return "none"
    has_twin = "twin" in s
    has_obs = bool(s - {"twin"})
    if has_twin and has_obs:
        return "mixed"
    return "twin" if has_twin else "camera"


@lru_cache(maxsize=1)
def stop_ids() -> frozenset[str]:
    return frozenset(query("SELECT stop_id FROM stop").stop_id)


@lru_cache(maxsize=1)
def routes_df():
    return query("SELECT * FROM route")


@lru_cache(maxsize=1)
def route_stops_df():
    return query("SELECT rs.*, s.name, s.lat, s.lon, s.mode, s.stop_type, s.station_id FROM route_stop rs "
                 "JOIN stop s ON s.stop_id = rs.stop_id ORDER BY route_id, direction, seq")


def clear_caches():
    stop_ids.cache_clear()
    routes_df.cache_clear()
    route_stops_df.cache_clear()
