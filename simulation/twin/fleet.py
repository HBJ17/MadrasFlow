"""Fleet plans for the scenario builder: depot managers add buses to a route for some hours; the twin
needs extra trips. A bus on a route makes one trip each way per round trip, so

  trips per direction = bus-hours x 60 / round-trip minutes

where round-trip minutes = scheduled run time in both directions + a layover at each end. Consecutive
hours on the same route (and direction) are merged into one window, and the trips are spread evenly
over it. A bus assigned to one direction only is assumed to run back empty (same trip count).
"""
from __future__ import annotations

from collections import defaultdict

LAYOVER_MIN = 10.0


def round_trip_minutes(net, route_id: str) -> float:
    rs = net.route_stop[net.route_stop.route_id == route_id]
    if not len(rs):
        raise ValueError(f"unknown route {route_id}")
    return float(rs.run_min.sum()) + 2 * LAYOVER_MIN


def buses_to_trips(net, fleet: list[dict] | None) -> tuple[list[dict], dict]:
    """fleet: [{route, direction (None = both), hour, buses}] -> (extra_trips, summary)."""
    cells: dict[tuple, dict[int, int]] = defaultdict(dict)
    for f in fleet or []:
        n, h = int(f.get("buses", 0)), int(f["hour"])
        if n <= 0 or not 0 <= h <= 23:
            continue
        key = (f["route"], f.get("direction"))
        cells[key][h] = cells[key].get(h, 0) + n
    extra, per_route = [], {}
    bus_hours = 0
    for (route, direction), hours in sorted(cells.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        cyc = round_trip_minutes(net, route)
        hs = sorted(hours)
        runs, cur = [], [hs[0]]
        for h in hs[1:]:
            if h == cur[-1] + 1:
                cur.append(h)
            else:
                runs.append(cur)
                cur = [h]
        runs.append(cur)
        for run in runs:
            bh = sum(hours[h] for h in run)
            n = max(1, round(bh * 60 / cyc))
            dirs = [direction] if direction is not None else [0, 1]
            for d in dirs:
                extra.append({"route": route, "direction": d, "start": f"{run[0]:02d}:00",
                              "end": f"{min(run[-1] + 1, 24):02d}:00" if run[-1] < 23 else "23:59", "n": int(n)})
            bus_hours += bh
            pr = per_route.setdefault(route, {"bus_hours": 0, "trips": 0, "peak_buses": 0, "round_trip_min": round(cyc)})
            pr["bus_hours"] += bh
            pr["trips"] += n * len(dirs)
            pr["peak_buses"] = max(pr["peak_buses"], max(hours[h] for h in run))
    return extra, {"bus_hours": bus_hours, "trips_added": sum(x["n"] for x in extra), "by_route": per_route}
