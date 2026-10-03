# Demo script (about 6 minutes)

Start: `python scripts/demo.py --clock 08:15` (morning peak regardless of the real time). Open
`http://127.0.0.1:8000/` on a phone-sized window and `/depot` on a second screen.

## 1. The problem (30 s)
"South Chennai commuters cannot see how crowded the next bus or train is. Metro runs at about a fifth
of its planned ridership while MTC buses on the same corridor are packed at peaks. We forecast crowding
stop by stop and use it to steer both commuters and depots."

Point at the amber **Simulated data** badge: "The data here is simulated. In deployment, these cameras
feed the same pipeline."

## 2. Commuter app (2 min)
1. Home → tap **95** (Tambaram East → Thiruvanmiyur). The vertical crowd strip shows each stop's next
   bus, its ETA and the forecast level with a load %. Toggle **Now / In 30 min / In 1 h**.
2. Tap a red stop → **Next departures** and the **Wait or go?** hint
   ("Next bus in 3 min is CROWDED; the one after in 11 min is MEDIUM. Worth waiting 8 min.").
3. **Plan a trip**: Tambaram West Bus Stand → Thiruvanmiyur. Three cards: Fastest, Least crowded,
   Balanced; expand one to see per-leg crowd bars. Tick **Prefer less crowded** (seniors, women
   travelling alone, luggage) and plan again.
4. Toggle **தமிழ்** to show Tamil labels. Mention: text + colour by default, the map only loads on
   "Show map", works offline with a "Last updated" banner, initial JS ~55 KB.

## 3. Depot dashboard (2 min)
1. **Fleet heatmap**: routes × next 12 slots, coloured by forecast load factor.
2. **Advisories**: "forecast LF 1.24 at Medavakkam for 45 min → add 3 trips 08:00–09:00". The twin
   already tested it: LF before → after, neighbouring routes checked. Accept it.
3. **Scenario panel**: choose *Heavy rain* → Run twin (~30 s) → before/after charts of load factor,
   left-behind passengers and CROWDED vehicle-stops. Then *Cyclone day* (MRTS halted, a quarter of buses
   off the road, as in Cyclone Michaung) to show riders shifting to metro, and *Extra trips* on route 95 in the peak.
4. **Impact**: computed reduction in CROWDED vehicle-stops and left-behind passengers if advisories are
   followed, and the extra bus-hours it costs.

## 4. Cameras (1 min)
Run the vehicle node on a laptop webcam; walk a few people across the line; press Enter to "depart"
the stop. The **Data health** panel shows `+3 −1 → 2 on board` within seconds. "Only counts leave the
device. No images are stored or sent."

## 5. Honesty slide (30 s)
- Calibrated simulation, not a replica: metro anchored to published CMRL totals, MRTS to a 2023 line-wide
  figure; the bus total is an assumption until MTC/CUMTA data is available.
- Forecast accuracy shown is on twin data — it proves the pipeline, not real-world accuracy.
- Camera accuracy was checked on a synthetic clip; occlusion in packed buses will lower it.
