# MadrasFlow — Public Transport Occupancy Predictor (South Chennai)

A crowd-forecasting platform for one South Chennai corridor — **Tambaram · Velachery · Thiruvanmiyur**
with the Guindy / St. Thomas Mount interchange — covering MTC buses, MRTS (Chennai Beach–St. Thomas Mount)
and Chennai Metro. A calibrated **digital twin** (SimPy) produces the demo data; a **two-camera
computer-vision pipeline** is the real-world collection method. Both write the same event table, so
every downstream module is source-agnostic.

> **The data here is simulated. In deployment, these cameras feed the same pipeline.**
> Every simulated row carries `source='twin'`, the database labels it `SIMULATED` (`v_event_labelled`),
> and the UI shows a "Simulated data" badge wherever a number derives from twin rows.

| Solution point | Where |
|---|---|
| 1. Historical + live crowd forecasting | `predictor/` — B0 same-time-last-week, Prophet, PyTorch LSTM (quantiles), live correction |
| 2. Stop-by-stop occupancy indicators | `GET /occupancy/route/{id}` + crowd strip in the PWA |
| 3. Multi-modal route recommendations | `routing/` — crowd-aware NetworkX graph, Fastest / Least crowded / Balanced |
| 4. Depot-level frequency advisories | `advisory/` — detect → propose → verify with the twin (what-if) |
| 5. Public web/mobile portal | `frontend/` — React PWA, low-bandwidth by default, English + Tamil, offline cache |

## Quick start

Requirements: Python 3.11, Node 18+ (for the web app). Windows commands shown; on Linux/macOS use
`.venv/bin/python`.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

```bash
.venv/Scripts/python scripts/demo.py
```

`scripts/demo.py` builds whatever is missing (data → DB → 90-day history → models → impact → web
build) and then serves everything on <http://127.0.0.1:8000>: commuter app at `/`, depot dashboard
at `/depot`, API docs at `/docs`. To show the morning peak at any hour, run the demo clock from 08:30:

```bash
.venv/Scripts/python scripts/demo.py --clock 08:30
```

Docker alternative: `docker compose up --build` (first start prepares data inside the `data/` volume).

## Step by step (build order of the spec)

