"""Config loading and shared constants (crowd levels, time helpers)."""
from __future__ import annotations

import math
import os
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]   # backend/common/config.py -> project root
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
# Overridable so the smoke test never overwrites real models/reports
REPORTS_DIR = Path(os.environ.get("TRANSIT_REPORTS_DIR", ROOT / "reports"))
MODELS_DIR = Path(os.environ.get("TRANSIT_MODELS_DIR", ROOT / "ml" / "models"))

IST = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")

# Section 1: load factor -> crowd level. Use everywhere.
LEVELS = ["LOW", "MEDIUM", "HIGH", "CROWDED"]
LEVEL_BOUNDS = [0.40, 0.75, 1.00]


def crowd_level(load_factor: float | None) -> str | None:
    if load_factor is None or (isinstance(load_factor, float) and math.isnan(load_factor)):
        return None
    if load_factor < 0.40:
        return "LOW"
    if load_factor < 0.75:
        return "MEDIUM"
    if load_factor < 1.00:
        return "HIGH"
    return "CROWDED"


def level_index(level: str | None) -> int:
    return LEVELS.index(level) if level in LEVELS else 0


def load_yaml(name: str) -> dict:
    path = CONFIG_DIR / name
    with open(path, encoding="utf8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def corridor() -> dict:
    return load_yaml("corridor.yaml")


def demand_config() -> dict:
    """demand.yaml with demand_fitted.yaml (calibration output) overlaid, if present."""
    cfg = load_yaml("demand.yaml")
    fitted = CONFIG_DIR / "demand_fitted.yaml"
    if fitted.exists():
        with open(fitted, encoding="utf8") as f:
            fit = yaml.safe_load(f) or {}
        for k, v in (fit.get("params") or {}).items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k] = {**cfg[k], **v}
            else:
                cfg[k] = v
    return cfg


def peak_hours() -> list[int]:
    """Clock hours counted as peak (calibration_targets.yaml peak_hours, [from, to) pairs)."""
    spans = load_yaml("calibration_targets.yaml")["corridor"]["peak_hours"]
    return [h for a, b in spans for h in range(a, b)]


def hhmm_to_min(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def floor_15(ts: datetime) -> datetime:
    return ts.replace(minute=ts.minute - ts.minute % 15, second=0, microsecond=0)


def day_start(d: date) -> datetime:
    return datetime.combine(d, time(0, 0), tzinfo=IST)


def iso(ts: datetime) -> str:
    return ts.astimezone(IST).isoformat(timespec="seconds")


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres (works on scalars or numpy arrays)."""
    import numpy as np

    r = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2) - np.radians(lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))
