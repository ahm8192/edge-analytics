"""
Gerçek veriyle Dixon-Coles eğitimi + walk-forward doğrulama.

Bu script sadece model eğitmez, MODELİN İŞE YARAYIP YARAMADIĞINI ölçer.
Baseline'ı geçemiyorsa öyle yazar.
"""
from __future__ import annotations
import argparse
import datetime as dt
import sqlite3
import sys
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

sys.path.insert(0, ".")
from app.models.dixon_coles import tau, build_matrix, market_1x2
from app.models.metrics import multiclass_log_loss, rps
from app.models.calibration import expected_calibration_error


def load(conn, league: str) -> pd.DataFrame:
    df = pd.read_sql_query(
        """SELECT m.kickoff_utc, th.canonical_name AS home, ta.canonical_name AS away,
                  m.home_goals AS hg, m.away_goals AS ag, m.season
           FROM match m
           JOIN team th ON th.id = m.home_team_id
           JOIN team ta ON ta.id = m.away_team_id
           JOIN league l ON l.id = m.league_id
           WHERE l.name = ? AND m.status='finished'
           ORDER BY m.kickoff_utc""", conn, params=(league,))
    df["date"] = pd.to_datetime(df.kickoff_utc, format="mixed", utc=True)
    return df


def fit_dc(df: pd.DataFrame, as_of: pd.Timestamp, xi: float = 0.0045):
    """Verilen ana kadar olan maçlarla eğitir. Sızıntı yok."""
    train = df[df.date < as_of]
    if len(train) < 120:
        return None

    teams = sorted(set(train.home) | set(train.away))
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    h = train.home.map(idx).to_numpy()
    a = train.away.map(idx).to_numpy()
    hg = train.hg.to_numpy(float)
    ag = train.ag.to_numpy(float)
    days = (as_of - train.date).dt.total_seconds().to_numpy() / 86400
    w = np.exp(-xi * days)

    def nll(p):
        atk, dfc = p[:n], p[n:2 * n]
        ha, rho = p[2 * n], p[2 * n + 1]
        lam = np.clip(np.exp(atk[h] - dfc[a] + ha), 1e-6, 12)
        mu = np.clip(np.exp(atk[a] - dfc[h]), 1e-6, 12)
        ll = poisson.logpmf(hg, lam) + poisson.logpmf(ag, mu)
        t = np.ones(len(hg))
        low = (hg <= 1) & (ag <= 1)
        for i in np.where(low)[0]:
            t[i] = tau(int(hg[i]), int(ag[i]), lam[i], mu[i], rho)
        ll += np.log(np.clip(t, 1e-9, None))
        return -np.sum(w * ll)

    x0 = np.concatenate([np.zeros(n), np.zeros(n), [0.25], [-0.05]])
    res = minimize(nll, x0, method="L-BFGS-B",
                   bounds=[(-2.5, 2.5)] * (2 * n) + [(-1, 1), (-0.2, 0.2)],
                   options={"maxiter": 400})
    x = res.x
    x[:n] -= x[:n].mean()          # kimlik kısıtı
    return {"teams": idx,
            "attack": x[:n], "defence": x[n:2 * n],
            "home_adv": x[2 * n], "rho": x[2 * n + 1]}


def predict(params, home: str, away: str):
    idx = params["teams"]
    if home not in idx or away not in idx:
        return None
    i, j = idx[home], idx[away]
    lam = np.exp(params["attack"][i] - params["defence"][j] + params["home_adv"])
    mu = np.exp(params["attack"][j] - params["defence"][i])
    m = build_matrix(float(lam), float(mu), float(params["rho"]))
    p = market_1x2(m)
    return [p["HOME"], p["DRAW"], p["AWAY"]], float(lam), float(mu)


def walk_forward(df: pd.DataFrame, xi: float, step_days: int = 42,
                 initial_days: int = 540):
    start = df.date.min() + pd.Timedelta(days=initial_days)
    end = df.date.max()
    cut = start
    rows = []

    while cut < end:
        nxt = cut + pd.Timedelta(days=step_days)
        test = df[(df.date >= cut) & (df.date < nxt)]
        if len(test) == 0:
            cut = nxt
            continue
        params = fit_dc(df, cut, xi)
        if params is None:
            cut = nxt
            continue
        for _, r in test.iterrows():
            out = predict(params, r.home, r.away)
            if out is None:
                continue
            probs, lam, mu = out
            y = 0 if r.hg > r.ag else (1 if r.hg == r.ag else 2)
            rows.append({"probs": probs, "y": y, "date": r.date,
                         "lam": lam, "mu": mu,
                         "total_goals": r.hg + r.ag})
        cut = nxt
    return rows


def evaluate(rows, df: pd.DataFrame, label: str) -> dict:
    P = np.array([r["probs"] for r in rows])
    y = np.array([r["y"] for r in rows])

    # Baseline 1: düzgün dağılım
    uniform = np.full_like(P, 1 / 3)
    # Baseline 2: tarihsel taban oranlar (eğitim döneminden)
    base_rates = np.array([
        (df.hg > df.ag).mean(), (df.hg == df.ag).mean(), (df.hg < df.ag).mean()])
    prior = np.tile(base_rates, (len(P), 1))

    ll_model = multiclass_log_loss(P, y)
    ll_uniform = multiclass_log_loss(uniform, y)
    ll_prior = multiclass_log_loss(prior, y)

    # Kalibrasyon: ev sahibi kazanma olasılığı üzerinden
    ece = expected_calibration_error(P[:, 0], (y == 0).astype(float))

    return {
        "lig": label, "n": len(rows),
        "log_loss": ll_model, "rps": rps(P, y),
        "baseline_uniform": ll_uniform, "baseline_prior": ll_prior,
        "skill_vs_prior": (ll_prior - ll_model) / ll_prior,
        "ece": ece,
        "accuracy": float((P.argmax(1) == y).mean()),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="edge.db")
    ap.add_argument("--xi", type=float, default=0.0045)
    ap.add_argument("--leagues", nargs="*", default=None)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    leagues = args.leagues or [r[0] for r in conn.execute(
        "SELECT name FROM league ORDER BY name")]

    results = []
    for lg in leagues:
        df = load(conn, lg)
        if len(df) < 600:
            continue
        rows = walk_forward(df, args.xi)
        if not rows:
            continue
        results.append(evaluate(rows, df, lg))
        r = results[-1]
        print(f"{lg:16s} n={r['n']:5d}  log loss {r['log_loss']:.4f}  "
              f"(taban {r['baseline_prior']:.4f})  kazanım %{r['skill_vs_prior']*100:5.2f}  "
              f"ECE {r['ece']:.4f}  isabet %{r['accuracy']*100:.1f}")

    print()
    agg_n = sum(r["n"] for r in results)
    agg_ll = sum(r["log_loss"] * r["n"] for r in results) / agg_n
    agg_base = sum(r["baseline_prior"] * r["n"] for r in results) / agg_n
    print(f"TOPLAM  {agg_n} maç | model {agg_ll:.4f} | taban {agg_base:.4f} | "
          f"kazanım %{(agg_base-agg_ll)/agg_base*100:.2f}")
