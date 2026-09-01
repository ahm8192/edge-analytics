"""
Walk-forward eğitim ve doğrulama.

Tek soru: model kapanış oranından daha iyi olasılık üretiyor mu?
Cevap hayırsa proje burada durur (docs/egitim-boru-hatti.md, durma kuralları).
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from app.models.dixon_coles import DixonColes, build_matrix, market_1x2
from app.models.metrics import multiclass_log_loss, rps
from app.models.calibration import expected_calibration_error, reliability_curve
from app.models.ensemble import blend_with_market
from app.market.devig import devig_shin, devig_multiplicative

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("train")

OUTCOME = {"HOME": 0, "DRAW": 1, "AWAY": 2}


def load_matches(conn, league_code: str = "Premier League") -> pd.DataFrame:
    df = pd.read_sql_query("""
        SELECT m.id, m.kickoff_utc, m.season,
               th.canonical_name AS home, ta.canonical_name AS away,
               m.home_goals AS hg, m.away_goals AS ag
        FROM match m
        JOIN team th ON th.id = m.home_team_id
        JOIN team ta ON ta.id = m.away_team_id
        JOIN league l ON l.id = m.league_id
        WHERE l.name = ? AND m.status = 'finished'
        ORDER BY m.kickoff_utc""", conn, params=(league_code,))
    df["date"] = pd.to_datetime(df.kickoff_utc, format="ISO8601", utc=True)

    odds = pd.read_sql_query("""
        SELECT o.match_id, b.code AS book, o.selection, o.price
        FROM odds_snapshot o JOIN bookmaker b ON b.id = o.bookmaker_id
        WHERE o.market = '1X2'""", conn)
    wide = odds.pivot_table(index="match_id", columns=["book", "selection"],
                            values="price", aggfunc="first")
    wide.columns = [f"{b}_{s}" for b, s in wide.columns]
    return df.merge(wide, left_on="id", right_index=True, how="left")


def market_probs(df: pd.DataFrame, prefix: str, method="shin") -> np.ndarray:
    cols = [f"{prefix}_HOME", f"{prefix}_DRAW", f"{prefix}_AWAY"]
    fn = devig_shin if method == "shin" else devig_multiplicative
    out = np.full((len(df), 3), np.nan)
    for i, (_, r) in enumerate(df[cols].iterrows()):
        if r.notna().all():
            out[i] = fn([float(r[c]) for c in cols])
    return out


def run(conn, xi: float, train_years: float, step_days: int,
        start: str, blend_weight: float) -> dict:
    df = load_matches(conn)
    df = df.dropna(subset=["market_avg_HOME"]).reset_index(drop=True)
    log.info("Maç: %d  |  %s → %s  |  takım: %d",
             len(df), df.date.min().date(), df.date.max().date(),
             len(set(df.home) | set(df.away)))

    y = np.array([0 if h > a else (1 if h == a else 2)
                  for h, a in zip(df.hg, df.ag)])

    test_start = pd.Timestamp(start, tz="UTC")
    cursor = test_start
    end = df.date.max()

    rows = []
    fold = 0
    while cursor < end:
        stop = cursor + pd.Timedelta(days=step_days)
        train_mask = (df.date < cursor) & \
                     (df.date >= cursor - pd.Timedelta(days=365 * train_years))
        test_mask = (df.date >= cursor) & (df.date < stop)

        if test_mask.sum() == 0 or train_mask.sum() < 300:
            cursor = stop
            continue

        tr, te = df[train_mask], df[test_mask]
        teams = sorted(set(tr.home) | set(tr.away) | set(te.home) | set(te.away))
        days_ago = (cursor - tr.date).dt.total_seconds().to_numpy() / 86400

        model = DixonColes(xi=xi)
        model.fit(tr.home.to_numpy(), tr.away.to_numpy(),
                  tr.hg.to_numpy(), tr.ag.to_numpy(), days_ago, teams)

        p = model.params
        preds = np.zeros((len(te), 3))
        for i, (_, r) in enumerate(te.iterrows()):
            lam = np.exp(p.attack[r.home] - p.defence[r.away] + p.home_adv)
            mu = np.exp(p.attack[r.away] - p.defence[r.home])
            m = build_matrix(float(np.clip(lam, .05, 6)),
                             float(np.clip(mu, .05, 6)), p.rho)
            d = market_1x2(m)
            preds[i] = [d["HOME"], d["DRAW"], d["AWAY"]]

        rows.append({"fold": fold, "date": cursor, "n_train": int(train_mask.sum()),
                     "idx": np.where(test_mask)[0], "model": preds})
        fold += 1
        cursor = stop
        if fold % 10 == 0:
            log.info("  kat %d  (%s, eğitim %d maç)", fold, cursor.date(), train_mask.sum())

    idx = np.concatenate([r["idx"] for r in rows])
    model_p = np.vstack([r["model"] for r in rows])
    y_test = y[idx]
    sub = df.iloc[idx].reset_index(drop=True)

    avg_p = market_probs(sub, "market_avg")
    best_p = market_probs(sub, "market_best")

    ok = ~np.isnan(avg_p).any(axis=1)
    model_p, avg_p, y_test = model_p[ok], avg_p[ok], y_test[ok]
    best_p = best_p[ok]
    sub = sub[ok].reset_index(drop=True)

    blended = blend_with_market(model_p, avg_p, blend_weight)

    res = {
        "n_test": int(len(y_test)),
        "n_folds": fold,
        "xi": xi,
        "half_life_days": float(np.log(2) / xi),
        "model": _score(model_p, y_test),
        "market": _score(avg_p, y_test),
        "blend": _score(blended, y_test),
        "coin_flip": _score(np.full_like(model_p, 1 / 3), y_test),
    }
    res["skill_vs_market"] = (res["market"]["log_loss"] - res["model"]["log_loss"]) \
        / res["market"]["log_loss"]
    res["blend_skill"] = (res["market"]["log_loss"] - res["blend"]["log_loss"]) \
        / res["market"]["log_loss"]
    res["_arrays"] = {"model": model_p, "market": avg_p, "best": best_p,
                      "blend": blended, "y": y_test, "df": sub}
    return res


def _score(p: np.ndarray, y: np.ndarray) -> dict:
    p = np.clip(p, 1e-9, 1); p = p / p.sum(axis=1, keepdims=True)
    onehot = np.zeros_like(p); onehot[np.arange(len(y)), y] = 1
    return {
        "log_loss": float(multiclass_log_loss(p, y)),
        "rps": float(rps(p, y)),
        "brier": float(np.mean(np.sum((p - onehot) ** 2, axis=1))),
        "accuracy": float(np.mean(p.argmax(axis=1) == y)),
        "ece_home": float(expected_calibration_error(p[:, 0], (y == 0).astype(int))),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="edge.db")
    ap.add_argument("--xi", type=float, default=0.0045)
    ap.add_argument("--train-years", type=float, default=4.0)
    ap.add_argument("--step-days", type=int, default=30)
    ap.add_argument("--start", default="2014-08-01")
    ap.add_argument("--blend", type=float, default=0.35)
    ap.add_argument("--out", default="train_result.json")
    a = ap.parse_args()

    conn = sqlite3.connect(a.db)
    r = run(conn, a.xi, a.train_years, a.step_days, a.start, a.blend)
    arrays = r.pop("_arrays")
    np.savez("preds.npz", model=arrays["model"], market=arrays["market"],
             best=arrays["best"], blend=arrays["blend"], y=arrays["y"])
    arrays["df"].to_csv("test_matches.csv", index=False)
    Path(a.out).write_text(json.dumps(r, indent=2, default=str))

    print("\n" + "=" * 62)
    print(f"WALK-FORWARD SONUÇ   ({r['n_test']} test maçı, {r['n_folds']} kat)")
    print(f"yarı ömür: {r['half_life_days']:.0f} gün")
    print("=" * 62)
    print(f"{'':12s} {'log loss':>10s} {'RPS':>8s} {'isabet':>8s} {'kalib.':>8s}")
    for k in ("coin_flip", "model", "blend", "market"):
        s = r[k]
        print(f"{k:12s} {s['log_loss']:10.5f} {s['rps']:8.4f} "
              f"{s['accuracy']*100:7.1f}% {s['ece_home']:8.4f}")
    print("=" * 62)
    print(f"model  piyasaya karşı beceri : {r['skill_vs_market']*100:+.2f}%")
    print(f"harman piyasaya karşı beceri : {r['blend_skill']*100:+.2f}%")
