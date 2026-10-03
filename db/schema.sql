-- Canonical schema (spec section 4). SQLite for the demo; types and constraints are kept
-- compatible with Postgres/TimescaleDB (TEXT timestamps are ISO 8601 with +05:30 offset).

-- Static network
CREATE TABLE IF NOT EXISTS stop (
  stop_id TEXT PRIMARY KEY, name TEXT, lat REAL, lon REAL,
  mode TEXT CHECK (mode IN ('bus','mrts','metro')),
  stop_type TEXT,            -- office | college | market | residential | interchange | hospital
  demand_weight REAL DEFAULT 1.0,
  station_id TEXT            -- physical station (stops within 150 m), used for transfers
);
CREATE TABLE IF NOT EXISTS route (
  route_id TEXT PRIMARY KEY, short_name TEXT, mode TEXT, operator TEXT,
  capacity_seated INT, capacity_total INT,   -- per vehicle, from config
  long_name TEXT, depot TEXT
);
CREATE TABLE IF NOT EXISTS route_stop (
  route_id TEXT, direction INT, seq INT, stop_id TEXT,
  dist_from_prev_m REAL, run_min REAL,
  PRIMARY KEY (route_id, direction, seq)
);
CREATE TABLE IF NOT EXISTS trip (
  trip_id TEXT PRIMARY KEY, route_id TEXT, direction INT,
  scheduled_start TIMESTAMP, vehicle_id TEXT
);

-- The contract: one row per vehicle-at-stop visit (or per camera report)
CREATE TABLE IF NOT EXISTS event (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TIMESTAMP NOT NULL,              -- vehicle departure time from the stop (ISO 8601, +05:30)
  slot_15 TIMESTAMP NOT NULL,         -- ts floored to 15 minutes
  route_id TEXT, trip_id TEXT, vehicle_id TEXT, stop_id TEXT NOT NULL,
  direction INT,
  boardings INT DEFAULT 0 CHECK (boardings >= 0), alightings INT DEFAULT 0 CHECK (alightings >= 0),
  onboard_load INT CHECK (onboard_load IS NULL OR onboard_load >= 0),   -- after this stop
  waiting_count INT,                  -- people left at the stop after departure (nullable)
  left_behind INT,                    -- boarders refused due to capacity (twin truth; nullable for cameras)
  payment_mode TEXT,                  -- card | qr | cash | unknown
  fare_inr REAL,
  source TEXT NOT NULL CHECK (source IN ('twin','camera_stop','camera_vehicle','afc_real')),
  scenario_id TEXT,                   -- twin run id
  run_id TEXT,
  client_event_id TEXT                -- idempotency key for ingest (nullable)
);
CREATE INDEX IF NOT EXISTS idx_event_stop_slot ON event(stop_id, slot_15);
CREATE INDEX IF NOT EXISTS idx_event_route_slot ON event(route_id, slot_15);
CREATE INDEX IF NOT EXISTS idx_event_ts ON event(ts);
CREATE UNIQUE INDEX IF NOT EXISTS idx_event_client ON event(client_event_id) WHERE client_event_id IS NOT NULL;

-- Every simulated row is labelled in the database, not only in the UI.
CREATE VIEW IF NOT EXISTS v_event_labelled AS
  SELECT e.*, CASE WHEN e.source = 'twin' THEN 'SIMULATED' ELSE 'OBSERVED' END AS data_label FROM event e;

-- Aggregation used for modelling (section 4 rules)
CREATE VIEW IF NOT EXISTS v_stop_slot AS
  SELECT stop_id, slot_15, SUM(boardings) AS boardings, SUM(alightings) AS alightings,
         MAX(onboard_load) AS max_load, COUNT(*) AS n_events,
         MIN(source) AS source_min, MAX(source) AS source_max
  FROM event GROUP BY stop_id, slot_15;

