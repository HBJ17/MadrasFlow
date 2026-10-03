# Forecast evaluation

Generated 2026-10-03 06:31 by `python -m predictor.evaluate` on the held-out test period.

> **Results are on twin (simulated) data.** They show how well the models learn the simulator and that the pipeline works end to end, not real-world accuracy. Real accuracy needs real AFC or sensor data, which the schema is built to accept.

Split (time-based): train 2026-07-05 .. 2026-09-02 (first 7 days warm up lags), validation 2026-09-03 .. 2026-09-17, test 2026-09-18 .. 2026-10-02.
Target: max demand load factor per (route, direction, stop, 15-min slot), evaluated only on slots where a vehicle departed. 221 series. Models: B0 = same time last week; Prophet = per route-direction with stop share profiles; LSTM = 2x128, 24-slot window, 12-slot quantile head.

## Acceptance: LSTM beats B0 on 1-hour MAE at peak slots: **PASS** (LSTM 0.0680 vs B0 0.0854, +20.4%)

## Load factor and boardings

| Horizon | Segment | Model | n | MAE LF | RMSE LF | MAE board | RMSE board | Level acc | Macro-F1 | CROWDED recall | CROWDED precision | 80% band coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15 min | all | b0 | 146,052 | 0.0704 | 0.1282 | 8.0976 | 23.2855 | 87.2% | 0.6490 | 73.3% | 71.0% | - |
| 15 min | all | prophet | 146,052 | 0.0600 | 0.1044 | - | - | 87.3% | 0.6436 | 49.0% | 78.4% | 67.8% |
| 15 min | all | lstm | 146,052 | 0.0544 | 0.0930 | 6.4075 | 17.2082 | 88.9% | 0.7073 | 60.2% | 88.4% | 82.9% |
| 1 h | all | b0 | 142,985 | 0.0714 | 0.1294 | 8.1447 | 23.4170 | 86.9% | 0.6492 | 73.5% | 71.1% | - |
| 1 h | all | prophet | 142,985 | 0.0607 | 0.1053 | - | - | 87.1% | 0.6443 | 49.4% | 78.5% | 67.3% |
| 1 h | all | lstm | 142,985 | 0.0620 | 0.1071 | 6.5506 | 17.5729 | 88.0% | 0.7008 | 70.6% | 83.0% | 80.7% |
| 3 h | all | b0 | 128,056 | 0.0727 | 0.1312 | 8.2062 | 23.7679 | 86.7% | 0.6496 | 73.4% | 71.1% | - |
| 3 h | all | prophet | 128,056 | 0.0617 | 0.1065 | - | - | 86.9% | 0.6459 | 49.5% | 78.7% | 66.6% |
| 3 h | all | lstm | 128,056 | 0.0669 | 0.1166 | 6.6435 | 17.8877 | 87.4% | 0.6910 | 76.6% | 77.3% | 80.8% |
| 15 min | peak | b0 | 46,506 | 0.0854 | 0.1515 | 11.5555 | 31.4882 | 84.4% | 0.6442 | 78.2% | 74.9% | - |
| 15 min | peak | prophet | 46,506 | 0.0762 | 0.1258 | - | - | 83.1% | 0.6182 | 50.2% | 80.0% | 55.5% |
| 15 min | peak | lstm | 46,506 | 0.0612 | 0.1028 | 8.1769 | 21.3731 | 87.3% | 0.7203 | 69.5% | 90.9% | 82.5% |
| 1 h | peak | b0 | 46,506 | 0.0854 | 0.1515 | 11.5555 | 31.4882 | 84.4% | 0.6442 | 78.2% | 74.9% | - |
| 1 h | peak | prophet | 46,506 | 0.0762 | 0.1258 | - | - | 83.1% | 0.6182 | 50.2% | 80.0% | 55.5% |
| 1 h | peak | lstm | 46,506 | 0.0680 | 0.1148 | 8.2701 | 21.5320 | 86.5% | 0.7084 | 73.6% | 87.7% | 80.0% |
| 3 h | peak | b0 | 46,506 | 0.0854 | 0.1515 | 11.5555 | 31.4882 | 84.4% | 0.6442 | 78.2% | 74.9% | - |
| 3 h | peak | prophet | 46,506 | 0.0762 | 0.1258 | - | - | 83.1% | 0.6182 | 50.2% | 80.0% | 55.5% |
| 3 h | peak | lstm | 46,506 | 0.0731 | 0.1272 | 8.6327 | 22.0909 | 86.4% | 0.6979 | 79.1% | 82.5% | 80.6% |
| 15 min | off-peak | b0 | 99,546 | 0.0634 | 0.1157 | 6.4822 | 18.2294 | 88.5% | 0.6455 | 68.3% | 66.8% | - |
| 15 min | off-peak | prophet | 99,546 | 0.0524 | 0.0928 | - | - | 89.2% | 0.6574 | 47.7% | 76.8% | 73.5% |
| 15 min | off-peak | lstm | 99,546 | 0.0512 | 0.0881 | 5.5808 | 14.8679 | 89.6% | 0.6889 | 50.6% | 84.9% | 83.0% |
| 1 h | off-peak | b0 | 96,479 | 0.0646 | 0.1172 | 6.5006 | 18.2960 | 88.1% | 0.6458 | 68.4% | 67.0% | - |
| 1 h | off-peak | prophet | 96,479 | 0.0532 | 0.0938 | - | - | 89.0% | 0.6591 | 48.5% | 76.8% | 73.0% |
| 1 h | off-peak | lstm | 96,479 | 0.0591 | 0.1032 | 5.7217 | 15.3030 | 88.7% | 0.6910 | 67.5% | 78.2% | 81.0% |
| 3 h | off-peak | b0 | 81,550 | 0.0655 | 0.1180 | 6.2962 | 17.9341 | 88.0% | 0.6454 | 67.2% | 66.1% | - |
| 3 h | off-peak | prophet | 81,550 | 0.0535 | 0.0937 | - | - | 89.1% | 0.6646 | 48.6% | 77.0% | 73.0% |
| 3 h | off-peak | lstm | 81,550 | 0.0633 | 0.1101 | 5.5092 | 14.9714 | 88.0% | 0.6797 | 73.3% | 71.1% | 81.0% |
| 1 h | normal | b0 | 114,233 | 0.0720 | 0.1305 | 8.3208 | 23.9320 | 86.9% | 0.6517 | 74.6% | 70.8% | - |
| 1 h | normal | prophet | 114,233 | 0.0596 | 0.1034 | - | - | 87.2% | 0.6505 | 49.4% | 80.6% | 68.2% |
| 1 h | normal | lstm | 114,233 | 0.0623 | 0.1073 | 6.7009 | 18.0030 | 88.0% | 0.7033 | 71.7% | 83.0% | 80.6% |
| 1 h | rain | b0 | 19,150 | 0.0701 | 0.1264 | 7.8896 | 22.7347 | 86.8% | 0.6407 | 75.5% | 70.8% | - |
| 1 h | rain | prophet | 19,150 | 0.0652 | 0.1130 | - | - | 86.5% | 0.6234 | 53.4% | 70.7% | 64.5% |
| 1 h | rain | lstm | 19,150 | 0.0614 | 0.1083 | 6.1284 | 16.3585 | 88.1% | 0.6896 | 67.8% | 82.9% | 80.7% |
| 1 h | event | b0 | 9,602 | 0.0668 | 0.1219 | 6.5585 | 17.9181 | 87.4% | 0.6266 | 50.7% | 80.9% | - |
| 1 h | event | prophet | 9,602 | 0.0653 | 0.1114 | - | - | 86.8% | 0.6025 | 40.6% | 67.1% | 62.9% |
| 1 h | event | lstm | 9,602 | 0.0588 | 0.1015 | 5.6042 | 14.4555 | 88.1% | 0.6876 | 60.0% | 84.4% | 81.7% |

