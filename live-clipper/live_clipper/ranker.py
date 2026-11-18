"""Learned moment ranker: trained on per-second features, labelled by viewer-made Twitch clips and their views."""
import logging
import math
import time
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

COLS = ["chat", "users", "z_chat", "z_audio", "loud", "laugh", "shock", "hype", "clipword", "viewers"]
WINDOWS = (5, 15, 30)
MIN_POSITIVES = 30


def _matrix(rows: list[tuple]) -> tuple[np.ndarray, np.ndarray]:
    """rows: (sec, *COLS) sorted by sec for one channel -> rolling-window features per second."""
    a = np.array([[np.nan if v is None else v for v in r] for r in rows], dtype=float)
    secs, x = a[:, 0], np.nan_to_num(a[:, 1:], nan=-60.0)
    feats = []
    for w in WINDOWS:
        k = np.ones(w) / w
        mean = np.vstack([np.convolve(x[:, j], k, mode="full")[: len(x)] for j in range(x.shape[1])]).T
        feats.append(mean)
    base = np.vstack([np.convolve(x[:, 0], np.ones(300) / 300, mode="full")[: len(x)]]).T + 1e-3
    feats.append(feats[0][:, :1] / base)
    feats.append(np.log1p(x[:, -1:]))
    return secs, np.hstack(feats)


def dataset(store, since: float):
    X, y, w, groups = [], [], [], []
    for login in [r["login"] for r in store.rows("SELECT DISTINCT login FROM features WHERE sec > ?", since)]:
        rows = [tuple(r.values()) for r in store.rows(
            f"SELECT sec, {', '.join(COLS)} FROM features WHERE login = ? AND sec > ? ORDER BY sec", login, since)]
        if len(rows) < 600:
            continue
        secs, feats = _matrix(rows)
        label = np.zeros(len(secs))
        for v in store.rows("SELECT created, duration, views FROM viewer_clips WHERE login = ? AND created BETWEEN ? AND ?",
                            login, secs[0], secs[-1] + 60):
            # a viewer clip ends when it is created; the chat reaction peaks a few seconds after the event
            lo, hi = v["created"] - v["duration"], v["created"] + 10
            label[(secs >= lo) & (secs <= hi)] = np.maximum(label[(secs >= lo) & (secs <= hi)], math.log1p(v["views"]))
        keep = np.arange(len(secs)) % 3 == 0
        X.append(feats[keep])
        y.append(label[keep])
        w.append(secs[keep])
        groups += [login] * int(keep.sum())
    if not X:
        return None
    return np.vstack(X), np.concatenate(y), np.concatenate(w), np.array(groups)


def _recall_at(score: np.ndarray, y: np.ndarray, secs: np.ndarray, share: float = 0.02) -> float:
    """Share of popular-clip seconds ranked in the top `share` of all seconds (what a clipper would actually cut)."""
    pos = y >= math.log1p(300)
    if not pos.any():
        return float("nan")
    thr = np.quantile(score, 1 - share)
    return float((score[pos] >= thr).mean())


def train(store, data_dir: Path, days: float = 7) -> dict:
    from joblib import dump
    from sklearn.ensemble import HistGradientBoostingRegressor

    d = dataset(store, time.time() - days * 86400)
    if d is None:
        return {"ok": False, "reason": "мало данных: нужно хотя бы 10 минут признаков по стриму"}
    X, y, secs, _ = d
    positives = int((y >= math.log1p(300)).sum() // 5)
    if positives < MIN_POSITIVES:
        return {"ok": False, "reason": f"мало популярных зрительских клипов в данных ({positives} из {MIN_POSITIVES})"}
    order = np.argsort(secs)
    cut = order[int(len(order) * 0.8)]
    tr, te = secs < secs[cut], secs >= secs[cut]
    model = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.08, max_leaf_nodes=31, l2_regularization=1.0)
    model.fit(X[tr], y[tr])
    pred = model.predict(X[te])
    baseline = X[te][:, 2] + X[te][:, 3]  # 5-s mean of z_chat + z_audio: what the current detector uses
    res = {"ok": True, "trained_at": time.time(), "samples": int(len(y)), "positives": positives,
           "recall_model": round(_recall_at(pred, y[te], secs[te]), 3),
           "recall_detector": round(_recall_at(baseline, y[te], secs[te]), 3)}
    res["promoted"] = bool(res["recall_model"] > res["recall_detector"] + 0.02)
    if res["promoted"]:
        res["threshold"] = float(np.quantile(model.predict(X), 0.995))
        dump({"model": model, "meta": res}, data_dir / "ranker.joblib")
    return res


class Ranker:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "ranker.joblib"
        self.model, self.meta, self.loaded_at = None, None, 0.0
        self.load()

    def load(self):
        if self.path.exists():
            from joblib import load
            obj = load(self.path)
            self.model, self.meta, self.loaded_at = obj["model"], obj["meta"], time.time()

    def score(self, rows: list[tuple]) -> float | None:
        if not self.model or len(rows) < 40:
            return None
        _, feats = _matrix(rows)
        return float(self.model.predict(feats[-1:])[0])
