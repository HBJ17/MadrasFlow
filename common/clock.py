"""Demo clock. Real wall-clock time in Asia/Kolkata, optionally shifted so a demo at 2 a.m.
can show the 08:00 peak: set DEMO_CLOCK_START=08:00 (time-of-day at server start) and
DEMO_CLOCK_SPEED=1 (real-time) or higher to fast-forward."""
from __future__ import annotations

import os
import time as _time
from datetime import datetime, timedelta

from .config import IST, hhmm_to_min

_T0_REAL = _time.time()


def now() -> datetime:
    real = datetime.now(IST)
    start = os.environ.get("DEMO_CLOCK_START")
    if not start:
        return real
    speed = float(os.environ.get("DEMO_CLOCK_SPEED", "1"))
    base = real.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=hhmm_to_min(start))
    return base + timedelta(seconds=(_time.time() - _T0_REAL) * speed)
