#!/usr/bin/env python3
"""
Gerçek veri üzerinde walk-forward doğrulama.

Sorulan tek soru: model piyasayı yeniyor mu?
Cevap "hayır" ise bu bir başarısızlık değil, DOĞRU bilgidir — ve
karmaşıklık eklemeden önce bilinmesi gerekir.
"""
from __future__ import annotations
import sqlite3, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

sys.path.insert(0, ".")
from app.models.dixon_coles import DixonColes, build_matrix, market_1x2
from app.models.metrics import multiclass_log_loss, rps
from app.models.calibration import Calibrator, expected_calibration_error
from app.market.devig import devig_shin, devig_multiplicative

OUTCOME = {"H": 0, "D": 1, "A": 2}


def load_league(conn, league_code: str) -> pd.DataFrame:
    q = """
    SELECT m.id, m.kickoff_utc, m.season,
           th.canonical_name AS home, ta.canonical_name AS away,
           m.home_goals AS hg, m.away_goals AS ag
    FROM match m
    JOIN league l ON l.id = m.league_id
    JOIN team th ON th.id = m.home_team_id
    JOIN team ta ON ta.id = m.away_team_id
    WHERE l.name = ? AND m.home_goals IS NOT NULL
    ORDER BY m.kickoff_utc
    """
    df = pd.read_sql_query(q, conn, params=(league_code,))
    df["date"] = pd.to_datetime(df.kickoff_utc)
    df["y"] = np.where(df.hg > df.ag, 0, np.where(df.hg == df.ag, 1, 2))
    return df


def load_odds(conn, match_ids: list[int]) -> pd.DataFrame:
    """Her maç için en iyi referans oranı. Pinnacle varsa o, yoksa ortalama."""
    ph = ",".join("?" * len(match_ids))
    q = f"""
    SELECT o.match_id, b.code AS book, b.is_sharp, o.selection, o.price, o.is_closing
    FROM odds_snapshot o JOIN bookmaker b ON b.id = o.bookmaker_id
    WHERE o.market='1X2' AND o.match_id IN ({ph})
    """
    d = pd.read_sql_query(q, conn, params=match_ids)
    if d.empty:
        return d
    # Öncelik: kapanış > keskin > ortalama
    d["prio"] = (d.is_closing * 4 + d.is_sharp * 2 +
                 (d.book == "market_average").astype(int))
    d = d.sort_values("prio", ascending=False)
    piv = d.drop_duplicates(["match_id", "selection"]).pivot(
        index="match_id", columns="selection", values="price")
    return piv.dropna(subset=["HOME", "DRAW", "AWAY"])


def market_probs(odds: pd.DataFrame, method="shin") -> np.ndarray:
    fn = devig_shin if method == "shin" else devig_multiplicative
    out = np.empty((len(odds), 3))
    for i, (_, r) in enumerate(odds.iterrows()):
        out[i] = fn([r.HOME, r.DRAW, r.AWAY])
    return out


def run(db="edge.db", league="tr.1", xi=0.0045,
        train_seasons=4, step_days=30, min_train=400):
    conn = sqlite3.connect(db)
    df = load_league(conn, league)
    print(f"\n{'='*66}")
    print(f"LİG: {league}   maç: {len(df)}   "
          f"{df.date.min().date()} → {df.date.max().date()}")

    odds = load_odds(conn, df.id.tolist())
    df = df[df.id.isin(odds.index)].reset_index(drop=True)
    odds = odds.loc[df.id].reset_index(drop=True)
    print(f"Oranı olan maç: {len(df)}")
    if len(df) < min_train + 200:
        print("Yetersiz veri."); return

    start = df.date.min() + pd.Timedelta(days=365 * train_seasons)
    cut = start
    rows = []

    while cut < df.date.max():
        test_end = cut + pd.Timedelta(days=step_days)
        tr = df[df.date <= cut]
        te = df[(df.date > cut) & (df.date <= test_end)]
        cut = test_end
        if len(tr) < min_train or len(te) < 5:
            continue

        teams = sorted(set(tr.home) | set(tr.away))
        if not set(te.home).issubset(teams) or not set(te.away).issubset(teams):
            te = te[te.home.isin(teams) & te.away.isin(teams)]
            if len(te) < 5:
                continue

        days_ago = (tr.date.max() - tr.date).dt.days.to_numpy()
        dc = DixonColes(xi=xi)
        try:
            dc.fit(tr.home.to_numpy(), tr.away.to_numpy(),
                   tr.hg.to_numpy(), tr.ag.to_numpy(), days_ago, teams)
        except Exception as e:
            print("  fit hatası:", e); continue

        P = np.array([list(market_1x2(dc.score_matrix(h, a)).values())
                      for h, a in zip(te.home, te.away)])
        M = market_probs(odds.loc[te.index])
        y = te.y.to_numpy()

        rows.append({
            "tarih": cut.date(), "n": len(te),
            "model_ll": multiclass_log_loss(P, y),
            "piyasa_ll": multiclass_log_loss(M, y),
            "model_rps": rps(P, y), "piyasa_rps": rps(M, y),
            "P": P, "M": M, "y": y,
        })

    if not rows:
        print("Kat üretilemedi."); return

    res = pd.DataFrame(rows)
    allP = np.vstack(res.P.tolist()); allM = np.vstack(res.M.tolist())
    ally = np.concatenate(res.y.tolist())

    m_ll = multiclass_log_loss(allP, ally)
    k_ll = multiclass_log_loss(allM, ally)
    print(f"\nKat sayısı: {len(res)}   test maçı: {len(ally)}")
    print(f"\n{'':<22}{'log loss':>10}{'RPS':>9}")
    print(f"{'Dixon-Coles':<22}{m_ll:>10.4f}{rps(allP, ally):>9.4f}")
    print(f"{'Piyasa (Shin)':<22}{k_ll:>10.4f}{rps(allM, ally):>9.4f}")
    skill = (k_ll - m_ll) / k_ll
    print(f"\nSkill (piyasaya karşı): {skill:+.2%}")
    print("→", "MODEL PİYASAYI YENİYOR" if skill > 0 else
          "Model piyasadan kötü — beklenen sonuç bu.")

    won = (res.model_ll < res.piyasa_ll).mean()
    print(f"Katların %{won*100:.0f}'inde model daha iyi "
          f"(şans %50 olurdu)")

    # Harmanlama: model + piyasa
    print(f"\n{'Harman (model ağırlığı)':<24}{'log loss':>10}{'kazanım':>10}")
    for w in (0.10, 0.20, 0.30, 0.40, 0.50):
        lp = w * np.log(np.clip(allP, 1e-9, 1)) + (1-w) * np.log(np.clip(allM, 1e-9, 1))
        B = np.exp(lp); B /= B.sum(axis=1, keepdims=True)
        b_ll = multiclass_log_loss(B, ally)
        print(f"  {w:<22.0%}{b_ll:>10.4f}{(k_ll-b_ll)/k_ll:>+10.2%}")

    print(f"\nKalibrasyon hatası (ECE):")
    for name, Q in (("model", allP), ("piyasa", allM)):
        e = np.mean([expected_calibration_error(Q[:, k], (ally == k).astype(int))
                     for k in range(3)])
        print(f"  {name:<20}{e:.4f}")
    return res


if __name__ == "__main__":
    lg = sys.argv[1] if len(sys.argv) > 1 else "tr.1"
    run(league=lg)
