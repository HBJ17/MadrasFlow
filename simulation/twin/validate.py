"""Twin validation report (section 6) -> reports/twin_validation.md (+ figures).

    python -m twin.validate

Everything in the report is computed from runs made by this script; nothing is typed by hand.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common.config import REPORTS_DIR, crowd_level, demand_config, load_yaml, peak_hours  # noqa: E402
from twin.network import load_network  # noqa: E402
from twin.simulate import run  # noqa: E402
from twin.calibrate import service_date  # noqa: E402

FIG = REPORTS_DIR / "figures"
WEEKDAY0 = date(2026, 9, 21)  # Monday


def check_conservation(ev: pd.DataFrame, cap: pd.Series) -> dict:
    """load_after = load_before + boardings - alightings along each trip; load >= 0; load <= capacity."""
    e = ev.sort_values(["run_id", "trip_id", "ts"]).copy()
    prev = e.groupby(["run_id", "trip_id"]).onboard_load.shift(1).fillna(0)
    viol = (e.onboard_load != prev + e.boardings - e.alightings).sum()
    neg = (e.onboard_load < 0).sum()
    over = (e.onboard_load > e.route_id.map(cap)).sum()
    end_load = e.groupby(["run_id", "trip_id"]).onboard_load.last()
    return {"rows": len(e), "conservation_violations": int(viol), "negative_loads": int(neg),
            "over_capacity": int(over), "trips_not_empty_at_terminus": int((end_load != 0).sum())}


def main():
    REPORTS_DIR.mkdir(exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    net = load_network()
    routes = net.routes.set_index("route_id")
    cap = routes.capacity_total
    modes = routes["mode"]
    tgt = load_yaml("calibration_targets.yaml")
    tc, tol = tgt["corridor"], tgt["tolerances"]
    dcfg = demand_config()

    # 7 weekdays + 2 weekend days, calendar effects off (shape on normal days)
    ev_wk, s_wk = run(start_date=WEEKDAY0, days=7, seed=101, use_calendar=False)
    ev_wk = ev_wk[pd.to_datetime(service_date(ev_wk)).dt.weekday < 5]
    ev_we, s_we = run(start_date=WEEKDAY0 + timedelta(days=5), days=2, seed=202, use_calendar=False)
    ev_ev, s_ev = run(scenario="cricket_match", start_date=WEEKDAY0, days=1, seed=101, use_calendar=False)
    base1 = ev_wk[service_date(ev_wk) == WEEKDAY0]
    # direction checks for Phase 4
    ev_rain, s_rain = run(scenario="rain_heavy", start_date=WEEKDAY0, days=1, seed=101, use_calendar=False)
    xt = [{"route": "BUS_95", "direction": 0, "start": "07:30", "end": "10:30", "n": 6},
          {"route": "BUS_95", "direction": 1, "start": "16:30", "end": "20:00", "n": 6}]
    ev_x, s_x = run(scenario="extra_trips", start_date=WEEKDAY0, days=1, seed=101, use_calendar=False,
                    mods={"extra_trips": xt})
    ev_dis, s_dis = run(scenario="metro_disruption", start_date=WEEKDAY0, days=1, seed=101, use_calendar=False)
    ev_cy, s_cy = run(scenario="cyclone", start_date=WEEKDAY0, days=1, seed=101, use_calendar=False)

    all_ev = pd.concat([ev_wk, ev_we, ev_ev, ev_rain, ev_x, ev_dis, ev_cy])
    cons = check_conservation(all_ev, cap)

    n_wd = service_date(ev_wk).nunique()
    by_mode = (ev_wk.groupby(ev_wk.route_id.map(modes)).boardings.sum() / n_wd).round()
    target_mode = {"bus": tc["bus_daily_boardings"], "metro": tc["metro_daily_boardings"], "mrts": tc["mrts_daily_boardings"]}
    wd_total = ev_wk.boardings.sum() / n_wd
    tgt_total = sum(target_mode.values())
    we_total = ev_we.boardings.sum() / service_date(ev_we).nunique()
    ratio = wd_total / we_total
    ev_ratio = ev_ev.boardings.sum() / base1.boardings.sum()
    h = ev_wk.ts.dt.hour
    peak_share = ev_wk.boardings[h.isin(peak_hours())].sum() / ev_wk.boardings.sum()

    def lf(e, route=None):
        x = e if route is None else e[e.route_id == route]
        return x.onboard_load / x.route_id.map(cap)

    bus = lambda e: e[e.route_id.map(modes) == "bus"]  # noqa: E731
    rain_bus = bus(ev_rain).onboard_load.mean() / bus(base1).onboard_load.mean()
    x_mask = lambda e: (e.route_id == "BUS_95") & (e.ts.dt.hour.between(7, 10) | e.ts.dt.hour.between(16, 20))  # noqa: E731
    x_lf_before, x_lf_after = lf(base1[x_mask(base1)]).mean(), lf(ev_x[x_mask(ev_x)]).mean()
    x_lb_before, x_lb_after = base1[x_mask(base1)].left_behind.sum(), ev_x[x_mask(ev_x)].left_behind.sum()
    metro_win = lambda e: e[(e.route_id.map(modes) == "metro") & e.ts.dt.hour.between(8, 9)]  # noqa: E731
    dis_lf = (lf(metro_win(ev_dis)).mean(), lf(metro_win(base1)).mean())
    metro_b = lambda e: e[e.route_id.map(modes) == "metro"].boardings.sum()  # noqa: E731
    cy_mrts = int((ev_cy.route_id.map(modes) == "mrts").sum())
    cy_metro = metro_b(ev_cy) / max(1, metro_b(base1))

    # MRTS station checks (reported, not fitted)
    mrts = ev_wk[ev_wk.route_id.map(modes) == "mrts"]
    foot = (mrts.groupby("stop_id").boardings.sum() + mrts.groupby("stop_id").alightings.sum()) / n_wd
    top3 = tc["mrts_top3_share"]
    top3_sim = mrts[mrts.stop_id.isin(top3["stations"])].boardings.sum() / max(1, mrts.boardings.sum())

    checks = [
        ("Load conservation (load_after = load_before + boardings - alightings)", cons["conservation_violations"] == 0,
         f"{cons['conservation_violations']} violations in {cons['rows']:,} rows"),
        ("No negative loads", cons["negative_loads"] == 0, f"{cons['negative_loads']} rows"),
        ("Capacity never exceeded", cons["over_capacity"] == 0, f"{cons['over_capacity']} rows"),
        ("Vehicles empty at terminus", cons["trips_not_empty_at_terminus"] == 0, f"{cons['trips_not_empty_at_terminus']} trips"),
        (f"Daily total within {tol['daily_total_rel']:.0%} of target", abs(wd_total / tgt_total - 1) <= tol["daily_total_rel"],
         f"{wd_total:,.0f} vs {tgt_total:,} ({wd_total / tgt_total - 1:+.1%})"),
        (f"Weekday/weekend ratio within {tol['weekday_weekend_rel']:.0%}",
         abs(ratio / tc["weekday_weekend_ratio"] - 1) <= tol["weekday_weekend_rel"],
         f"{ratio:.2f} vs {tc['weekday_weekend_ratio']}"),
        (f"Event-day ratio between {tol['event_day_ratio'][0]} and {tol['event_day_ratio'][1]}",
         tol["event_day_ratio"][0] <= ev_ratio <= tol["event_day_ratio"][1], f"{ev_ratio:.3f}"),
        (f"Peak-hour share in {tc['peak_hour_share']} (assumption)",
         tc["peak_hour_share"][0] <= peak_share <= tc["peak_hour_share"][1], f"{peak_share:.3f}"),
        ("Scenario direction: heavy rain increases bus load", rain_bus > 1.0, f"mean bus load x{rain_bus:.3f}"),
        ("Scenario direction: extra trips lower load on the target route", x_lf_after < x_lf_before,
         f"BUS_95 peak mean LF {x_lf_before:.3f} -> {x_lf_after:.3f}; left-behind {x_lb_before:,} -> {x_lb_after:,}"),
        ("Scenario direction: metro disruption raises metro load in the window", dis_lf[0] > dis_lf[1],
         f"metro 08-10 mean LF {dis_lf[1]:.3f} -> {dis_lf[0]:.3f}"),
        ("Scenario direction: cyclone halts MRTS; metro loses less than the 25% day-total cut",
         cy_mrts == 0 and cy_metro > 0.75,
         f"MRTS vehicle-stops {cy_mrts}; metro boardings x{cy_metro:.2f} (day total x0.75)"),
    ]

    # ---------------- figures
    st = net.stops.set_index("stop_id").stop_type
    e = ev_wk.copy()
    e["stop_type"] = e.stop_id.map(st)
    e["hour"] = e.ts.dt.hour + e.ts.dt.minute / 60
    prof = e.groupby([e.ts.dt.floor("30min").dt.strftime("%H:%M"), "stop_type"]).boardings.sum().unstack().fillna(0) / n_wd
    fig, ax = plt.subplots(figsize=(10, 4.5))
    prof.plot(ax=ax, lw=1.6)
    ax.set_title("Simulated boardings per 30 min by stop type (weekday mean) - SIMULATED DATA")
    ax.set_xlabel("time of day")
    ax.set_ylabel("boardings")
    fig.tight_layout()
    fig.savefig(FIG / "hourly_profile_by_stop_type.png", dpi=110)
    plt.close(fig)

    r0 = base1[(base1.route_id == "BUS_95") & (base1.direction == 0)].copy()
    r0["lf"] = r0.onboard_load / cap["BUS_95"]
    seq = net.route_stops("BUS_95", 0)
    names = seq.stop_id.map(net.stops.set_index("stop_id").name).values
    r0["seq"] = r0.stop_id.map(dict(zip(seq.stop_id, seq.seq)))
    hm = r0.pivot_table(index="seq", columns=r0.slot_15.dt.strftime("%H:%M"), values="lf", aggfunc="max")
    fig, ax = plt.subplots(figsize=(12, 6))
    im = ax.imshow(hm.values, aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=1.0, interpolation="nearest")
    ax.set_yticks(range(len(hm.index)))
    ax.set_yticklabels([names[i - 1][:24] for i in hm.index], fontsize=7)
    ax.set_xticks(range(0, len(hm.columns), 4))
    ax.set_xticklabels(hm.columns[::4], rotation=90, fontsize=7)
    fig.colorbar(im, ax=ax, label="max load factor")
    ax.set_title("Load-factor heatmap, route 95 Tambaram -> Thiruvanmiyur, one weekday - SIMULATED DATA")
    fig.tight_layout()
    fig.savefig(FIG / "lf_heatmap_bus95_d0.png", dpi=110)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    for m in ("bus", "metro", "mrts"):
        x = ev_wk[ev_wk.route_id.map(modes) == m]
        ax.hist((x.onboard_load / x.route_id.map(cap)).clip(0, 1.0), bins=40, alpha=0.55, label=m, density=True)
    for b in (0.4, 0.75, 1.0):
        ax.axvline(b, color="k", lw=0.6, ls="--")
    ax.legend()
    ax.set_xlabel("load factor at departure (vehicle-stop)")
    ax.set_title("Distribution of vehicle load factors - SIMULATED DATA")
    fig.tight_layout()
    fig.savefig(FIG / "lf_distribution.png", dpi=110)
    plt.close(fig)

    # ---------------- report
    levels = (ev_wk.onboard_load / ev_wk.route_id.map(cap)).map(crowd_level).value_counts(normalize=True)
    lines = [
        "# Twin validation report",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python -m twin.validate`. **All figures are simulated data.**",
        "",
        f"Runs: 7 weekdays from {WEEKDAY0} (5 used) + 2 weekend days, calendar effects off; plus one day each of "
        "`cricket_match`, `rain_heavy`, `extra_trips` (6 extra trips per direction on route 95 in peaks), `cyclone` and "
        "`metro_disruption`, same seed as the baseline day.",
        f"Fitted parameters: `{json.dumps({k: dcfg.get(k) for k in ('base_mode', 'beta_per_km', 'peak_width_scale')})}`",
        "",
        "## Checks",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    lines += [f"| {c} | {'PASS' if ok else '**FAIL**'} | {d} |" for c, ok, d in checks]
    lines += [
        "",
        "## Daily boardings by mode (weekday mean)",
        "",
        "| Mode | Simulated | Target | Error |",
        "|---|---|---|---|",
    ]
    for m, t in target_mode.items():
        v = by_mode.get(m, 0)
        lines.append(f"| {m} | {v:,.0f} | {t:,} | {v / t - 1:+.1%} |")
    lines += [
        "",
        f"Unmet demand (gave up after patience / refused twice / end of service): "
        f"{s_wk['unmet_demand'] / 7:,.0f} per day (7 days incl. weekend); reasons {s_wk['unmet_by_reason']}.",
        f"CROWDED vehicle-stops per weekday: {s_wk['crowded_vehicle_stops'] / 7:,.0f}. "
        f"Crowd-level shares over all vehicle-stops: "
        + ", ".join(f"{k} {v:.0%}" for k, v in levels.items()) + ".",
        "",
        "## MRTS stations against published figures (reported, not fitted)",
        "",
        "| Check | Simulated | Published |",
        "|---|---|---|",
        *[f"| {sid} footfall (boardings + alightings) per weekday | {foot.get(sid, 0):,.0f} | {v:,} |"
          for sid, v in tc["mrts_station_footfall"].items()],
        f"| Share of MRTS boardings at {', '.join(top3['stations'])} | {top3_sim:.0%} | {top3['share']:.0%} (2012) |",
        "",
        "The twin only generates trips between modelled stops, so station footfall that includes riders "
        "from outside the corridor (suburban rail at St. Thomas Mount, buses not modelled) is expected to "
        "come out lower.",
        "",
        "## Figures",
        "",
        "![hourly profile](figures/hourly_profile_by_stop_type.png)",
        "",
        "![LF heatmap](figures/lf_heatmap_bus95_d0.png)",
        "",
        "![LF distribution](figures/lf_distribution.png)",
        "",
        "## Sanity check against reality",
        "",
        "No measured hourly ridership profile for these routes or stations was available to compare against "
        f"(the CMRL figures used are daily/monthly totals). The peak-hour share band "
        f"({tc['peak_hour_share'][0]:.0%}-{tc['peak_hour_share'][1]:.0%}) is itself an assumption. "
        "**No claim of a match to real hourly patterns is made.** The bus total is an assumption (see "
        "ASSUMPTIONS.md); the MRTS total uses a 2023 line-wide figure from before the March 2026 extension; the "
        "metro total is anchored to published figures through an assumed corridor share.",
        "",
        "> A simulation twin calibrated to published ridership totals and designed to ingest real AFC and "
        "sensor feeds. Bus-level counts are assumptions until MTC data is available.",
    ]
    (REPORTS_DIR / "twin_validation.md").write_text("\n".join(lines), encoding="utf8")
    print("\n".join(lines[:30]))
    fails = [c for c, ok, _ in checks if not ok]
    print(f"\n{len(checks) - len(fails)}/{len(checks)} checks passed" + (f"; FAILED: {fails}" if fails else ""))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