| Phase | Command | Output / acceptance |
|---|---|---|
| 0 | `python data/fetch_data.py` | GTFS, weather, holidays in `data/raw/` with row counts (OSM falls back loudly if Overpass is down) |
| 1 | `python -m db.seed` | `data/transit.db`; every `route_stop.stop_id` exists in `stop` |
| 2 | `uvicorn api.main:app --port 8000` | `/health`, `/routes`, `/stops`, `/ingest/events` |
| 3–4 | `python -m twin.simulate --start 2026-09-30 --days 1` | one corridor-day in ~15 s; scenarios via `--scenario rain_heavy` … |
| 5 | `python -m twin.calibrate` then `python -m twin.validate` | `config/demand_fitted.yaml`, `reports/twin_validation.md` |
| 6 | `python -m twin.generate --days 90 --verify` | 90 days in ~90 s on 16 cores, parquet + DB, same seed ⇒ identical |
| 7 | `python -m predictor.evaluate` | `ml/models/lstm_v1.pt`, `ml/models/prophet_v1.pkl`, `reports/forecast_eval.md` |
| 8 | `python -m predictor.serve` (also every 5 min in the API) | rows in `forecast`; `/occupancy/*`, `/forecast`, `/history`, `/wait-or-go` |
| 9 | `POST /api/v1/plan/window` (`/plan` for a single time) | ranked itineraries for every 15-min slot in depart ± window, with filters (modes, walk, fare, transfers, step-free, women's travel) and ranking (crowd + arrival by default); `GET /stops/nearest` turns GPS into a stop |
| 10 | `python -m advisory.headway`, `python -m advisory.impact` | add-trips advisories verified by twin what-if, plus short-turn, move-a-bus and hold-for-train rules; `GET /fleet/heatmap[/{route}?view=stops\|buses]`; `POST /twin/run` with `scenario: builder`; `reports/impact_summary.md` |
| 11–12 | `cd frontend && npm install && npm run build` | PWA in `frontend/dist` (served by FastAPI) |
| 13 | `python -m camera.vehicle_node …`, `python -m camera.accuracy` | counts posted to `/ingest/events`; `reports/camera_accuracy.md` |

After changing a model or config, `bash scripts/rebuild_all.sh` re-runs calibration → seed →
validation → 90-day history → training → impact in order (log in `reports/rebuild_log.txt`; set
`CALIBRATE=""` for a full recalibration instead of the default per-mode refit).

Tests: `python -m pytest -q` (isolated test DB). End-to-end: `bash scripts/smoke.sh` (or
`python scripts/smoke.py`) starts the API, runs a 1-day twin, trains a tiny model, hits every
endpoint and exits non-zero on any failure. It uses `data/smoke/`, so real models and reports are
untouched.

## Architecture

```
GTFS + weather + holidays + events          camera nodes (stop, vehicle) — counts only
            │                                         │  POST /ingest/events (X-API-Key)
            ▼                                         ▼
     twin/ (SimPy) ── events ──────────────►  event table (SQLite; Postgres/Timescale-compatible)
            ▲                                         │
            │ what-if (public run())                  ├─► predictor/  B0 · Prophet · LSTM · live correction ─► forecast
            │                                         ├─► routing/    crowd-aware multimodal graph
     advisory/ ◄──────────── forecast ────────────────┘   advisory/   detect → propose → verify
                                                      ▼
                                FastAPI /api/v1  ──►  frontend/ commuter PWA  +  /depot dashboard
```

- **Twin** (`twin/`): vehicles are SimPy processes running the GTFS timetable (or headway profiles);
  commuters are generated top-down (daily totals → stop-type 15-min profiles → negative-binomial
  arrivals → gravity destinations) and choose route/mode by multinomial logit using the crowding
  observed so far. Capacity limits produce crowding, left-behind passengers and unmet demand —
  nothing about crowding is sampled. `run(config, scenario, start_date, days, seed)` is deterministic.
- **Streaming mode**: at API start, today is simulated once and its events are released into the
  event table as the clock passes them, so forecasts, live correction and dashboards behave as with a
  live feed.
- **Predictor**: a dense (series × 15-min slot × 52 features) panel straight from the DB; target is
  the demand load factor `(onboard + left behind) / capacity`. The LSTM sees 6 h of history and
  predicts 3 h (12 slots) as q10/q50/q90. The API only reads forecast rows; models never run inside
  a request.
- **Trip planner** (`backend/routing/window.py`, `/plan`): from the user's location (nearest stop) or a typed stop, every
  15-minute departure in a ± window is planned; results show one card per slot with ranked routes (crowd level,
  arrival, fare, transfers, walking) and the chosen route on a crowd-coloured map. Filters and ranking criteria
  re-plan automatically; accessibility and fare-concession rules are in `config/accessibility.yaml`.
- **Depot tools** (`/depot`): fleet heatmap with drill-down by stop and by bus; recommendations read from the
  heatmap (add trips, short-turn, move a bus, hold for train); accepting one tests all accepted changes
  together in the twin and the heatmap's *With accepted changes* view shows the result (changed cells
  outlined, Undo on the card); a what-if simulator whose conditions panel (day,
  weather, events, disruptions, demand) and fleet plan panel (extra buses per route and hour) can run alone or
  together, with before / after / difference heatmaps and saved plans to compare.
- **Camera pipeline**: YOLOv8n + ByteTrack, a counting line at the door (vehicle node) and a waiting
  zone (stop node). The two nodes never talk to each other or to the twin; the backend joins them by
  `stop_id` + time (±60 s) and estimates left-behind when the vehicle leaves ≥ 90 % full.

## Camera demo

```bash
.venv/Scripts/python -m pip install -r ml/camera/requirements.txt
export PYTHONPATH=backend:database:ml:simulation
.venv/Scripts/python -m camera.stop_node --source 0 --stop-id MRTS_VLCY --show
.venv/Scripts/python -m camera.vehicle_node --source 0 --vehicle-id DEMO-V1 --route-id MRTS_BV --direction 1 --stops MRTS_VLCY,MRTS_PRGD,MRTS_TRMN --show
```

