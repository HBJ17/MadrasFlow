"""Measure counting accuracy (section 11.5) -> reports/camera_accuracy.md

Real clip (preferred):
    python -m camera.accuracy --clip door.mp4 --truth door_truth.csv [--line "0.5,0 0.5,1" --inside left]
    truth CSV columns: t_seconds,kind   (kind = in | out; one row per real crossing, counted by hand)

Synthetic clip (pipeline check when no recording is available):
    python -m camera.accuracy --synthetic
    Person cut-outs from the sample photos that ship with Ultralytics are composited onto a
    background and moved across a doorway line with exact ground truth, including people walking
    side by side (partial occlusion) and a hesitation (cross and step back) that must not count.
    This proves the YOLO + ByteTrack + line-counter pipeline end to end; it is NOT a measurement
    of real doorway accuracy, and the report says so.

Events are matched to ground truth within +/-1.5 s with the same direction.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from camera.counter import YOLO_WEIGHTS, LineCounter, PersonTracker, frames, open_source
from common.config import REPORTS_DIR

MATCH_S = 1.5
W, H, FPS = 960, 540, 15
HES_S = 1.6  # hesitation: over the line and back in 1.6 s


def _person_cutouts():
    """Person crops (with a soft mask from the box) from the Ultralytics sample images."""
    import cv2
    from ultralytics import YOLO
    from ultralytics.utils import ASSETS

    model = YOLO(str(YOLO_WEIGHTS))
    crops = []
    for name in ("bus.jpg", "zidane.jpg"):
        img = cv2.imread(str(ASSETS / name))
        r = model(img, classes=[0], conf=0.5, verbose=False)[0]
        for x1, y1, x2, y2 in r.boxes.xyxy.int().tolist():
            c = img[y1:y2, x1:x2]
            if c.shape[0] > 150 and c.shape[1] > 50:
                crops.append(c)
    bg = cv2.GaussianBlur(cv2.resize(cv2.imread(str(ASSETS / "bus.jpg")), (W, H)), (0, 0), 25)
    return crops, bg


def synthetic_clip(path: Path, seed: int = 3):
    """Writes the clip and returns the ground truth DataFrame (t_seconds, kind)."""
    import cv2

    rng = np.random.default_rng(seed)
    crops, bg = _person_cutouts()
    # schedule: (start_s, direction +1 in (left->right) / -1 out, lane_y, crop_idx, hesitate)
    plan, t = [], 1.0
    for k in range(24):
        d = 1 if rng.random() < 0.55 else -1
        plan.append((t, d, int(rng.integers(0, 2)), int(rng.integers(0, len(crops))), False))
        if k % 6 == 3:   # a second person walking alongside (partial occlusion)
            plan.append((t + 0.25, d, 1 - plan[-1][2], int(rng.integers(0, len(crops))), False))
        if k % 8 == 5:   # hesitation: steps across, then back within a second (must not count)
            plan.append((t + 1.5, -d, 0, int(rng.integers(0, len(crops))), True))
        t += float(rng.uniform(1.8, 3.2))
    dur = t + 4
    walk_s = 2.4
    truth = []
    sprites = []
    for (st, d, lane, ci, hes) in plan:
        h_px = 300 if lane == 0 else 260
        c = crops[ci]
        sc = h_px / c.shape[0]
        img = cv2.resize(c, (max(30, int(c.shape[1] * sc)), h_px))
        y0 = H - h_px - (10 if lane == 0 else 60)
        sprites.append((st, d, img, y0, hes))
        if not hes:
            truth.append((st + walk_s / 2, "in" if d == 1 else "out"))
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for fi in range(int(dur * FPS)):
        tt = fi / FPS
        fr = bg.copy()
        for st, d, img, y0, hes in sprites:
            u = (tt - st) / (HES_S if hes else walk_s)
            if not 0 <= u <= 1:
                continue
            if hes:  # step over the line and back: the two crossings are < 1 s apart (debounce window)
                u = 0.35 + (0.3 * (u / 0.5) if u < 0.5 else 0.3 * (1 - (u - 0.5) / 0.5))
            xc = (0.15 + 0.7 * u) * W if d == 1 else (0.85 - 0.7 * u) * W
            x0 = int(xc - img.shape[1] / 2)
            xa, xb = max(0, x0), min(W, x0 + img.shape[1])
            if xb > xa:
                fr[y0:y0 + img.shape[0], xa:xb] = img[:, xa - x0:xb - x0]
        vw.write(fr)
    vw.release()
    return pd.DataFrame(truth, columns=["t_seconds", "kind"]), len(plan), sum(1 for p in plan if p[4])


def run_counter(clip: str, line_spec: str, inside: str, fps: float):
    cap = open_source(clip)
    tracker = PersonTracker()
    line, events = None, []
    for t, frame in frames(cap, fps):
        h, w = frame.shape[:2]
        if line is None:
            (x1, y1), (x2, y2) = [tuple(float(v) for v in p.split(",")) for p in line_spec.split()]
            line = LineCounter((x1 * w, y1 * h), (x2 * w, y2 * h), inside=inside, min_box_area=0.004 * w * h)
        for tid, kind in line.update(tracker(frame), t=t):
            if kind == "undo":
                for i in range(len(events) - 1, -1, -1):
                    if events[i][2] == tid:
                        events.pop(i)
                        break
            else:
                events.append((t, kind, tid))
    return pd.DataFrame(events, columns=["t_seconds", "kind", "track"])


def match(pred: pd.DataFrame, truth: pd.DataFrame) -> dict:
    out = {}
    for kind in ("in", "out"):
        p = sorted(pred[pred.kind == kind].t_seconds)
        g = sorted(truth[truth.kind == kind].t_seconds)
        used, tp = set(), 0
        for x in p:
            best = None
            for j, y in enumerate(g):
                if j not in used and abs(x - y) <= MATCH_S and (best is None or abs(x - y) < abs(x - g[best])):
                    best = j
            if best is not None:
                used.add(best)
                tp += 1
        out[kind] = {"truth": len(g), "counted": len(p), "tp": tp,
                     "precision": tp / len(p) if p else float("nan"), "recall": tp / len(g) if g else float("nan")}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip")
    ap.add_argument("--truth")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--line", default="0.5,0.0 0.5,1.0")
    ap.add_argument("--inside", default="right", help="side of the line (from a to b) that is inside")
    ap.add_argument("--fps", type=float, default=FPS)
    a = ap.parse_args()
    REPORTS_DIR.mkdir(exist_ok=True)
    note = ""
    if a.synthetic:
        clip = REPORTS_DIR / "synthetic_door.mp4"
        truth, n_people, n_hes = synthetic_clip(clip)
        # 'in' walkers move left->right; with the line pointing down the frame, image-right is the 'right' side
        a.inside = "right"
        note = (f"**Synthetic clip** ({clip.name}, {len(truth)} true crossings, {n_people} walkers incl. {n_hes} "
                "hesitations that must not count, side-by-side pairs for partial occlusion). Person cut-outs come from "
                "the sample photos bundled with Ultralytics. This verifies the pipeline end to end; it is **not** a "
                "measurement of accuracy at a real bus door.")
        src = str(clip)
    else:
        if not (a.clip and a.truth):
            ap.error("--clip and --truth are required (or use --synthetic)")
        truth = pd.read_csv(a.truth)
        src = a.clip
        note = f"Real clip `{Path(a.clip).name}` with a manual ground-truth count ({len(truth)} crossings)."
    pred = run_counter(src, a.line, a.inside, a.fps)
    m = match(pred, truth)
    lines = ["# Camera counting accuracy", "",
             f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python -m camera.accuracy {'--synthetic' if a.synthetic else ''}`.", "",
             note, "",
             "Pipeline: YOLOv8n person detection (class 0) + ByteTrack, virtual counting line with 1 s debounce, "
             f"processed at {a.fps:g} FPS. Matching window ±{MATCH_S} s, same direction.", "",
             "| Direction | True crossings | Counted | Matched | Precision | Recall |", "|---|---|---|---|---|---|"]
    for k, lbl in (("in", "Entries (boardings)"), ("out", "Exits (alightings)")):
        x = m[k]
        lines.append(f"| {lbl} | {x['truth']} | {x['counted']} | {x['tp']} | {x['precision']:.1%} | {x['recall']:.1%} |")
    lines += ["", "Expected limitations, stated plainly: accuracy falls in packed vehicles because people occlude each "
              "other at the door; top-down mounting over the door reduces this. Counts only leave the device; frames "
              "are processed in memory and discarded, with no face recognition or re-identification beyond "
              "within-clip track IDs."]
    if a.synthetic:
        lines += ["", "To measure real accuracy: record a doorway clip, count crossings by hand into a CSV "
                  "(`t_seconds,kind`), and run `python -m camera.accuracy --clip clip.mp4 --truth truth.csv`."]
    (REPORTS_DIR / "camera_accuracy.md").write_text("\n".join(lines), encoding="utf8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
