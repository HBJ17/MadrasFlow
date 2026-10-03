# Assumptions and fallbacks

Every value the spec marks *assumption* or *verify* lives in a config file with a `# ASSUMPTION`
comment. This file lists them in one place, with the fallbacks used for inputs that could not be
obtained. **Nothing below is a measured fact about Chennai transit unless a source is named.**

## Inputs that fell back (spec section 3)

| # | Input | What happened | Fallback used |
|---|---|---|---|
| 1 | Bus + metro GTFS | Downloaded (community feed `chennai-unified-gtfs.zip`, Ithu Ungal Soththu, version 2025.03.25). License terms of the feed were **not** confirmed. The feed is a merge with ragged rows (CMRL rows have a different column order) and is read with a tolerant parser. | — |
| 2 | OSM bus stops | Overpass API unreachable from the build machine (504 / connection resets on three mirrors). | GTFS stop list for the corridor (the spec's "manual stop list" role). |
| 3 | MRTS timetable | Not in the GTFS feed. | 19 stations hand-coded in `config/corridor.yaml` (Chennai Beach – St. Thomas Mount, including the March 2026 extension), **approximate coordinates** except Puzhuthivakkam and St. Thomas Mount (Wikipedia). 43 train pairs a day (Southern Railway notice, Mar 2026) spread as 15 min peak / 20 min evening / 36–60 min off-peak (the split is an assumption). |
| 4 | Metro timetable | The feed's CMRL trips are schematic (only first/last stop, every 3 h). | Station list and coordinates from the feed; headways hand-coded (5 min peak / 8 min off-peak Blue, 6 / 9 Green). |
| 7 | MTC ridership | No corridor figure found. | Bus target set by what the 4 modelled routes' GTFS timetables can carry (see below). |
| 8 | MTC fares | Only an old city-guide figure (Rs 2 per ~2 km stage). | Configurable fare table, minimum Rs 5. |
| 12 | POIs for stop weights | Overpass unreachable. | Manual weights by stop type (interchange 4, office 3, college 3, market 2.5, hospital 2, residential 1.5; rail stations x2 for wider catchment), stop type from name keywords + overrides. |
| 13 | Population density | Not attempted (needs ward data). | Uniform within catchment, scaled by stop-type weight. |
| 14 | Real AFC sample | Not available. | The twin remains the data source. |

Weather (Open-Meteo, 92 past days + 7 forecast days) and Tamil Nadu holidays (`holidays` package) were downloaded successfully.

## Network (config/corridor.yaml)

- Corridor routes: MTC 51R (Tambaram West–Velachery), 95 (Tambaram East–Thiruvanmiyur), S97 (Guindy Metro–Velachery), M70 CT (Guindy–Thiruvanmiyur); MRTS Chennai Beach–St. Thomas Mount (extended from Velachery on 14 Mar 2026; Puzhuthivakkam modelled, Adambakkam skipped because trains do not stop there yet); Metro Blue Line segment Saidapet–Airport; Green Line segment Ekkattuthangal–St. Thomas Mount.
- 51R: the feed has only the Velachery→Tambaram pattern; the other direction is the reversed pattern, with timetable from the headway profile.
- M70 CT: the feed has only 10 midday trips per direction; timetable from the headway profile (stops and run times from GTFS).
- Guindy metro station (`CMRL_22`): the feed coordinate is ~600 m east of the station; moved next to Guindy railway station so bus–metro transfers work.
- Interchange overrides: Velachery MRTS, Chennai Beach, Park Town, Guindy, Alandur (both lines), St. Thomas Mount (metro and MRTS).
- St. Thomas Mount MRTS (`MRTS_STM`): placed ~100 m from the metro station so the integrated MRTS/metro terminal counts as one station; Wikipedia's coordinate (12.9947, 80.1989) is the suburban platform ~700 m away, which would put the transfer outside the 400 m walk limit. Assumption.
- The 2 Beach–Velachery and 3 Velachery–St. Thomas Mount short workings are not modelled; all MRTS trips run end to end.
- Vehicle capacities (seated / total incl. standing): MTC ordinary 48 / 83 (RTO permitted load, per Wikipedia's MTC article; peak-hour buses are reported carrying over 160, which the twin does not allow — riders beyond 83 are left behind and counted in the demand load factor), AC 38 / 55, MRTS 9-car 1,000 / 2,500, CMRL 3-car 350 / 1,100. AC, MRTS and metro: **verify.**
- Dwell: bus `10 + 1.5·boarders + 1.0·alighters` s; rail `25 + 0.4·b + 0.4·a` s (from the spec).
- Fallback bus speed 18 km/h where GTFS run times are missing; road distance = 1.25 × straight line; MRTS 32 km/h, metro 34 km/h average.
- Stops within 150 m are one physical station; walking transfers up to 400 m at 4.5 km/h with a 4-minute transfer penalty (spec).
- Route → depot mapping (51R Tambaram, 95 Thiruvanmiyur, S97 Velachery, M70 Adyar): **not confirmed**.
- Truncated metro lines: trips that continue beyond the modelled segment are represented by extra demand weight (×6) at the segment's boundary stops (Saidapet, Ekkattuthangal).

## Demand (config/demand.yaml, fitted values in config/demand_fitted.yaml)

- Production profiles by stop type (two Gaussian peaks + base per type) follow the spec's peak windows; weekend/holiday total ×0.68, peaks 75 min later and 1.6× wider.
- Destination attraction by stop type, AM vs PM (e.g. office 2.2 AM / 0.6 PM, residential 0.6 / 2.0) — makes demand direction-aware.
- Rail riders may finish by share-auto / auto / walk instead of transferring to a bus: an egress option within 3 km of the destination station, priced at 4 min wait + 15 km/h + Rs 10 + Rs 4/km (detour ×1.3). The egress itself is not simulated, but it is in the logit — without it every rail rider bound for a bus-only area was forced onto the four modelled buses.
- Gravity `exp(−β·km)`, trips under 1 km excluded. β fitted to 0.135/km (start 0.12).
- Per-mode production scale (`base_mode`) fitted by calibration (see `config/demand_fitted.yaml`).
- Logit coefficients from the spec. The crowd penalty uses levels numbered LOW=0 … CROWDED=3, so `max(0, level−1)` penalises HIGH (1.5) and CROWDED (3.0) only. Mode constants: bus 0, MRTS −0.3, metro +0.2.
- Arrivals: negative binomial, dispersion k = 8; day-level lognormal noise σ = 0.04.
- Payment shares: metro 94% card / 5.5% QR / 0.5% cash (Aug 2026 CMRL mix); MRTS 15/35/50 and bus 10/20/70 (assumed). An event row carries the dominant payment mode of its boarders and the sum of their fares.
- Patience: lognormal, mean 15 min, counted from the end of one scheduled headway (people time their arrival to the timetable, so waiting one full headway is expected). Refused twice or out of patience → switch route/mode with probability 0.6 if an alternative exists, else unmet demand.
- Weather: a day with ≥ 20 mm precipitation (05–23 h) uses the `rain_heavy` effects; 5–20 mm uses light-rain multipliers (bus ×1.05, rail ×1.03, run time ×1.10).
- Operations: exponential dispatch delay (bus 2 min, MRTS 1.5, metro 0.3 mean); lognormal run-time noise (σ bus 0.12, MRTS 0.05, metro 0.03); bus traffic factors by time of day (0.85 early morning … 1.45 evening peak).

## Calibration targets (config/calibration_targets.yaml)

- Metro anchors are published (CMRL via DT Next and press, Feb/Jul/Aug 2026).
- Corridor metro share = 10 of 41 stations, equal weights → 0.244 × 342,702 ≈ **83,600 boardings/day** (assumption).
- MRTS **100,000/day**: the whole line is modelled, so the target is the line-wide figure of about 1 lakh/day (Wikipedia, Chennai MRTS, 2023). It predates the March 2026 extension, so it is probably conservative.
- MRTS station checks, reported in `reports/twin_validation.md` but not fitted: Velachery ~70,000/day (Wikipedia, 2026; no source cited there) and Beach + Thirumayilai + Velachery ≈ 40% of MRTS ridership (Wikipedia, 2012 figure).
- Bus **24,000/day**: assumed. The 4 modelled routes stand in for many parallel route variants that are not modelled, so their target is what their GTFS timetables can carry — busiest slots at a demand load factor of about 1.3–1.4 rather than overloaded all day — not the 70:30 bus:rail split. Chosen with `scripts/dev/bus_sweep.py`. The twin still reports ~10,000 trips/day that give up (mostly rail riders waiting for a sparse feeder bus at Guindy, Little Mount, Kasturba Nagar and Velachery); read it as "these four timetables are overloaded at feeder stops", not as a corridor-wide statistic.
- Peak hours 07–10 and 17–20 (press reports on MTC/MRTS crowding; the spec used 08–10). Peak-hour share band 45–60 %: the spec's 40–55 % band for 08–10 + 17–20, widened by 5 points for the extra hour (assumption).
- Weekday/weekend ratio 1.47 (= 1/0.68), event-day ratio 1.2: assumptions from the spec.

## Scenarios (config/scenarios.yaml)

- Heavy rain: bus demand ×1.15, metro/MRTS ×1.10, run times ×1.25, bus dispatch delay ×1.5 (spec values, assumptions).
- Cricket match at Chepauk: 35,000 attendance, catchment 20,000 → surge factor 2.75 at the venue for 2 h before / 1 h after, day total ×1.2; match 15:30–19:00 (so the after-surge falls inside service hours).
- College reopening ×1.5 at college stops; metro disruption doubles metro headways 08:30–10:00.
- Cyclone day (Cyclone Michaung pattern, Dec 2023: MTC suspended 1,000+ of ~3,861 buses, MRTS halted, metro kept running): MRTS suspended all day, bus trips ×1/1.35 (~26% cancelled), day total ×0.75, metro preference ×1.25, bus run times ×1.5 (heavy rain is reported to add 20–50 min to bus journeys), bus dispatch delay ×2. The halt and the bus cut follow the press reports; the multipliers are assumptions.
- `data/events.csv` is a hand-made illustrative calendar (12 rows); dates and attendances are not verified.

## Trip planner filters (config/accessibility.yaml)

- Step-free access: metro stations assumed step-free (lifts and ramps); MRTS stations assumed not step-free. Per-stop corrections can be added once verified.
- Low-floor buses: no route-level data, so every MTC route is "unknown". An accessible plan may still use a bus but is flagged "low-floor bus not guaranteed".
- Women's option: bus fare ₹0 on the four modelled MTC ordinary routes (Vidiyal Payanam since 2021, extended as Vettri Payanam from 2 Oct 2026); MRTS and metro fares unchanged. After dark (19:00–06:00) walks are capped at 5 min and waits at 10 min (thresholds are assumptions).

## Forecasting, routing, advisories

- **Target = demand load factor** `(onboard + left_behind) / capacity_total`. Onboard alone can never exceed capacity, so it cannot express "LF 1.3"; adding the people left behind does. CROWDED (≥ 1.0) therefore means "left full with people still waiting".
- Weather-forecast features use the recorded weather for twin data (a perfect forecast); deployment would use the Open-Meteo forecast.
- Live correction gains: camera vehicle 0.5, camera stop 0.3, twin stream 0.6, AFC 0.7; ρ = 0.7; correction applied to the observed stop and 3 downstream stops for 3 slots.
- Routing crowd penalty f = {LOW 0, MEDIUM 1, HIGH 3, CROWDED 8} min per ride segment (spec); missed-vehicle penalty = 50 % × gap to the following vehicle when the next is CROWDED.
- Advisories: required vehicles at target LF 0.85 (spec); "peak LF" in what-if comparisons = 90th percentile of vehicle-stop demand LF in the window; neighbouring routes = routes sharing a station.
- Impact summary: overloaded windows found on the baseline run itself (perfect foresight) → an upper bound.
- Forecast table key includes `direction` (rail stations share one stop_id in both directions) — a small extension of the spec's key.
