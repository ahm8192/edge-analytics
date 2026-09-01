"""
Drawdown simülasyonu (madde 91, 92).
Amaç: kullanıcıya "%55 isabetle bile 15 maç üst üste kaybedebilirsin" gerçeğini
sayıyla göstermek. Beklenti yönetimi, modelden daha çok bankroll kurtarır.
"""
from __future__ import annotations
import numpy as np


def simulate(n_bets: int, win_prob: float, avg_price: float,
             kelly_fraction: float, bankroll: float = 1000.0,
             n_sims: int = 10_000, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    b = avg_price - 1.0
    f = kelly_fraction

    wins = rng.random((n_sims, n_bets)) < win_prob
    equity = np.empty((n_sims, n_bets + 1))
    equity[:, 0] = bankroll

    for t in range(n_bets):
        stake = equity[:, t] * f
        equity[:, t + 1] = equity[:, t] + np.where(wins[:, t], stake * b, -stake)

    running_max = np.maximum.accumulate(equity, axis=1)
    dd = (running_max - equity) / running_max
    max_dd = dd.max(axis=1)
    final = equity[:, -1]

    # En uzun kayıp serisi
    streaks = np.zeros(n_sims, dtype=int)
    cur = np.zeros(n_sims, dtype=int)
    for t in range(n_bets):
        cur = np.where(wins[:, t], 0, cur + 1)
        streaks = np.maximum(streaks, cur)

    return {
        "median_final": float(np.median(final)),
        "p05_final": float(np.percentile(final, 5)),
        "p95_final": float(np.percentile(final, 95)),
        "prob_loss": float((final < bankroll).mean()),
        "prob_ruin_50pct": float((max_dd > 0.5).mean()),
        "median_max_drawdown": float(np.median(max_dd)),
        "p95_max_drawdown": float(np.percentile(max_dd, 95)),
        "median_longest_losing_streak": int(np.median(streaks)),
        "p95_longest_losing_streak": int(np.percentile(streaks, 95)),
        "equity_percentiles": {
            "p10": equity[:, ::max(1, n_bets // 50)].tolist()[:0] or
                   np.percentile(equity, 10, axis=0)[::max(1, n_bets // 50)].tolist(),
            "p50": np.percentile(equity, 50, axis=0)[::max(1, n_bets // 50)].tolist(),
            "p90": np.percentile(equity, 90, axis=0)[::max(1, n_bets // 50)].tolist(),
        },
    }
