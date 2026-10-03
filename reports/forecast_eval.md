# Forecast evaluation

Generated 2026-10-02 13:38 by `python -m predictor.evaluate` on the held-out test period.

> **Results are on twin (simulated) data.** They show how well the models learn the simulator and that the pipeline works end to end, not real-world accuracy. Real accuracy needs real AFC or sensor data, which the schema is built to accept.

Split (time-based): train 2026-07-04 .. 2026-09-01 (first 7 days warm up lags), validation 2026-09-02 .. 2026-09-16, test 2026-09-17 .. 2026-10-01.
Target: max demand load factor per (route, direction, stop, 15-min slot), evaluated only on slots where a vehicle departed. 217 series. Models: B0 = same time last week; Prophet = per route-direction with stop share profiles; LSTM = 2x128, 24-slot window, 12-slot quantile head.

## Acceptance: LSTM beats B0 on 1-hour MAE at peak slots: **PASS** (LSTM 0.0717 vs B0 0.0809, +11.4%)

## Load factor and boardings

| Horizon | Segment | Model | n | MAE LF | RMSE LF | MAE board | RMSE board | Level acc | Macro-F1 | CROWDED recall | CROWDED precision | 80% band coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15 min | all | b0 | 153,651 | 0.0663 | 0.1291 | 5.4487 | 16.2166 | 87.5% | 0.6897 | 77.1% | 79.8% | - |
| 15 min | all | prophet | 153,651 | 0.0626 | 0.1211 | - | - | 86.5% | 0.6573 | 51.9% | 81.0% | 67.7% |
| 15 min | all | lstm | 153,651 | 0.0578 | 0.1097 | 4.8760 | 14.2147 | 88.2% | 0.7159 | 74.5% | 83.1% | 84.5% |
| 1 h | all | b0 | 150,566 | 0.0669 | 0.1297 | 5.4765 | 16.3125 | 87.3% | 0.6904 | 77.3% | 79.9% | - |
| 1 h | all | prophet | 150,566 | 0.0632 | 0.1218 | - | - | 86.3% | 0.6578 | 52.1% | 81.0% | 67.3% |
| 1 h | all | lstm | 150,566 | 0.0616 | 0.1164 | 4.8490 | 14.0804 | 87.3% | 0.7011 | 69.1% | 84.5% | 83.2% |
| 3 h | all | b0 | 134,789 | 0.0681 | 0.1319 | 5.5493 | 16.6763 | 87.1% | 0.6933 | 78.0% | 80.1% | - |
| 3 h | all | prophet | 134,789 | 0.0648 | 0.1248 | - | - | 86.1% | 0.6596 | 53.2% | 80.6% | 66.2% |
| 3 h | all | lstm | 134,789 | 0.0652 | 0.1228 | 5.1494 | 14.7340 | 86.6% | 0.6989 | 68.9% | 83.9% | 81.9% |
| 15 min | peak | b0 | 47,593 | 0.0809 | 0.1571 | 8.0925 | 23.9923 | 85.0% | 0.6801 | 82.6% | 83.8% | - |
| 15 min | peak | prophet | 47,593 | 0.0834 | 0.1574 | - | - | 81.8% | 0.6260 | 53.4% | 83.0% | 54.4% |
| 15 min | peak | lstm | 47,593 | 0.0694 | 0.1294 | 6.9360 | 20.1245 | 86.0% | 0.7020 | 81.8% | 86.1% | 83.9% |
| 1 h | peak | b0 | 47,593 | 0.0809 | 0.1571 | 8.0925 | 23.9923 | 85.0% | 0.6801 | 82.6% | 83.8% | - |
| 1 h | peak | prophet | 47,593 | 0.0834 | 0.1574 | - | - | 81.8% | 0.6260 | 53.4% | 83.0% | 54.4% |
| 1 h | peak | lstm | 47,593 | 0.0717 | 0.1343 | 6.8718 | 19.8357 | 85.4% | 0.6932 | 78.2% | 87.4% | 82.4% |
| 3 h | peak | b0 | 47,593 | 0.0809 | 0.1571 | 8.0925 | 23.9923 | 85.0% | 0.6801 | 82.6% | 83.8% | - |
| 3 h | peak | prophet | 47,593 | 0.0834 | 0.1574 | - | - | 81.8% | 0.6260 | 53.4% | 83.0% | 54.4% |
| 3 h | peak | lstm | 47,593 | 0.0746 | 0.1401 | 7.1147 | 20.2613 | 84.7% | 0.6847 | 76.6% | 85.6% | 82.3% |
| 15 min | off-peak | b0 | 106,058 | 0.0597 | 0.1143 | 4.2623 | 11.0759 | 88.6% | 0.6874 | 71.5% | 75.4% | - |
| 15 min | off-peak | prophet | 106,058 | 0.0533 | 0.1006 | - | - | 88.6% | 0.6722 | 50.3% | 79.0% | 73.7% |
| 15 min | off-peak | lstm | 106,058 | 0.0526 | 0.0996 | 3.9515 | 10.5352 | 89.2% | 0.7135 | 66.9% | 79.6% | 84.7% |
| 1 h | off-peak | b0 | 102,973 | 0.0604 | 0.1149 | 4.2674 | 11.0920 | 88.4% | 0.6887 | 71.8% | 75.7% | - |
| 1 h | off-peak | prophet | 102,973 | 0.0539 | 0.1012 | - | - | 88.4% | 0.6733 | 50.8% | 78.9% | 73.3% |
| 1 h | off-peak | lstm | 102,973 | 0.0570 | 0.1071 | 3.9141 | 10.3942 | 88.1% | 0.6934 | 59.5% | 80.8% | 83.5% |
| 3 h | off-peak | b0 | 87,196 | 0.0612 | 0.1159 | 4.1612 | 10.7565 | 88.3% | 0.6936 | 72.3% | 75.5% | - |
| 3 h | off-peak | prophet | 87,196 | 0.0547 | 0.1027 | - | - | 88.4% | 0.6798 | 53.1% | 77.8% | 72.7% |
| 3 h | off-peak | lstm | 87,196 | 0.0600 | 0.1122 | 4.0767 | 10.5599 | 87.7% | 0.6960 | 59.3% | 81.3% | 81.7% |
| 1 h | normal | b0 | 110,480 | 0.0663 | 0.1283 | 5.5475 | 16.5931 | 87.3% | 0.6921 | 77.6% | 80.3% | - |
| 1 h | normal | prophet | 110,480 | 0.0621 | 0.1207 | - | - | 86.5% | 0.6614 | 51.7% | 82.5% | 68.1% |
| 1 h | normal | lstm | 110,480 | 0.0617 | 0.1161 | 4.9014 | 14.1817 | 87.2% | 0.7011 | 69.3% | 84.7% | 83.4% |
| 1 h | rain | b0 | 30,049 | 0.0705 | 0.1375 | 5.5367 | 16.5526 | 87.2% | 0.6876 | 78.4% | 78.4% | - |
| 1 h | rain | prophet | 30,049 | 0.0642 | 0.1240 | - | - | 86.4% | 0.6631 | 55.0% | 80.4% | 66.7% |
| 1 h | rain | lstm | 30,049 | 0.0628 | 0.1189 | 4.8953 | 14.6164 | 87.0% | 0.6977 | 68.6% | 84.1% | 82.2% |
| 1 h | event | b0 | 10,037 | 0.0628 | 0.1208 | 4.5150 | 11.8670 | 88.0% | 0.6745 | 69.6% | 80.6% | - |
| 1 h | event | prophet | 10,037 | 0.0724 | 0.1269 | - | - | 84.9% | 0.5962 | 47.1% | 64.1% | 60.6% |
| 1 h | event | lstm | 10,037 | 0.0578 | 0.1117 | 4.1341 | 10.9861 | 88.5% | 0.7093 | 67.3% | 83.1% | 83.8% |

