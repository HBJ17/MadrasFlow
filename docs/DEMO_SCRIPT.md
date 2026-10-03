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
3. **Plan a trip**: From defaults to your location (or type Airport); To: Thiruvanmiyur; leave 08:30,
   window **± 15** (tap + for ± 30). Swipe between the 08:15 / 08:30 / 08:45 cards; each lists routes
   ranked by crowd and arrival with Low / Medium / High / Crowded, arrival time, fare and transfers.
   Tap the top one: the map draws it coloured by crowding.
4. **Filters**: untick Bus, or turn on *Women's travel* (bus legs show ₹0) or *Step-free stations*;
   the cards re-rank by themselves. Untick *Crowd* under Rank by to see the fastest-first order.
5. Toggle **தமிழ்** to show Tamil labels. Mention: works offline with a "Last updated" banner.

## 3. Depot dashboard (2 min)
1. **Fleet heatmap**: routes × next 3 hours. Click *95 → Thiruvanmiyur*: **By stop** shows where along the
   route it fills; **By bus** shows each scheduled bus filling up stop by stop.
2. **Recommendations**: filter by kind. An *Add trips* card is twin-tested (before → after); a *Short-turn*
   or *Hold for train* (Guindy) card explains why it was suggested and that it is an estimate. Accept one.
3. **What-if simulator**: tap *Peak boost on 95* (fleet only) → Run (~40 s) → the difference heatmap and
   the cost in bus-hours; *Save to compare*. Clear the fleet, tap *Monsoon morning* (conditions only) → Run
   → Save. The saved-plans table compares the two. Then try *Cyclone day* together with extra buses.
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
