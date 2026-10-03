# Twin validation report

Generated 2026-10-02 13:15 by `python -m twin.validate`. **All figures are simulated data.**

Runs: 7 weekdays from 2026-09-21 (5 used) + 2 weekend days, calendar effects off; plus one day each of `cricket_match`, `rain_heavy`, `extra_trips` (6 extra trips per direction on route 95 in peaks) and `metro_disruption`, same seed as the baseline day.
Fitted parameters: `{"base_mode": {"bus": 0.25939415877170185, "mrts": 1.347798442033079, "metro": 2.9131452027766076}, "beta_per_km": 0.135, "peak_width_scale": 1.1}`

## Checks

| Check | Result | Detail |
|---|---|---|
| Load conservation (load_after = load_before + boardings - alightings) | PASS | 0 violations in 151,724 rows |
| No negative loads | PASS | 0 rows |
| Capacity never exceeded | PASS | 0 rows |
| Vehicles empty at terminus | PASS | 0 trips |
| Daily total within 5% of target | PASS | 151,739 vs 147,600 (+2.8%) |
| Weekday/weekend ratio within 10% | PASS | 1.47 vs 1.47 |
| Event-day ratio between 1.1 and 1.3 | PASS | 1.202 |
| Peak-hour share in [0.4, 0.55] (assumption) | PASS | 0.493 |
| Scenario direction: heavy rain increases bus load | PASS | mean bus load x1.085 |
| Scenario direction: extra trips lower load on the target route | PASS | BUS_95 peak mean LF 0.485 -> 0.434; left-behind 3,335 -> 2,860 |
| Scenario direction: metro disruption raises metro load in the window | PASS | metro 08-10 mean LF 0.086 -> 0.127 |

## Daily boardings by mode (weekday mean)

| Mode | Simulated | Target | Error |
|---|---|---|---|
| bus | 24,530 | 24,000 | +2.2% |
| metro | 86,524 | 83,600 | +3.5% |
| mrts | 40,686 | 40,000 | +1.7% |

Unmet demand (gave up after patience / refused twice / end of service): 9,523 per day (7 days incl. weekend); reasons {'patience': 32146, 'refused_twice': 19497, 'end_of_service': 15016}.
CROWDED vehicle-stops per weekday: 1,014. Crowd-level shares over all vehicle-stops: LOW 78%, CROWDED 9%, MEDIUM 8%, HIGH 5%.

## Figures

![hourly profile](figures/hourly_profile_by_stop_type.png)

![LF heatmap](figures/lf_heatmap_bus95_d0.png)

![LF distribution](figures/lf_distribution.png)

## Sanity check against reality

No measured hourly ridership profile for these routes or stations was available to compare against (the CMRL figures used are daily/monthly totals). The peak-hour share band (40-55%) is itself an assumption from the spec. **No claim of a match to real hourly patterns is made.** Bus and MRTS totals are assumptions (see ASSUMPTIONS.md); only the metro total is anchored to published figures, and only through an assumed corridor share.

> A simulation twin calibrated to published ridership totals and designed to ingest real AFC and sensor feeds. Bus-level counts are assumptions until MTC data is available.