import pandas as pd
from twin.simulate import run
from twin.network import load_network
from common.config import corridor
CAP = corridor()["vehicle_types"]["bus_ordinary"]["capacity_total"]
if __name__ == "__main__":
    ev, s = run(start_date="2026-09-22", days=1, seed=3, workers=1, use_calendar=False)
    um = s["_unmet"]; names = load_network().stops.set_index("stop_id").name
    um["name"] = um.stop_id.map(names)
    print(um.groupby(["route_id", "reason"]).size().unstack(fill_value=0))
    print(um.groupby(["route_id", "name"]).size().sort_values(ascending=False).head(12))
    bus = ev[ev.route_id.str.startswith("BUS")].copy()
    bus["dlf"] = (bus.onboard_load + bus.left_behind) / CAP
    top = bus.sort_values("dlf", ascending=False).head(8)
    top["name"] = top.stop_id.map(names)
    print(top[["ts", "route_id", "direction", "name", "boardings", "alightings", "onboard_load", "left_behind"]])
    print(bus.groupby(["route_id","direction"]).agg(trips=("trip_id","nunique"), board=("boardings","sum"), lb=("left_behind","sum")))
