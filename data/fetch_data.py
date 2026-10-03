"""Download the free inputs (spec section 3, inputs 1, 2, 9, 10 and 12) into data/raw/.

    python data/fetch_data.py            # download what is missing
    python data/fetch_data.py --force    # re-download everything

Caches under data/raw/, prints row counts, and exits non-zero with a clear message if any
required file is missing after the run. Raw data is never committed (see .gitignore).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common.config import RAW_DIR  # noqa: E402

GTFS_URL = "https://raw.githubusercontent.com/ungalsoththu/ChennaiGTFS/main/data/chennai-unified-gtfs.zip"
OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
                 "https://overpass.kumi.systems/api/interpreter"]
HEADERS = {"User-Agent": "transit-twin/0.1 (hackathon research; South Chennai occupancy predictor)"}
# South Chennai corridor bounding box (S, W, N, E), wide enough for MRTS up to Chennai Beach
BBOX = (12.90, 80.09, 13.10, 80.30)
LAT, LON = 13.08, 80.27
HISTORY_DAYS = 92

REQUIRED = {
    "gtfs": RAW_DIR / "chennai-unified-gtfs.zip",
    "osm_stops": RAW_DIR / "osm_bus_stops.json",
    "osm_poi": RAW_DIR / "osm_poi.json",
    "weather": RAW_DIR / "weather_hourly.csv",
    "holidays": RAW_DIR / "holidays_tn.csv",
}
# OSM has a documented fallback (GTFS stop list + manual weights by stop type, section 3 rows 2/12).
# Its absence is reported loudly but does not fail the run unless --strict is given.
HAS_FALLBACK = {"osm_stops", "osm_poi"}


def fetch_gtfs(force: bool) -> None:
    path = REQUIRED["gtfs"]
    if force or not path.exists():
        print(f"[gtfs] downloading {GTFS_URL}")
        r = requests.get(GTFS_URL, timeout=180)
        r.raise_for_status()
        path.write_bytes(r.content)
    out = RAW_DIR / "gtfs"
    out.mkdir(exist_ok=True)
    with zipfile.ZipFile(path) as z:
        z.extractall(out)
        for name in ("routes.txt", "stops.txt", "trips.txt", "stop_times.txt"):
            with z.open(name) as f:
                n = sum(1 for _ in io.TextIOWrapper(f, encoding="utf8")) - 1
            print(f"[gtfs] {name}: {n:,} rows")


def overpass(query: str) -> dict:
    last = None
    for url in OVERPASS_URLS:
        try:
            r = requests.post(url, data={"data": query}, headers=HEADERS, timeout=240)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # try the mirror
            last = e
            print(f"[osm] {url} failed: {e}")
    raise RuntimeError(f"Overpass unavailable: {last}")


def fetch_osm(force: bool) -> None:
    s, w, n, e = BBOX
    bb = f"{s},{w},{n},{e}"
    if force or not REQUIRED["osm_stops"].exists():
        q = f"""[out:json][timeout:180];
        (node["highway"="bus_stop"]({bb}); node["public_transport"="platform"]({bb});
         relation["route"="bus"]({bb}););
        out tags center;"""
        data = overpass(q)
        REQUIRED["osm_stops"].write_text(json.dumps(data), encoding="utf8")
    data = json.loads(REQUIRED["osm_stops"].read_text(encoding="utf8"))
    els = data.get("elements", [])
    print(f"[osm] bus stops/platforms: {sum(1 for x in els if x['type']=='node'):,}; "
          f"bus route relations: {sum(1 for x in els if x['type']=='relation'):,}")

    if force or not REQUIRED["osm_poi"].exists():
        q = f"""[out:json][timeout:180];
        (nwr["office"]({bb}); nwr["amenity"~"^(college|university|hospital|school|marketplace|bus_station)$"]({bb});
         nwr["shop"="mall"]({bb}); nwr["railway"="station"]({bb}););
        out tags center;"""
        data = overpass(q)
        REQUIRED["osm_poi"].write_text(json.dumps(data), encoding="utf8")
    data = json.loads(REQUIRED["osm_poi"].read_text(encoding="utf8"))
    print(f"[osm] POIs: {len(data.get('elements', [])):,}")


def fetch_weather(force: bool) -> None:
    path = REQUIRED["weather"]
    if force or not path.exists():
        url = ("https://api.open-meteo.com/v1/forecast"
               f"?latitude={LAT}&longitude={LON}&hourly=precipitation,temperature_2m"
               f"&past_days={HISTORY_DAYS}&forecast_days=7&timezone=Asia%2FKolkata")
        print("[weather] Open-Meteo forecast API (past + next 7 days)")
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        h = r.json()["hourly"]
        df = pd.DataFrame({"ts": h["time"], "precip_mm": h["precipitation"], "temp_c": h["temperature_2m"]})
        df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize("Asia/Kolkata")
        df.to_csv(path, index=False)
    df = pd.read_csv(path)
    print(f"[weather] hourly rows: {len(df):,} ({df.ts.iloc[0]} .. {df.ts.iloc[-1]}), "
          f"total precip {df.precip_mm.sum():.0f} mm")


def fetch_holidays(force: bool) -> None:
    import holidays

    path = REQUIRED["holidays"]
    if force or not path.exists():
        today = date.today()
        years = sorted({(today - timedelta(days=HISTORY_DAYS + 10)).year, today.year, today.year + 1})
        tn = holidays.country_holidays("IN", subdiv="TN", years=years)
        df = pd.DataFrame(sorted(tn.items()), columns=["date", "name"])
        df.to_csv(path, index=False)
    df = pd.read_csv(path)
    print(f"[holidays] Tamil Nadu holidays: {len(df)} rows")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--skip-osm", action="store_true", help="skip Overpass (slow); stop weights fall back")
    ap.add_argument("--strict", action="store_true", help="treat missing OSM data as an error too")
    args = ap.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    steps = [("gtfs", fetch_gtfs), ("weather", fetch_weather), ("holidays", fetch_holidays)]
    if not args.skip_osm:
        steps.insert(1, ("osm", fetch_osm))
    failures = []
    for name, fn in steps:
        try:
            fn(args.force)
        except Exception as e:
            failures.append(f"{name}: {e}")
            print(f"[{name}] FAILED: {e}", file=sys.stderr)

    missing = [k for k, p in REQUIRED.items() if not p.exists()]
    fallback = [k for k in missing if k in HAS_FALLBACK and not args.strict]
    missing = [k for k in missing if k not in fallback]
    failures = [f for f in failures if not (f.startswith("osm") and fallback)]
    if fallback:
        bar = "!" * 72
        print(f"\n{bar}\nFALLBACK IN USE: OpenStreetMap/Overpass data missing ({', '.join(fallback)}).\n"
              "Stop demand weights will use manual weights by stop type (see ASSUMPTIONS.md).\n"
              f"Re-run later or pass --strict to make this an error.\n{bar}")
    if missing or failures:
        print("\nERROR: required inputs missing: " + ", ".join(missing or []) +
              ("\n  " + "\n  ".join(failures) if failures else "") +
              "\nSee ASSUMPTIONS.md for the fallbacks (manual stop weights for OSM, synthetic rain calendar).",
              file=sys.stderr)
        return 1
    print("\nRequired inputs present in data/raw/" + (" (with OSM fallback)." if fallback else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