-- Per (route, direction, stop, slot): max load factor, the predictor's primary target
CREATE VIEW IF NOT EXISTS v_route_stop_slot AS
  SELECT e.route_id, e.direction, e.stop_id, e.slot_15,
         MAX(e.onboard_load) AS max_load, SUM(e.boardings) AS boardings, SUM(e.alightings) AS alightings,
         MAX(e.onboard_load) * 1.0 / r.capacity_total AS max_lf, SUM(COALESCE(e.left_behind,0)) AS left_behind,
         MAX(e.onboard_load + COALESCE(e.left_behind,0)) * 1.0 / r.capacity_total AS demand_lf,
         MAX(e.source) AS source
  FROM event e JOIN route r ON r.route_id = e.route_id
  GROUP BY e.route_id, e.direction, e.stop_id, e.slot_15;

-- Raw camera rows are kept alongside the merged event rows (section 11.4)
CREATE TABLE IF NOT EXISTS camera_raw (
  id INTEGER PRIMARY KEY AUTOINCREMENT, received_at TIMESTAMP, node_id TEXT, source TEXT,
  ts TIMESTAMP, stop_id TEXT, vehicle_id TEXT, route_id TEXT, trip_id TEXT,
  boardings INT, alightings INT, onboard_load INT, waiting_count INT, client_event_id TEXT
);
CREATE TABLE IF NOT EXISTS node_heartbeat (
  node_id TEXT PRIMARY KEY, last_seen TIMESTAMP, battery REAL, fps REAL, kind TEXT
);

-- Context
CREATE TABLE IF NOT EXISTS weather_hourly (ts TIMESTAMP PRIMARY KEY, precip_mm REAL, temp_c REAL);
CREATE TABLE IF NOT EXISTS calendar_day (date DATE PRIMARY KEY, day_type TEXT, is_holiday INT, note TEXT);
CREATE TABLE IF NOT EXISTS city_event (event_name TEXT, start_ts TIMESTAMP, end_ts TIMESTAMP,
                                       stop_id TEXT, expected_attendance INT, multiplier REAL);

-- Predictions
CREATE TABLE IF NOT EXISTS forecast (
  made_at TIMESTAMP, target_slot TIMESTAMP, stop_id TEXT, route_id TEXT,
  model TEXT,                         -- baseline | prophet | lstm
  pred_load REAL, pred_boardings REAL,
  level TEXT, lo REAL, hi REAL,
  direction INT, pred_lf REAL, stale INT DEFAULT 0, data_source TEXT, horizon INT,
  -- direction added to the key: rail stations share one stop_id in both directions
  PRIMARY KEY (made_at, target_slot, stop_id, route_id, direction, model)
);
CREATE INDEX IF NOT EXISTS idx_forecast_route ON forecast(route_id, direction, target_slot);

-- Advisories
CREATE TABLE IF NOT EXISTS advisory (
  advisory_id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TIMESTAMP,
  route_id TEXT, depot TEXT, slot_start TIMESTAMP, slot_end TIMESTAMP,
  reason TEXT, action TEXT, extra_trips INT, expected_lf_before REAL, expected_lf_after REAL,
  direction INT, neighbour_lf_after REAL, extra_vehicle_hours REAL,
  status TEXT DEFAULT 'active' CHECK (status IN ('active','accepted','dismissed','rejected_by_whatif')),
  data_source TEXT,
  kind TEXT DEFAULT 'add_trips'       -- add_trips | short_turn | move_bus | hold_for_train
);

-- Twin runs and unmet demand (logged separately for the pitch)
CREATE TABLE IF NOT EXISTS twin_run (
  run_id TEXT PRIMARY KEY, scenario_id TEXT, created_at TIMESTAMP, status TEXT,
  params TEXT, summary TEXT
);
CREATE TABLE IF NOT EXISTS unmet_demand (
  run_id TEXT, date DATE, slot_15 TIMESTAMP, stop_id TEXT, route_id TEXT, n INT, reason TEXT
);
