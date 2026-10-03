"""Demand model (section 5.3): top-down daily totals -> stop-type 15-minute profiles -> stochastic
arrivals per station and slot -> gravity destination choice. Mode/route choice happens inside the
simulation (agents.choose_options) so it can react to observed crowding."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.config import hhmm_to_min

SLOTS = 96
SLOT_MIN = 15
TYPES = ["office", "college", "market", "residential", "hospital", "interchange"]


def slot_profiles(dcfg: dict, day_type: str, svc_start: int, svc_end: int) -> dict[str, np.ndarray]:
    """15-minute production shares per stop type, summing to 1 over the service day."""
    centers = (np.arange(SLOTS) + 0.5) * SLOT_MIN
    in_service = (centers >= svc_start) & (centers <= svc_end)
    wk = day_type != "weekday"
    wcfg = dcfg["weekend"]
    scale = dcfg.get("peak_width_scale", 1.0)
    out = {}
    for t in TYPES:
        p = dcfg["profiles"][t]
        y = np.full(SLOTS, float(p["base"]))
        for pk in p["peaks"]:
            mu = hhmm_to_min(pk["at"]) + (wcfg["shift_min"] if wk else 0)
            sd = pk["width_min"] * scale * (wcfg["width_mult"] if wk else 1.0)
            y += pk["w"] * np.exp(-0.5 * ((centers - mu) / sd) ** 2) * (60.0 / sd)
        y = np.where(in_service, y, 0.0)
        out[t] = y / y.sum()
    return out


@dataclass
class DayContext:
    date: pd.Timestamp
    day_type: str                 # weekday | weekend | holiday
    precip_mm: float
    weather: str                  # dry | light | heavy
    events: list                  # rows from data/events.csv active on this date


def generate_arrivals(paths, net, dcfg: dict, ctx: DayContext, scen, rng: np.random.Generator,
                      svc_start: int, svc_end: int) -> pd.DataFrame:
    """Commuter arrivals for one day: columns t (min after midnight), o, d (station indices)."""
    st = net.stations
    n = len(st)
    types = st.stop_type.values
    w = st.weight.values.astype(float).copy()
    w_norm = w.sum()  # normalise by unscaled weights so base_mode scales each mode independently
    # base_mode: per-mode production scale (calibrated). Multi-mode stations take the mean.
    bm = dcfg.get("base_mode", {})
    w *= np.array([np.mean([bm.get(m, 1.0) for m in ms.split(",")]) for ms in st.modes.values])

    # Daily total D = base * day_type * season * event * noise (weather per mode via thinning later)
    day_mult = 1.0 if ctx.day_type == "weekday" else dcfg["weekend"]["total_mult"]
    if scen.day_type == "weekend":
        day_mult = dcfg["weekend"]["total_mult"]
    D = (dcfg["base_daily_trips"] * day_mult * dcfg.get("season_mult", 1.0) * scen.day_total_mult
         * np.exp(rng.normal(0, dcfg.get("day_noise_sigma", 0.0))))
    D *= scen.max_mode_mult  # oversample; thinned per mode after choice

    profiles = slot_profiles(dcfg, "weekend" if scen.day_type == "weekend" else ctx.day_type, svc_start, svc_end)
    prof = np.stack([profiles[t] for t in types])               # n x 96
    stmult = np.array([scen.stop_type_mult.get(t, 1.0) for t in types])
    mean = D * (w / w_norm)[:, None] * prof * stmult[:, None]  # n x 96

    # Event surges: production after the event at the venue (people leaving), attraction before.
    attract_surge = []  # (station_idx, slot_from, slot_to, factor)
    for s in scen.surges:
        if s["station"] is None:
            continue
        k0, k1 = int(s["from_min"] // SLOT_MIN), int(min(SLOTS, np.ceil(s["to_min"] / SLOT_MIN)))
        if s["kind"] == "produce":
            mean[s["station"], k0:k1] *= s["factor"]
        else:
            attract_surge.append((s["station"], k0, k1, s["factor"]))

    # Arrivals: negative binomial (dispersion k) or Poisson
    arr = dcfg.get("arrival", {})
    if arr.get("dist") == "negbin":
        k = float(arr.get("k", 8))
        counts = rng.negative_binomial(k, k / (k + np.maximum(mean, 1e-9)))
    else:
        counts = rng.poisson(mean)
    counts = np.where(mean > 0, counts, 0)

    # Gravity destination choice, direction-aware (AM/PM attraction by stop type)
    beta = dcfg["beta_per_km"]
    att = dcfg["attraction"]
    base_g = np.exp(-beta * paths.km) * paths.reach
    w_am = w * np.array([att[t]["am"] for t in types])
    w_pm = w * np.array([att[t]["pm"] for t in types])

    ts, os_, ds = [], [], []
    noon = 13 * 60 // SLOT_MIN
    for o in range(n):
        row_c = counts[o]
        if row_c.sum() == 0 or not paths.reach[o].any():
            continue
        g_am, g_pm = base_g[o] * w_am, base_g[o] * w_pm
        for kslot in np.nonzero(row_c)[0]:
            c = int(row_c[kslot])
            g = (g_am if kslot < noon else g_pm).copy()
            for (si, k0, k1, f) in attract_surge:
                if k0 <= kslot < k1:
                    g[si] *= f
            tot = g.sum()
            if tot <= 0:
                continue
            dest = rng.choice(n, size=c, p=g / tot)
            ts.append(kslot * SLOT_MIN + rng.uniform(0, SLOT_MIN, size=c))
            os_.append(np.full(c, o))
            ds.append(dest)
    if not ts:
        return pd.DataFrame({"t": [], "o": [], "d": []})
    df = pd.DataFrame({"t": np.concatenate(ts), "o": np.concatenate(os_), "d": np.concatenate(ds)})
    return df.sort_values("t", kind="stable").reset_index(drop=True)
