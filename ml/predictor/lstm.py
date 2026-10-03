"""Main model M1 (section 7.3): LSTM over the last 24 slots (6 h) of the feature set, with stop and
route embeddings, predicting the next 12 slots (3 h) of load factor as quantiles q10/q50/q90 plus
boardings. Quantiles are built as q50 -/+ softplus offsets, so lo <= pred <= hi holds by
construction (the spec's crossing penalty is therefore always zero and omitted).

    python -m predictor.lstm --train      # trains on the DB, saves ml/models/lstm_v1.pt
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from common.config import MODELS_DIR

WINDOW = 24
HORIZON = 12
QUANTILES = (0.1, 0.5, 0.9)


class LSTMForecaster(nn.Module):
    def __init__(self, n_feat: int, n_stops: int, n_routes: int, hidden: int = 128, dropout: float = 0.2):
        super().__init__()
        self.emb_stop = nn.Embedding(n_stops, 16)
        self.emb_route = nn.Embedding(n_routes, 8)
        self.lstm = nn.LSTM(n_feat + 24, hidden, num_layers=2, dropout=dropout, batch_first=True)
        self.head = nn.Sequential(nn.Linear(hidden + 24, hidden), nn.ReLU(), nn.Dropout(dropout),
                                  nn.Linear(hidden, HORIZON * 4))

    def forward(self, x, sid, rid):
        e = torch.cat([self.emb_stop(sid), self.emb_route(rid)], dim=1)
        h, _ = self.lstm(torch.cat([x, e[:, None, :].expand(-1, x.shape[1], -1)], dim=2))
        o = self.head(torch.cat([h[:, -1], e], dim=1)).view(-1, HORIZON, 4)
        q50 = o[..., 1]
        q10 = q50 - F.softplus(o[..., 0])
        q90 = q50 + F.softplus(o[..., 2])
        board = F.softplus(o[..., 3])
        return torch.stack([q10, q50, q90], dim=-1), board


def pinball(pred, y, mask):
    """Quantile loss averaged over observed targets. pred B x H x 3, y B x H."""
    loss = 0.0
    for i, q in enumerate(QUANTILES):
        d = y - pred[..., i]
        loss = loss + torch.maximum(q * d, (q - 1) * d)
    return (loss * mask).sum() / mask.sum().clamp(min=1)


class WindowData:
    """Gathers (window, target) samples from the S x T x F panel tensor without copying it."""

    def __init__(self, X, lf, board, mean, std):
        self.X = torch.from_numpy(((X - mean) / std).astype(np.float32))
        self.lf = torch.from_numpy(np.nan_to_num(lf, nan=0.0).astype(np.float32))
        self.mask = torch.from_numpy((~np.isnan(lf)).astype(np.float32))
        self.board = torch.from_numpy(board.astype(np.float32))

    def batch(self, s_idx: np.ndarray, t_idx: np.ndarray):
        s = torch.from_numpy(s_idx)
        tw = torch.from_numpy(t_idx[:, None] + np.arange(-WINDOW + 1, 1)[None, :])
        th = torch.from_numpy(t_idx[:, None] + np.arange(1, HORIZON + 1)[None, :])
        x = self.X[s[:, None], tw]
        T = self.lf.shape[1]
        thc = th.clamp(max=T - 1)
        y = self.lf[s[:, None], thc]
        m = self.mask[s[:, None], thc] * (th < T).float()
        b = self.board[s[:, None], thc]
        return x, y, m, b


def origins_for(panel_times, t_from: int, t_to: int, lf: np.ndarray, service=(5, 23)):
    """(s, t) origin pairs in [t_from, t_to) during service hours with >= 1 observed target ahead."""
    S, T = lf.shape
    hours = panel_times.hour.values
    ts = np.arange(max(t_from, WINDOW), min(t_to, T - 1))
    ts = ts[(hours[ts] >= service[0]) & (hours[ts] < service[1])]
    obs = ~np.isnan(lf)
    ahead = np.zeros_like(obs)
    for h in range(1, HORIZON + 1):
        ahead[:, :-h] |= obs[:, h:]
    s_all, t_all = np.meshgrid(np.arange(S), ts, indexing="ij")
    keep = ahead[s_all, t_all]
    return s_all[keep], t_all[keep]


def train(X, lf, board, series, times, t_train_end, t_val_end, epochs=40, batch=256, samples_per_epoch=120_000,
          lr=1e-3, patience=6, seed=0, log=print):
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    torch.set_num_threads(max(1, min(12, torch.get_num_threads())))
    cap = series.capacity.values[:, None].astype(np.float32)
    board_n = board / cap
    warmup = min(7 * 96, t_train_end // 3)  # first week only warms up the lags (less for tiny datasets)
    tr_s, tr_t = origins_for(times, warmup, t_train_end, lf)
    va_s, va_t = origins_for(times, t_train_end, t_val_end, lf)
    # scaler from training positions
    sub = rng.choice(len(tr_s), size=min(200_000, len(tr_s)), replace=False)
    sample = X[tr_s[sub], tr_t[sub]]
    mean, std = sample.mean(axis=0), sample.std(axis=0) + 1e-6
    data = WindowData(X, lf, board_n, mean, std)
    routes = sorted(series.route_id.unique())
    rid_of = np.array([routes.index(r) for r in series.route_id])
    model = LSTMForecaster(X.shape[2], len(series), len(routes))
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    va_sel = rng.choice(len(va_s), size=min(40_000, len(va_s)), replace=False)
    best, best_state, bad = np.inf, None, 0
    # peak-heavy sampling: target slots in peaks are what matters operationally
    hrs = times.hour.values[tr_t]
    w = np.where(((hrs >= 7) & (hrs < 10)) | ((hrs >= 16) & (hrs < 20)), 2.0, 1.0)
    w /= w.sum()
    for ep in range(epochs):
        t0 = time.time()
        model.train()
        idx = rng.choice(len(tr_s), size=min(samples_per_epoch, len(tr_s)), replace=True, p=w)
        tot = 0.0
        for k in range(0, len(idx), batch):
            j = idx[k:k + batch]
            x, y, m, b = data.batch(tr_s[j], tr_t[j])
            q, bp = model(x, torch.from_numpy(tr_s[j]), torch.from_numpy(rid_of[tr_s[j]]))
            loss = pinball(q, y, m) + 0.5 * ((bp - b).abs() * m).sum() / m.sum().clamp(min=1)
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot += loss.item() * len(j)
        model.eval()
        with torch.no_grad():
            err, n = 0.0, 0.0
            for k in range(0, len(va_sel), 2048):
                j = va_sel[k:k + 2048]
                x, y, m, _ = data.batch(va_s[j], va_t[j])
                q, _ = model(x, torch.from_numpy(va_s[j]), torch.from_numpy(rid_of[va_s[j]]))
                err += ((q[..., 1] - y).abs() * m).sum().item()
                n += m.sum().item()
        val_mae = err / max(n, 1)
        log(f"epoch {ep:02d} train_loss {tot / len(idx):.4f} val_MAE(LF) {val_mae:.4f} ({time.time() - t0:.0f}s)")
        if val_mae < best - 1e-4:
            best, bad = val_mae, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                log(f"early stop at epoch {ep}")
                break
    model.load_state_dict(best_state)
    return model, mean, std, routes, best


def save(model, mean, std, routes, feature_names, series, path=None, meta=None):
    path = path or MODELS_DIR / "lstm_v1.pt"
    MODELS_DIR.mkdir(exist_ok=True)
    torch.save({"state": model.state_dict(), "mean": mean, "std": std, "routes": routes,
                "features": feature_names, "n_feat": len(feature_names), "n_stops": len(series),
                "series_keys": list(zip(series.route_id, series.direction.astype(int), series.stop_id)),
                "meta": meta or {}}, path)


def load(path=None):
    path = path or MODELS_DIR / "lstm_v1.pt"
    ck = torch.load(path, weights_only=False)
    m = LSTMForecaster(ck["n_feat"], ck["n_stops"], len(ck["routes"]))
    m.load_state_dict(ck["state"])
    m.eval()
    return m, ck


@torch.no_grad()
def predict(model, ck, X, series, s_idx, t_idx, batch=4096):
    """Returns q (N x H x 3) load factor quantiles and boardings (N x H, in passengers)."""
    data = WindowData(X, np.zeros(X.shape[:2], np.float32), np.zeros(X.shape[:2], np.float32), ck["mean"], ck["std"])
    rid_of = np.array([ck["routes"].index(r) for r in series.route_id])
    qs, bs = [], []
    for k in range(0, len(s_idx), batch):
        s, t = s_idx[k:k + batch], t_idx[k:k + batch]
        x, _, _, _ = data.batch(s, t)
        q, b = model(x, torch.from_numpy(s), torch.from_numpy(rid_of[s]))
        qs.append(q.numpy())
        bs.append(b.numpy() * series.capacity.values[s][:, None])
    return np.concatenate(qs), np.concatenate(bs)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    a = ap.parse_args()
    if a.train:
        from predictor.evaluate import main as ev_main

        ev_main(["--train-only"])
