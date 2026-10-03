# Known limits

Requirements that are not fully met, and why. Nothing here was silently dropped.

## Data
- **OpenStreetMap / Overpass** (inputs 2 and 12) was unreachable from the build machine (504 and
  connection resets on three public mirrors). Stop demand weights use the documented fallback
  (manual weights by stop type). `python data/fetch_data.py` retries and `--strict` makes it fatal;
  if `data/raw/osm_poi.json` appears, `simulation/twin/network.py` uses POI counts automatically.
- **GTFS licence** of the community feed was not confirmed (the spec flags it as IIITD licence — check terms).
- The feed's CMRL trips are schematic (first/last stop only), so metro timetables are hand-coded headways.
  MRTS is not in the feed at all; its station coordinates are approximate.
- Suburban rail (Beach–Tambaram line, ~1.44 lakh/day at Tambaram) is not modelled, so riders who
  reach St. Thomas Mount, Guindy or Tambaram by suburban train are missing from station footfall.
- The twin caps buses at their permitted load (83). Real peak buses carry 160+; those riders appear as
  left-behind demand instead of as an overloaded bus.
- Only 4 MTC routes are modelled; real corridor bus supply is spread over many route variants and
  feeder services. The modelled routes are therefore overloaded at rail feeder stops in the peaks, and
  the twin reports about 10,000 trips/day that give up. Treat bus-level numbers as illustrative.

## Trip planner and depot tools
- Step-free access and low-floor buses come from an assumption table (`config/accessibility.yaml`), not
  surveyed station or fleet data.
- The planner snaps the user's position to the nearest stop and adds a straight-line walk estimate; it does
  not route along streets.
- Only add-trips advisories are tested in the twin. Short-turn reuses that test (the twin cannot run partial
  trips), move-a-bus estimates the quiet route's load from the forecast, and hold-for-train is untested.
- A what-if compares one simulated day with one baseline day; hour-level differences under about 10 load-%
  points are within that run-to-run noise, so the difference view only colours larger changes.

## Twin
- Commuters are lightweight records driven by a dispatcher process, not one SimPy process each
  (`simulation/twin/agents.py` explains why: ~150k commuters/day must simulate in seconds). Behaviour follows
  the spec (FIFO boarding up to capacity, patience, refused-twice switching, transfers).
- Truncated metro segments: through-passengers from beyond Saidapet/Ekkattuthangal appear as boardings
  at the boundary station rather than arriving already on board.
- Trip-level payment: the event table holds one row per vehicle-stop visit, so `payment_mode` is the
  dominant mode among that visit's boarders and `fare_inr` is their total.
- No measured hourly profile was available, so the "sanity check against reality" in the validation
  report states that no match is claimed.

## Forecasting
- Accuracy is measured on twin data only.
- Weather "forecast" features use recorded weather (a perfect forecast) when training on twin data.
- Prophet is fitted per route-direction on the route-mean load factor, with stop-level forecasts from
  learned stop share profiles (the spec allows per-route groups); it has no boardings model.
- The LSTM is trained on CPU with 120k sampled windows per epoch (peak slots weighted ×2) and early
  stopping, not on every window.
- The optional M2 graph model (temporal GCN) was not built (spec: skip unless M1 is done — M1 is done,
  M2 was left out for time).

## Camera pipeline
- `reports/camera_accuracy.md` was produced on a **synthetic** clip (person cut-outs from Ultralytics'
  sample photos composited onto a background with exact ground truth). It proves the YOLO + ByteTrack +
  line-counter pipeline end to end, but it is not a real doorway measurement. Record a clip, count it by
  hand, and run `python -m camera.accuracy --clip … --truth …` for a real number.
- The live "20–30 people through a doorway" demo needs a webcam; it was not run on the build machine.
- GPS stop matching is implemented as a function (`gps_stop_match`) but there is no GPS hardware
  integration; the demo uses keypress stop attribution as the spec allows. MQTT transport is not wired
  (HTTP only).

## API / web
- Rate limiting and run state for `/twin/run` are in-process (single API worker).
- `/twin/whatif` runs two twin days synchronously (~15–30 s); the dashboard shows progress for
  `/twin/run`, which is asynchronous.
- ETAs come from the timetable plus the last reported stop of each trip (AVL-style), not from GPS.
- Lighthouse 11 (mobile) was run on the home and route pages: performance 99, accessibility 100,
  best practices 100, PWA 100 (`reports/lighthouse*.report.html`). Offline was checked by stopping the
  server and reloading a route page (cached strip + "Offline · last updated" banner). The commuter
  app's initial JS is ~55 KB gzipped against a 150 KB budget. The "last updated" time is wall-clock
  time even when the demo clock (`--clock`) is shifted.
- The Docker image builds and runs the full rebuild, the test suite and the smoke test (2026-10-03).
  `docker compose up` on a fresh machine, with no host data, was not tested end to end.
- "Check Rapido" on a route opens Rapido's mobile web app for the first and last mile: drop = the
  trip's first stop (pickup left blank), or pickup = the last stop (drop left blank). It uses an
  undocumented link (`m.rapido.bike/unup-home/seo/<pickup>/<drop>?version=v3`, the one Rapido's own
  route pages use; a blank side is sent as four spaces). Rapido geocodes the stop names and takes the
  first match; it may change without notice, and booking needs a Rapido login. No Rapido API or fare
  data is used.