## Improvement of the LSTM (MAE on load factor)

| Horizon | Segment | vs B0 | vs Prophet |
|---|---|---|---|
| 15 min | all | +22.8% | +9.4% |
| 15 min | peak | +28.4% | +19.8% |
| 15 min | off-peak | +19.2% | +2.3% |
| 1 h | all | +13.2% | -2.0% |
| 1 h | peak | +20.4% | +10.9% |
| 1 h | off-peak | +8.6% | -10.9% |
| 3 h | all | +8.0% | -8.3% |
| 3 h | peak | +14.4% | +4.1% |
| 3 h | off-peak | +3.2% | -18.4% |

## Crowd-level confusion matrix (LSTM, 1-hour horizon; rows = actual, columns = predicted)

| actual \ predicted | LOW | MEDIUM | HIGH | CROWDED |
|---|---|---|---|---|
| LOW | 104,697 | 5,181 | 464 | 28 |
| MEDIUM | 2,102 | 9,673 | 3,094 | 286 |
| HIGH | 24 | 1,818 | 4,173 | 1,168 |
| CROWDED | 0 | 359 | 2,660 | 7,258 |

CROWDED recall (LSTM, 1 h, all slots): 70.6%. Reported as measured.

Load factor here is the *demand* load factor, (onboard + left behind) / capacity, so CROWDED (>= 1.0) means the vehicle left full with people still waiting.

Scenario types are assigned per test day from context tables only: event = a city_event with attendance that day; rain = >= 5 mm of precipitation in the recorded weather; otherwise normal. Segments with few days are noisy.

Notes: weather-forecast features use recorded weather (a perfect forecast) for twin data; in deployment they come from the Open-Meteo forecast API. Prophet has no boardings model, so its boardings columns are empty.