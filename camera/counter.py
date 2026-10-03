"""People counting: YOLOv8n person detection + ByteTrack IDs, a virtual counting line (doorway)
and a polygon zone (waiting area). Frames are processed in memory and discarded; only counts leave
this module. No face recognition, no re-identification beyond within-clip track IDs.

The counting logic (LineCounter, ZoneCounter) is pure Python so it can be unit-tested without a
camera or model.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

import numpy as np


def _side(p, a, b) -> float:
    """>0 if point p is left of the directed line a->b, <0 if right."""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


@dataclass
class LineCounter:
    """Counts tracks crossing the line a->b. `inside` is the side ('left'/'right' of a->b) that is
    inside the vehicle (or stop). Outside->inside = boarding (in); inside->outside = alighting (out).

    Debounce: a track that crosses back within `debounce_s` cancels its previous crossing (people
    hesitating in the doorway). Boxes smaller than `min_box_area` (px^2) are ignored."""
    a: tuple[float, float]
    b: tuple[float, float]
    inside: str = "left"
    debounce_s: float = 1.0
    min_box_area: float = 900.0
    count_in: int = 0
    count_out: int = 0
    _last_side: dict = field(default_factory=dict)
    _last_cross: dict = field(default_factory=dict)   # track_id -> (t, +1 in / -1 out)

    def _is_inside(self, s: float) -> bool:
        return s > 0 if self.inside == "left" else s < 0

    def update(self, tracks, t: float | None = None):
        """tracks: iterable of (track_id, x1, y1, x2, y2). Uses the bottom-centre (feet) point."""
        t = time.monotonic() if t is None else t
        events = []
        for tid, x1, y1, x2, y2 in tracks:
            if (x2 - x1) * (y2 - y1) < self.min_box_area:
                continue
            p = ((x1 + x2) / 2.0, y2)
            s = _side(p, self.a, self.b)
            if s == 0:
                continue
            ins = self._is_inside(s)
            prev = self._last_side.get(tid)
            self._last_side[tid] = ins
            if prev is None or prev == ins:
                continue
            direction = +1 if ins else -1
            lc = self._last_cross.get(tid)
            if lc and t - lc[0] < self.debounce_s and lc[1] == -direction:
                # crossed back quickly: undo the previous crossing
                if lc[1] == +1:
                    self.count_in -= 1
                else:
                    self.count_out -= 1
                del self._last_cross[tid]
                events.append((tid, "undo"))
                continue
            if direction == +1:
                self.count_in += 1
            else:
                self.count_out += 1
            self._last_cross[tid] = (t, direction)
            events.append((tid, "in" if direction == +1 else "out"))
        return events

    def reset(self):
        self.count_in = self.count_out = 0


@dataclass
class ZoneCounter:
    """Number of tracked people whose feet are inside a polygon, median over a time window."""
    polygon: list
    window_s: float = 5.0
    _hist: deque = field(default_factory=deque)

    def inside(self, p) -> bool:
        x, y = p
        poly = self.polygon
        n = len(poly)
        c = False
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
                c = not c
            j = i
        return c

    def update(self, tracks, t: float | None = None) -> int:
        t = time.monotonic() if t is None else t
        n = sum(1 for _, x1, y1, x2, y2 in tracks if self.inside(((x1 + x2) / 2.0, y2)))
        self._hist.append((t, n))
        while self._hist and t - self._hist[0][0] > self.window_s:
            self._hist.popleft()
        return int(np.median([v for _, v in self._hist]))


class PersonTracker:
    """YOLOv8n (class 0 = person) + ByteTrack via Ultralytics. Imported lazily."""

    def __init__(self, model: str = "yolov8n.pt", imgsz: int = 640, conf: float = 0.35):
        from ultralytics import YOLO

        self.model = YOLO(model)
        self.imgsz = imgsz
        self.conf = conf

    def __call__(self, frame):
        r = self.model.track(frame, persist=True, classes=[0], imgsz=self.imgsz, conf=self.conf,
                             tracker="bytetrack.yaml", verbose=False)[0]
        if r.boxes is None or r.boxes.id is None:
            return []
        ids = r.boxes.id.int().tolist()
        xyxy = r.boxes.xyxy.tolist()
        return [(i, *b) for i, b in zip(ids, xyxy)]


def open_source(src: str):
    import cv2

    cap = cv2.VideoCapture(int(src) if str(src).isdigit() else src)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video source {src!r}")
    return cap


def frames(cap, target_fps: float = 5.0):
    """Yield (t_seconds, frame) at about target_fps. For files, t is video time."""
    import cv2

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps / target_fps)))
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            yield i / fps, frame
        i += 1
