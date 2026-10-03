# Impact summary (simulated)

Generated 2026-10-03T06:32:38 by `python -m advisory.impact` over 3 simulated weekdays. **Simulated data.**

| Metric (MTC routes in the twin, per day) | Baseline | With advisories | Change |
|---|---|---|---|
| CROWDED vehicle-stops | 889 | 701 | -21% |
| Passengers left behind | 8,494 | 4,625 | -46% |
| Busiest-slot load factor (95th pct of route-slots) | 1.217 | 1.091 | -10% |
| Extra bus-hours required | - | 74.7 | - |
| Extra trips | - | 77.0 | - |

Windows are found on the baseline run itself (perfect foresight), so this is an upper bound on what forecast-driven advisories achieve.