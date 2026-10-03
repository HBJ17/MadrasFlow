# Camera counting accuracy

Generated 2026-10-02 13:07 by `python -m camera.accuracy --synthetic`.

**Synthetic clip** (synthetic_door.mp4, 28 true crossings, 31 walkers incl. 3 hesitations that must not count, side-by-side pairs for partial occlusion). Person cut-outs come from the sample photos bundled with Ultralytics. This verifies the pipeline end to end; it is **not** a measurement of accuracy at a real bus door.

Pipeline: YOLOv8n person detection (class 0) + ByteTrack, virtual counting line with 1 s debounce, processed at 15 FPS. Matching window ±1.5 s, same direction.

| Direction | True crossings | Counted | Matched | Precision | Recall |
|---|---|---|---|---|---|
| Entries (boardings) | 15 | 17 | 15 | 88.2% | 100.0% |
| Exits (alightings) | 13 | 14 | 12 | 85.7% | 92.3% |

Expected limitations, stated plainly: accuracy falls in packed vehicles because people occlude each other at the door; top-down mounting over the door reduces this. Counts only leave the device; frames are processed in memory and discarded, with no face recognition or re-identification beyond within-clip track IDs.

To measure real accuracy: record a doorway clip, count crossings by hand into a CSV (`t_seconds,kind`), and run `python -m camera.accuracy --clip clip.mp4 --truth truth.csv`.