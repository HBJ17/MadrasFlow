# Impact summary (simulated)

Generated 2026-10-02T13:39:41 by `python -m advisory.impact` over 3 simulated weekdays. **Simulated data.**

| Metric (MTC routes in the twin, per day) | Baseline | With advisories | Change |
|---|---|---|---|
| CROWDED vehicle-stops | 1,138 | 947 | -17% |
| Passengers left behind | 14,324 | 7,404 | -48% |
| Busiest-slot load factor (95th pct of route-slots) | 1.393 | 1.151 | -17% |
| Extra bus-hours required | - | 131.4 | - |
| Extra trips | - | 149.7 | - |

Windows are found on the baseline run itself (perfect foresight), so this is an upper bound on what forecast-driven advisories achieve.