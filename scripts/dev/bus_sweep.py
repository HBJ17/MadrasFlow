from concurrent.futures import ProcessPoolExecutor
import pandas as pd
from common.config import corridor, demand_config
CAP = corridor()["vehicle_types"]["bus_ordinary"]["capacity_total"]
from twin.simulate import run

def one(b):
    bm = dict(demand_config()["base_mode"]); bm["bus"] = b
    ev, s = run(config={"base_mode": bm}, start_date="2026-09-22", days=1, seed=3, workers=1, use_calendar=False)
    bus = ev[ev.route_id.str.startswith("BUS")]
    lf = (bus.onboard_load + bus.left_behind) / CAP
    worst = bus.assign(lf=lf, slot=bus.ts.dt.floor("15min")).groupby(["route_id", "direction", "slot"]).lf.quantile(0.9)
    um = s["_unmet"]; um_bus = um[um.route_id.str.startswith("BUS", na=False)]
    return b, int(bus.boardings.sum()), len(um_bus), round(float((lf >= 1).mean()), 3), round(float(worst.max()), 2), round(float(worst.quantile(0.95)), 2), round(float((bus.onboard_load/CAP).mean()),3)

if __name__ == "__main__":
    with ProcessPoolExecutor(6) as ex:
        for r in ex.map(one, [0.34, 0.25, 0.2, 0.16, 0.12, 0.09]):
            print("bus_base=%.2f boardings=%d unmet_bus=%d crowded_share=%.3f worstP90=%.2f p95slot=%.2f mean_onboard_lf=%.3f" % r)
