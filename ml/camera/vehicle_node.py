"""Vehicle camera node (section 11.2): door entries/exits and running onboard load.

    python -m camera.vehicle_node --source 0 --vehicle-id BUS_95-V001 --route-id BUS_95 --direction 0 \
        --stops 6662,6651,... [--line "0.5,0.0 0.5,1.0" --inside left] [--show]

A virtual counting line across the doorway: a track crossing outside->inside is a boarding,
inside->outside an alighting (debounced 1 s; tiny boxes ignored). load = load + in - out, clamped
at 0. Counts are batched per stop visit and posted as source='camera_vehicle'.

Stop attribution (demo): type the stop_id (or press Enter for the next stop in --stops) on stdin
when the vehicle departs a stop. In deployment a GPS matcher calls `depart(stop_id)` when the
vehicle is within 60 m of a stop and slower than 5 km/h (gps_stop_match below).
At the last stop (terminal) the running load is reset to 0 to remove drift.
"""
from __future__ import annotations

import argparse
import logging
import queue
import sys
import threading
import time

from camera.client import EdgeClient
from camera.counter import LineCounter, PersonTracker, frames, open_source


def gps_stop_match(lat, lon, speed_kmh, stops, radius_m=60, max_speed=5):
    """Nearest stop within radius_m while speed < max_speed km/h, else None. stops: [(id, lat, lon)]."""
    import math

    if speed_kmh >= max_speed:
        return None
    best, bd = None, radius_m
    for sid, la, lo in stops:
        d = 6371000 * 2 * math.asin(math.sqrt(math.sin(math.radians(la - lat) / 2) ** 2 + math.cos(math.radians(lat))
                                              * math.cos(math.radians(la)) * math.sin(math.radians(lo - lon) / 2) ** 2))
        if d <= bd:
            best, bd = sid, d
    return best


class VehicleCounter:
    def __init__(self, client: EdgeClient, vehicle_id, route_id, direction, trip_id=None, terminal=None):
        self.client, self.vehicle_id, self.route_id, self.direction = client, vehicle_id, route_id, direction
        self.trip_id, self.terminal = trip_id, terminal
        self.load = 0
        self.in_since, self.out_since = 0, 0

    def depart(self, stop_id: str, line: LineCounter):
        b, a = line.count_in - self.in_since, line.count_out - self.out_since
        self.in_since, self.out_since = line.count_in, line.count_out
        self.load = max(0, self.load + b - a)
        if stop_id == self.terminal:
            self.load = 0  # terminal reset: vehicle known to be empty at end of trip
        self.client.post_event(source="camera_vehicle", stop_id=stop_id, vehicle_id=self.vehicle_id, route_id=self.route_id,
                               direction=self.direction, trip_id=self.trip_id, boardings=b, alightings=a,
                               onboard_load=self.load)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0")
    ap.add_argument("--vehicle-id", required=True)
    ap.add_argument("--route-id", required=True)
    ap.add_argument("--direction", type=int, default=0)
    ap.add_argument("--trip-id", default=None)
    ap.add_argument("--stops", default="", help="comma-separated stop_ids in order (Enter = next stop)")
    ap.add_argument("--line", default="0.5,0.0 0.5,1.0", help="counting line as two x,y fractions")
    ap.add_argument("--inside", default="left", choices=["left", "right"])
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    stops = [s for s in a.stops.split(",") if s]
    client = EdgeClient(node_id=f"vehcam-{a.vehicle_id}", kind="camera_vehicle")
    vc = VehicleCounter(client, a.vehicle_id, a.route_id, a.direction, a.trip_id, stops[-1] if stops else None)
    cmds: queue.Queue = queue.Queue()

    def stdin_reader():
        for line in sys.stdin:
            cmds.put(line.strip())

    threading.Thread(target=stdin_reader, daemon=True).start()
    print("Type a stop_id + Enter when the vehicle departs a stop (Enter alone = next stop in --stops).", flush=True)
    next_i = 0
    cap = open_source(a.source)
    tracker = PersonTracker()
    line = None
    n, t0, minute_t = 0, time.monotonic(), time.monotonic()
    for _, frame in frames(cap, a.fps):
        h, w = frame.shape[:2]
        if line is None:
            (x1, y1), (x2, y2) = [tuple(float(v) for v in p.split(",")) for p in a.line.split()]
            line = LineCounter((x1 * w, y1 * h), (x2 * w, y2 * h), inside=a.inside, min_box_area=0.004 * w * h)
        line.update(tracker(frame))
        n += 1
        client.fps = n / max(time.monotonic() - t0, 1e-6)
        while not cmds.empty():
            c = cmds.get()
            sid = c or (stops[next_i] if next_i < len(stops) else None)
            if sid:
                vc.depart(sid, line)
                if sid in stops:
                    next_i = stops.index(sid) + 1
        if time.monotonic() - minute_t >= 60:
            logging.info("fps %.1f in %d out %d load %d buffered %d", client.fps, line.count_in, line.count_out, vc.load,
                         client.pending())
            minute_t = time.monotonic()
        client.heartbeat()
        client.flush()
        if a.show:
            import cv2

            cv2.line(frame, tuple(map(int, line.a)), tuple(map(int, line.b)), (0, 0, 255), 2)
            cv2.putText(frame, f"in {line.count_in} out {line.count_out} load {vc.load}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
            cv2.imshow(client.node_id, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        del frame


if __name__ == "__main__":
    main()
