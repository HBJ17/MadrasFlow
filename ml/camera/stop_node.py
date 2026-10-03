"""Stop camera node (section 11.1): people waiting at a stop.

    python -m camera.stop_node --source 0 --stop-id MRTS_VLCY [--zone "0.1,0.4 0.9,0.4 0.9,1 0.1,1"] [--show]

YOLOv8n + ByteTrack at ~5 FPS; waiting_count = tracked people with feet inside the waiting zone
(median over 5 s). Posts source='camera_stop' every 30 s, plus a burst when a bus is detected at the
stop (optional, --vehicle-burst). Zone coordinates are fractions of the frame (0..1).
Frames are processed in memory and discarded; only counts are sent.
"""
from __future__ import annotations

import argparse
import logging
import time

from camera.client import EdgeClient
from camera.counter import PersonTracker, ZoneCounter, frames, open_source


def parse_poly(s: str, w: int, h: int):
    return [(float(x) * w, float(y) * h) for x, y in (p.split(",") for p in s.split())]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0", help="webcam index or video file")
    ap.add_argument("--stop-id", required=True)
    ap.add_argument("--node-id", default=None)
    ap.add_argument("--zone", default="0.05,0.35 0.95,0.35 0.95,1.0 0.05,1.0")
    ap.add_argument("--period", type=float, default=30.0, help="seconds between reports")
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--show", action="store_true", help="local preview window (frames never leave the device)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    node = a.node_id or f"stopcam-{a.stop_id}"
    client = EdgeClient(node_id=node, kind="camera_stop")
    cap = open_source(a.source)
    tracker = PersonTracker()
    zone = None
    last_post, n_frames, t0, minute_t = 0.0, 0, time.monotonic(), time.monotonic()
    count = 0
    for _, frame in frames(cap, a.fps):
        h, w = frame.shape[:2]
        if zone is None:
            zone = ZoneCounter(parse_poly(a.zone, w, h))
        tracks = tracker(frame)
        count = zone.update(tracks)
        n_frames += 1
        now = time.monotonic()
        client.fps = n_frames / max(now - t0, 1e-6)
        if now - last_post >= a.period:
            client.post_event(source="camera_stop", stop_id=a.stop_id, waiting_count=count)
            last_post = now
        if now - minute_t >= 60:
            logging.info("fps %.1f, waiting %d, buffered %d", client.fps, count, client.pending())
            minute_t = now
        client.heartbeat()
        client.flush()
        if a.show:
            import cv2

            cv2.polylines(frame, [__import__("numpy").array(zone.polygon, dtype="int32")], True, (0, 200, 0), 2)
            cv2.putText(frame, f"waiting: {count}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 0), 2)
            cv2.imshow(node, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        del frame  # never stored
    client.post_event(source="camera_stop", stop_id=a.stop_id, waiting_count=count)


if __name__ == "__main__":
    main()