## Improvement of the LSTM (MAE on load factor)

| Horizon | Segment | vs B0 | vs Prophet |
|---|---|---|---|
| 15 min | all | +12.8% | +7.7% |
| 15 min | peak | +14.2% | +16.8% |
| 15 min | off-peak | +11.9% | +1.3% |
| 1 h | all | +7.9% | +2.5% |
| 1 h | peak | +11.4% | +14.1% |
| 1 h | off-peak | +5.7% | -5.7% |
| 3 h | all | +4.3% | -0.5% |
| 3 h | peak | +7.8% | +10.5% |
| 3 h | off-peak | +1.8% | -9.7% |

## Crowd-level confusion matrix (LSTM, 1-hour horizon; rows = actual, columns = predicted)

| actual \ predicted | LOW | MEDIUM | HIGH | CROWDED |
|---|---|---|---|---|
| LOW | 106,700 | 3,753 | 458 | 51 |
| MEDIUM | 3,301 | 9,068 | 3,449 | 367 |
| HIGH | 97 | 1,766 | 5,582 | 1,426 |
| CROWDED | 19 | 381 | 4,102 | 10,046 |

CROWDED recall (LSTM, 1 h, all slots): 69.1%. Reported as measured.

Load factor here is the *demand* load factor, (onboard + left behind) / capacity, so CROWDED (>= 1.0) means the vehicle left full with people still waiting.

Scenario types are assigned per test day from context tables only: event = a city_event with attendance that day; rain = >= 5 mm of precipitation in the recorded weather; otherwise normal. Segments with few days are noisy.

Notes: weather-forecast features use recorded weather (a perfect forecast) for twin data; in deployment they come from the Open-Meteo forecast API. Prophet has no boardings model, so its boardings columns are empty.