Walk people across the vertical line in the vehicle node's preview, then press Enter in its terminal
to "depart" the next stop; the counts appear under `camera_recent` in `GET /api/v1/health` within a
couple of seconds. Set `CAMERA_API_KEY` on both the API and the nodes (default
`dev-key` is for local demos only). Nodes buffer to SQLite when offline and retry with back-off.

**Privacy:** frames are processed in memory and discarded; only counts leave the device. No images
or video are stored or transmitted (the ingest schema has no binary fields and rejects unknown
fields), no face recognition, no re-identification beyond within-clip track IDs.

Web checks: Lighthouse 11 mobile scores 99 / 100 / 100 / 100 (performance, accessibility, best
practices, PWA) on the home and route pages; to re-run:

```bash
npx lighthouse@11.7.1 http://localhost:8000/ --form-factor=mobile --only-categories=pwa,accessibility,performance,best-practices --view
```

## Reports (generated by real runs, not hand-written)

- `reports/twin_validation.md` — conservation, capacity, totals vs targets, ratios, scenario directions, figures
- `reports/forecast_eval.md` — MAE/RMSE, level accuracy, macro-F1, CROWDED recall, interval coverage, vs B0 and Prophet
- `reports/camera_accuracy.md` — precision/recall of entries and exits
- `reports/impact_summary.md` — CROWDED vehicle-stops, left-behind and peak LF, baseline vs advised

## What to say honestly in the pitch

- The twin is a calibrated simulation, not a replica of the real network. Metro totals are anchored to
  published CMRL figures through an assumed corridor share; the MRTS total uses a 2023 line-wide
  figure (about 1 lakh/day); **the bus total is an assumption** until MTC/CUMTA data is available. See `ASSUMPTIONS.md`.
- Forecast accuracy is measured on twin data: it shows the pipeline works, not real-world accuracy.
- The camera system is a prototype proving the method on two cameras. Its accuracy report was run on a
  synthetic clip; a real doorway recording is needed for a real number, and occlusion in packed
  vehicles will lower it.
- Only counts leave the device.
- Context: CMRL actual ridership is about 3.14 lakh/day against a DPR projection of 15.69 lakh/day for
  2026 (DT Next) — about 20 % of plan.

See `KNOWN_LIMITS.md` for what is not done or not met.

## Project structure

```
transit-twin/
├── frontend/          React + Vite + TypeScript PWA (commuter app at /, depot dashboard at /depot)
├── backend/
│   ├── api/           FastAPI app: main.py, models.py, routes_*.py, live.py, jobs.py
│   ├── routing/       trip planner: graph.py, recommend.py, window.py, filters.py, ranking.py
│   ├── advisory/      depot advisories, what-if and impact: headway.py, rules.py, whatif.py, impact.py
│   └── common/        shared config loader and clock
├── database/
│   └── db/            schema.sql, seed.py, database.py
├── ml/
│   ├── predictor/     crowd forecasting: features, Prophet baseline, LSTM, live correction, evaluation
│   ├── camera/        YOLOv8n people counter (stop and vehicle nodes) + its requirements.txt
│   └── models/        trained weights: lstm_v1.pt, prophet_v1.pkl, yolov8n.pt (generated, not committed)
├── simulation/
│   └── twin/          digital twin: network, demand, agents, scenarios, simulate, calibrate, validate
├── config/            YAML settings (corridor, demand, scenarios, predictor, accessibility)
├── data/              fetch_data.py, events.csv, raw/ and processed/ (generated, not committed)
├── scripts/           demo.py, smoke.py, rebuild_all.sh
├── tests/             pytest suites
├── docs/              demo script
└── reports/           generated reports and figures
```

Python packages keep short names (`api`, `routing`, `db`, `predictor`, `twin`, ...); their parent folders
`backend/`, `database/`, `ml/` and `simulation/` are on `PYTHONPATH`. Docker, the Makefile, the scripts and
pytest set it for you; to run a module by hand, set it first:

```bash
export PYTHONPATH=backend:database:ml:simulation
```
