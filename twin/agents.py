"""Vehicle and commuter processes (sections 5.1-5.4).

Vehicles are SimPy processes that follow their route_stop sequence: travel, alight, board up to
capacity (FIFO), dwell, depart, and emit one event row per stop visit. Commuters are lightweight
records (not one SimPy process each, so a corridor-day with ~150k trips runs in seconds): a
dispatcher process releases each 15-minute batch of arrivals, makes the mode/route logit choice
using the crowding observed so far, and places commuters in the stop queues. Crowding and
left-behind passengers emerge from capacity limits; nothing about them is sampled.
"""
from __future__ import annotations

import heapq
import math
from collections import defaultdict, deque

import numpy as np
import pandas as pd
import simpy

from common.config import crowd_level, hhmm_to_min, level_index

SLOT_MIN = 15
PAY_MODES = ("card", "qr", "cash")
LAYOVER_MIN = 6


class _Queue:
    __slots__ = ("pending", "waiting")

    def __init__(self):
        self.pending = []          # heap of (t_arrival, cid): commuters not yet at the stop
        self.waiting = deque()     # cids at the stop, FIFO


class TwinSim:
    def __init__(self, net, paths, dcfg, ccfg, scen, ctx, rng: np.random.Generator, run_id: str):
        self.net, self.paths, self.dcfg, self.ccfg, self.scen, self.ctx = net, paths, dcfg, ccfg, scen, ctx
        self.rng = rng
        self.run_id = run_id
        self.svc_start = hhmm_to_min(ccfg["service_day"]["start"])
        self.svc_end = hhmm_to_min(ccfg["service_day"]["end"])
        self.env = simpy.Environment(initial_time=self.svc_start - 60)

        r = net.routes.set_index("route_id")
        self.mode = r["mode"].to_dict()
        self.capacity = r["capacity_total"].astype(int).to_dict()
        self.rs = {}
        for (rid, d), g in net.route_stop.groupby(["route_id", "direction"]):
            g = g.sort_values("seq")
            self.rs[(rid, d)] = (g.seq.to_numpy(), g.stop_id.to_numpy(), g.run_min.to_numpy())
        self.queues: dict[tuple, _Queue] = defaultdict(_Queue)
        self.obs_lf: dict[tuple, float] = {}  # (route, dir, seq) -> last departing load factor

        lg = dcfg["logit"]
        self.a, self.b, self.c, self.dcrowd, self.e = lg["a_per_min"], lg["b_per_inr"], lg["c_per_min"], lg["d_crowd"], lg["e_transfer"]
        self.asc = dcfg["asc"]
        self.traffic = [(hhmm_to_min(a), hhmm_to_min(b), f) for a, b, f in dcfg["ops"]["traffic"]]
        self.pay = {m: np.cumsum([dcfg["payment"][m][p] for p in PAY_MODES]) for m in ("bus", "metro", "mrts")}
        pt = dcfg["patience"]
        self.pat_mu = math.log(pt["mean_min"]) - 0.5 * pt["sigma"] ** 2
        self.pat_sigma = pt["sigma"]
        self.switch_p = dcfg["switch_prob_if_alternative"]

        # commuter state (parallel lists)
        self.c_opt, self.c_leg, self.c_tstop, self.c_t0, self.c_pat = [], [], [], [], []
        self.c_ref, self.c_sw, self.c_pay, self.c_od = [], [], [], []
        self.events, self.unmet = [], []
        self.stats = defaultdict(float)
        self.timetable = self._timetable()
        self.headway = self._headway_table()

    # ---------------------------------------------------------------- timetable and supply
    def _timetable(self) -> pd.DataFrame:
        tt = self.net.timetable[["route_id", "direction", "start_min"]].copy()
        tt["extra"] = False
        for hc in self.scen.headway_changes:
            m = tt.route_id.map(self.mode).isin(hc["modes"]) & tt.start_min.between(hc["from_min"], hc["to_min"])
            mult = hc["mult"]
            keep = np.ones(len(tt), dtype=bool)
            for _, g in tt[m].groupby(["route_id", "direction"]):
                idx = g.sort_values("start_min").index
                if math.isinf(mult):  # service suspended
                    drop = idx
                else:  # keep every mult-th trip (fractional: 1.35 keeps ~74%)
                    i = np.arange(len(idx))
                    drop = idx[(i > 0) & (np.floor(i / mult) == np.floor((i - 1) / mult))]
                keep[tt.index.get_indexer(drop)] = False
            tt = tt[keep]
        rows = []
        for x in self.scen.extra_trips:
            dirs = [x["direction"]] if x.get("direction") is not None else [0, 1]
            a, b = hhmm_to_min(x["start"]), hhmm_to_min(x["end"])
            for d in dirs:
                for j in range(int(x["n"])):
                    rows.append({"route_id": x["route"], "direction": d, "start_min": a + (b - a) * (j + 0.5) / x["n"], "extra": True})
        if rows:
            tt = pd.concat([tt, pd.DataFrame(rows)], ignore_index=True)
        tt = tt.sort_values("start_min").reset_index(drop=True)
        tt["trip_id"] = [f"{r}_{d}_{self.ctx.date:%Y%m%d}_{int(m):04d}{'x' if e else ''}{i}"
                         for i, (r, d, m, e) in enumerate(zip(tt.route_id, tt.direction, tt.start_min, tt.extra))]
        # vehicle blocks: reuse a vehicle that has finished at this terminal
        free: dict[tuple, list] = defaultdict(list)
        count: dict[str, int] = defaultdict(int)
        vids = []
        for r, d, m in zip(tt.route_id, tt.direction, tt.start_min):
            seq, stops, run = self.rs[(r, d)]
            dur = run.sum() * 1.25 + 0.5 * len(seq)
            q = free[(r, stops[0])]
            if q and q[0][0] <= m:
                _, vid = heapq.heappop(q)
            else:
                count[r] += 1
                vid = f"{r}-V{count[r]:03d}"
            vids.append(vid)
            heapq.heappush(free[(r, stops[-1])], (m + dur + LAYOVER_MIN, vid))
        tt["vehicle_id"] = vids
        return tt

    def _headway_table(self) -> dict:
        """Scheduled headway (min) per (route, dir) and 15-min slot, from the (modified) timetable."""
        out = {}
        for (r, d), g in self.timetable.groupby(["route_id", "direction"]):
            starts = np.sort(g.start_min.values)
            hw = np.full(96, 60.0)
            for k in range(96):
                c = k * SLOT_MIN + 7.5
                n = ((starts >= c - 30) & (starts < c + 30)).sum()
                if n:
                    hw[k] = 60.0 / n
            out[(r, d)] = hw
        return out

    def _traffic(self, t: float) -> float:
        for a, b, f in self.traffic:
            if a <= t < b:
                return f
        return 1.0

    # ---------------------------------------------------------------- choice
    def _utilities(self, opts, k: int) -> np.ndarray:
        u = np.empty(len(opts))
        k = min(max(k, 0), 95)
        for i, o in enumerate(opts):
            wait = 0.0
            crowd = 0.0
            for leg in o.legs:
                if (leg.route_id, leg.direction) not in self.headway:  # no service today (suspended)
                    crowd += 30
                    continue
                wait += 0.5 * self.headway[(leg.route_id, leg.direction)][k]
                lf = self.obs_lf.get((leg.route_id, leg.direction, leg.board_seq))
                if lf is not None:
                    crowd += max(0, level_index(crowd_level(lf)) - 1)
            run_mult = self.scen.run_time_mult if "bus" in o.modes else 1.0
            u[i] = (sum(self.asc[m] for m in set(o.modes)) - self.a * (o.ivt * run_mult + o.walk + o.egress)
                    - self.b * (o.fare + o.egress_fare) - self.c * wait - self.dcrowd * crowd - self.e * o.transfers)
        return u

    def _enqueue(self, cid: int, t: float):
        leg = self.c_opt[cid].legs[self.c_leg[cid]]
        self.c_tstop[cid] = t
        heapq.heappush(self.queues[(leg.route_id, leg.direction, leg.board_seq)].pending, (t, cid))

    def dispatcher(self, arrivals: pd.DataFrame):
        t_all, o_all, d_all = arrivals.t.to_numpy(), arrivals.o.to_numpy(), arrivals.d.to_numpy()
        n_st = len(self.paths.st_ids)
        maxm = self.scen.max_mode_mult
        for k in range(self.svc_start // SLOT_MIN, self.svc_end // SLOT_MIN + 1):
            yield self.env.timeout(max(0.0, k * SLOT_MIN - self.env.now))
            a, b = np.searchsorted(t_all, [k * SLOT_MIN, (k + 1) * SLOT_MIN])
            if a == b:
                continue
            key = o_all[a:b] * n_st + d_all[a:b]
            uk, inv = np.unique(key, return_inverse=True)
            for gi, kk in enumerate(uk):
                opts = self.paths.options.get((int(kk // n_st), int(kk % n_st)))
                if not opts:
                    continue
                members = np.nonzero(inv == gi)[0] + a
                u = self._utilities(opts, k)
                p = np.exp(u - u.max())
                p /= p.sum()
                picks = self.rng.choice(len(opts), size=len(members), p=p)
                keep_u = self.rng.random(len(members))
                pat = self.rng.lognormal(self.pat_mu, self.pat_sigma, len(members))
                pay_u = self.rng.random(len(members))
                for j, ci in enumerate(members):
                    opt = opts[picks[j]]
                    main = max(opt.legs, key=lambda l: l.ivt).mode
                    if keep_u[j] > self.scen.demand_mult.get(main, 1.0) / maxm:
                        continue  # thinning for per-mode demand multipliers
                    cid = len(self.c_opt)
                    self.c_opt.append(opt)
                    self.c_leg.append(0)
                    self.c_tstop.append(0.0)
                    self.c_t0.append(float(t_all[ci]))
                    self.c_pat.append(float(pat[j]))
                    self.c_ref.append(0)
                    self.c_sw.append(False)
                    self.c_pay.append(float(pay_u[j]))
                    self.c_od.append(int(kk))
                    self._enqueue(cid, float(t_all[ci]))

    # ---------------------------------------------------------------- abandonment / switching
    def _give_up(self, cid: int, now: float, stop_id: str, route_id: str, reason: str):
        n_st = len(self.paths.st_ids)
        if self.c_leg[cid] == 0 and not self.c_sw[cid] and self.rng.random() < self.switch_p:
            od = self.c_od[cid]
            cur = self.c_opt[cid]
            alts = [o for o in self.paths.options.get((od // n_st, od % n_st), [])
                    if o.legs[0].route_id != cur.legs[0].route_id]
            if alts:
                u = self._utilities(alts, int(now // SLOT_MIN))
                p = np.exp(u - u.max())
                p /= p.sum()
                self.c_opt[cid] = alts[int(self.rng.choice(len(alts), p=p))]
                self.c_sw[cid] = True
                self.c_ref[cid] = 0
                self.stats["switched"] += 1
                self._enqueue(cid, now)
                return
        self.stats["unmet"] += 1
        self.unmet.append((now, stop_id, route_id, reason))

    # ---------------------------------------------------------------- vehicle process
    def vehicle(self, trip):
        r, d = trip.route_id, trip.direction
        mode = self.mode[r]
        cap = self.capacity[r]
        seqs, stops, run = self.rs[(r, d)]
        dw = self.ccfg["dwell"][mode]
        sigma = self.dcfg["ops"]["run_time_sigma"][mode]
        delay_mean = self.dcfg["ops"]["dispatch_delay_min"][mode] * self.scen.dispatch_delay_mult.get(mode, 1.0)
        delay = self.rng.exponential(delay_mean) if delay_mean > 0 else 0.0
        yield self.env.timeout(max(0.0, trip.start_min + delay - self.env.now))
        onboard: dict[int, list] = defaultdict(list)
        load = 0
        last = len(seqs) - 1
        for i in range(len(seqs)):
            if i > 0:
                f = self.scen.run_time_mult * (self._traffic(self.env.now) if mode == "bus" else 1.0)
                yield self.env.timeout(run[i] * f * self.rng.lognormal(0, sigma))
            now = self.env.now
            seq = int(seqs[i])
            alight = onboard.pop(seq, [])
            load -= len(alight)
            for cid in alight:
                legs = self.c_opt[cid].legs
                if self.c_leg[cid] + 1 < len(legs):
                    self.c_leg[cid] += 1
                    self.stats["transfers"] += 1
                    self._enqueue(cid, now + self.c_opt[cid].walk)
                else:
                    self.stats["completed"] += 1
                    self.stats["journey_min"] += now - self.c_t0[cid]
            boarders, refused = [], 0
            q = self.queues.get((r, d, seq))
            if q is not None and i < last:
                while q.pending and q.pending[0][0] <= now:
                    q.waiting.append(heapq.heappop(q.pending)[1])
                if q.waiting:
                    stay = deque()
                    # patience counts the wait beyond the scheduled headway (people time their arrival
                    # to the timetable; waiting a full headway is expected, not a reason to give up)
                    hw = self.headway[(r, d)][min(95, int(now // SLOT_MIN))]
                    for cid in q.waiting:
                        if now - self.c_tstop[cid] > hw + self.c_pat[cid]:
                            self._give_up(cid, now, stops[i], r, "patience")
                        else:
                            stay.append(cid)
                    q.waiting = stay
                space = cap - load
                while q.waiting and space > 0:
                    boarders.append(q.waiting.popleft())
                    space -= 1
                refused = len(q.waiting)
                if refused:
                    stay = deque()
                    for cid in q.waiting:
                        self.c_ref[cid] += 1
                        if self.c_ref[cid] >= 2:
                            self._give_up(cid, now, stops[i], r, "refused_twice")
                        else:
                            stay.append(cid)
                    q.waiting = stay
            nb, na = len(boarders), len(alight)
            dwell_s = dw["d0"] + dw["a"] * nb + dw["b"] * na
            yield self.env.timeout(dwell_s / 60.0)
            fare = 0.0
            pays = [0, 0, 0]
            for cid in boarders:
                opt = self.c_opt[cid]
                leg = opt.legs[self.c_leg[cid]]
                onboard[leg.alight_seq].append(cid)
                self.stats["wait_min"] += now - self.c_tstop[cid]
                self.stats["boardings"] += 1
                fare += opt.fare / len(opt.legs)
                pays[int(np.searchsorted(self.pay[mode], self.c_pay[cid] * self.pay[mode][-1], side="right").clip(0, 2))] += 1
            load += nb
            assert 0 <= load <= cap, (r, trip.trip_id, load)
            self.obs_lf[(r, d, seq)] = load / cap
            self.events.append((self.env.now, r, trip.trip_id, trip.vehicle_id, stops[i], d, nb, na, load,
                                len(q.waiting) if q is not None else 0, refused,
                                PAY_MODES[int(np.argmax(pays))] if nb else None, round(fare, 2)))

    # ---------------------------------------------------------------- run
    def run(self, arrivals: pd.DataFrame):
        self.env.process(self.dispatcher(arrivals))
        for trip in self.timetable.itertuples(index=False):
            self.env.process(self.vehicle(trip))
        self.env.run(until=self.svc_end + 240)
        # anyone still queued at the end of service could not travel
        for key, q in self.queues.items():
            for _, cid in q.pending:
                self.unmet.append((self.svc_end, None, key[0], "end_of_service"))
            for cid in q.waiting:
                self.unmet.append((self.svc_end, None, key[0], "end_of_service"))
        self.stats["commuters"] = len(self.c_opt)
        return self.events, self.unmet, dict(self.stats)
