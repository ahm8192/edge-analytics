"""
Ensemble modelin kapanış oranını geçip geçmediğini ölçer.

Modeller:
  market   - devig(OddHome/Draw/Away)            (kıyas ölçütü)
  elo      - dataset Elo farkından multinomial lojistik
  gbdt     - LightGBM, TÜM özellikler (piyasa dahil)  <- "piyasa nerede yanılıyor"
  gbdt_raw - LightGBM, piyasa ÖZELLİĞİ YOK           <- saf kendi sinyalimiz
  blend    - gbdt + market log-havuz (ağırlık eğitimde optimize)

Walk-forward: her sezon başında (Ağustos) yeniden eğit, o sezonu test et.
Bahis simülasyonu: en iyi orana (Max*) göre %3+ kenar varsa 1 birim.

Çalıştır:  python scripts/ensemble_validate.py --csv <Matches.csv> --leagues E0 D1 I1 SP1 F1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    from sklearn.ensemble import HistGradientBoostingClassifier
    HAS_LGB = False

RES = {"H": 0, "D": 1, "A": 2}


def devig_mult(o: np.ndarray) -> np.ndarray:
    p = 1.0 / o
    return p / p.sum(axis=1, keepdims=True)


def log_loss(p, y):
    p = np.clip(p, 1e-9, 1)
    p = p / p.sum(axis=1, keepdims=True)
    return float(-np.log(p[np.arange(len(y)), y]).mean())


def rps(p, y):
    oh = np.zeros_like(p)
    oh[np.arange(len(y)), y] = 1
    cp = np.cumsum(p, axis=1)
    co = np.cumsum(oh, axis=1)
    return float(np.mean(np.sum((cp - co) ** 2, axis=1)) / (p.shape[1] - 1))


def ece(p_home, y_home, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    e = 0.0
    for i in range(bins):
        m = (p_home >= edges[i]) & (p_home < edges[i + 1])
        if m.sum() == 0:
            continue
        e += m.mean() * abs(p_home[m].mean() - y_home[m].mean())
    return float(e)


def season_of(d: pd.Timestamp) -> int:
    return d.year if d.month >= 7 else d.year - 1


def rolling_form(df: pd.DataFrame, n: int = 8) -> pd.DataFrame:
    """Her takım için son n maçın gol at/ye ortalaması — nedensel (sızıntısız)."""
    gf: dict[str, list] = {}
    rows = []
    for r in df.itertuples(index=False):
        h, a = r.HomeTeam, r.AwayTeam
        hh = gf.get(h, [])
        aa = gf.get(a, [])
        def avg(lst, idx):
            v = [x[idx] for x in lst[-n:]]
            return float(np.mean(v)) if v else np.nan
        rows.append((avg(hh, 0), avg(hh, 1), avg(aa, 0), avg(aa, 1)))
        gf.setdefault(h, []).append((r.FTHome, r.FTAway))
        gf.setdefault(a, []).append((r.FTAway, r.FTHome))
    return pd.DataFrame(rows, columns=["h_gf", "h_ga", "a_gf", "a_ga"], index=df.index)


def build(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df.MatchDate, errors="coerce")
    df = df[df.date.notna() & df.FTResult.isin(list(RES))
            & df.OddHome.notna() & df.OddDraw.notna() & df.OddAway.notna()
            & df.HomeElo.notna() & df.AwayElo.notna()].sort_values("date").reset_index(drop=True)

    mkt = devig_mult(df[["OddHome", "OddDraw", "OddAway"]].to_numpy(float))
    df["mkt_h"], df["mkt_d"], df["mkt_a"] = mkt[:, 0], mkt[:, 1], mkt[:, 2]
    df["overround"] = (1 / df.OddHome + 1 / df.OddDraw + 1 / df.OddAway) - 1.0
    df["elo_diff"] = df.HomeElo - df.AwayElo
    df["form3"] = df.Form3Home.fillna(0) - df.Form3Away.fillna(0)
    df["form5"] = df.Form5Home.fillna(0) - df.Form5Away.fillna(0)

    roll = rolling_form(df)
    df = pd.concat([df, roll], axis=1)
    df["att_diff"] = df.h_gf - df.a_gf
    df["def_diff"] = df.a_ga - df.h_ga

    df["season"] = df.date.map(season_of)
    df["y"] = df.FTResult.map(RES).astype(int)
    return df


FEATS_RAW = ["elo_diff", "form3", "form5", "h_gf", "h_ga", "a_gf", "a_ga",
             "att_diff", "def_diff"]
FEATS_MKT = FEATS_RAW + ["mkt_h", "mkt_d", "mkt_a", "overround"]


def fit_gbdt(X, y, Xv, yv):
    if HAS_LGB:
        tr = lgb.Dataset(X, label=y)
        va = lgb.Dataset(Xv, label=yv, reference=tr)
        params = dict(objective="multiclass", num_class=3, learning_rate=0.03,
                      num_leaves=31, feature_fraction=0.8, bagging_fraction=0.8,
                      bagging_freq=1, lambda_l2=5.0, min_data_in_leaf=80, verbosity=-1)
        m = lgb.train(params, tr, num_boost_round=1200, valid_sets=[va],
                      callbacks=[lgb.early_stopping(80, verbose=False)])
        return lambda Z: m.predict(Z, num_iteration=m.best_iteration).reshape(len(Z), 3)
    m = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.04,
                                       max_leaf_nodes=15, min_samples_leaf=80,
                                       l2_regularization=5.0)
    m.fit(X, y)
    return lambda Z: m.predict_proba(Z)


def fit_elo(df_tr):
    lr = LogisticRegression(max_iter=1000, C=1.0)
    lr.fit(df_tr[["elo_diff", "form5"]], df_tr.y)
    return lambda d: lr.predict_proba(d[["elo_diff", "form5"]])


def blend_weight(p_model, p_mkt, y):
    best_w, best_l = 0.0, 1e9
    for w in np.linspace(0, 1, 21):
        pool = np.exp(w * np.log(np.clip(p_model, 1e-9, 1)) +
                      (1 - w) * np.log(np.clip(p_mkt, 1e-9, 1)))
        pool /= pool.sum(axis=1, keepdims=True)
        ll = log_loss(pool, y)
        if ll < best_l:
            best_l, best_w = ll, w
    return best_w


def pool(p_model, p_mkt, w):
    x = np.exp(w * np.log(np.clip(p_model, 1e-9, 1)) +
               (1 - w) * np.log(np.clip(p_mkt, 1e-9, 1)))
    return x / x.sum(axis=1, keepdims=True)


def main(csv, leagues, start_season, min_train):
    raw = pd.read_csv(csv, low_memory=False)
    raw = raw[raw.Division.isin(leagues)]
    df = build(raw)
    print(f"{len(df)} maç | {df.season.min()}–{df.season.max()} | ligler {sorted(leagues)}")

    seasons = sorted(s for s in df.season.unique() if s >= start_season)
    acc = {k: [] for k in ("market", "elo", "gbdt", "gbdt_raw", "blend")}
    ally, allidx = [], []
    bets = {"blend": [], "gbdt": []}

    for s in seasons:
        tr = df[df.season < s]
        te = df[df.season == s]
        if len(tr) < min_train or len(te) < 50:
            continue
        # iç doğrulama: eğitim setinin son sezonu
        vs = tr.season.max()
        tr_fit, tr_val = tr[tr.season < vs], tr[tr.season == vs]
        if len(tr_val) < 50:
            tr_fit, tr_val = tr, tr.tail(400)

        y_te = te.y.to_numpy()
        p_mkt = te[["mkt_h", "mkt_d", "mkt_a"]].to_numpy()

        p_elo = fit_elo(tr)(te)
        g_all = fit_gbdt(tr_fit[FEATS_MKT], tr_fit.y.to_numpy(),
                         tr_val[FEATS_MKT], tr_val.y.to_numpy())
        p_gbdt = g_all(te[FEATS_MKT])
        g_raw = fit_gbdt(tr_fit[FEATS_RAW], tr_fit.y.to_numpy(),
                         tr_val[FEATS_RAW], tr_val.y.to_numpy())
        p_raw = g_raw(te[FEATS_RAW])

        w = blend_weight(g_all(tr_val[FEATS_MKT]),
                         tr_val[["mkt_h", "mkt_d", "mkt_a"]].to_numpy(), tr_val.y.to_numpy())
        p_bl = pool(p_gbdt, p_mkt, w)

        for k, p in (("market", p_mkt), ("elo", p_elo), ("gbdt", p_gbdt),
                     ("gbdt_raw", p_raw), ("blend", p_bl)):
            acc[k].append(p)
        ally.append(y_te)
        allidx.append(te.index.to_numpy())

        # bahis simülasyonu — en iyi oran (Max*), %3 kenar eşiği
        mx = te[["MaxHome", "MaxDraw", "MaxAway"]].to_numpy(float)
        av = te[["OddHome", "OddDraw", "OddAway"]].to_numpy(float)
        for name, p in (("blend", p_bl), ("gbdt", p_gbdt)):
            for i in range(len(te)):
                for k in range(3):
                    price = mx[i, k]
                    if not np.isfinite(price) or price < 1.1:
                        price = av[i, k]
                    if not np.isfinite(price):
                        continue
                    edge = p[i, k] * price - 1.0
                    if edge > 0.03:
                        won = (y_te[i] == k)
                        pnl = (price - 1.0) if won else -1.0
                        clv = price / av[i, k] - 1.0 if np.isfinite(av[i, k]) else 0.0
                        bets[name].append((pnl, clv, edge))
        print(f"  sezon {s}: test {len(te)}  blend w={w:.2f}")

    Y = np.concatenate(ally)
    print("\n" + "=" * 74)
    print(f"{'model':10s} {'log_loss':>9s} {'RPS':>7s} {'ECE':>7s} {'acc':>7s} {'skill_vs_mkt':>13s}")
    print("-" * 74)
    mkt_ll = log_loss(np.vstack(acc["market"]), Y)
    for k in ("market", "elo", "gbdt_raw", "gbdt", "blend"):
        P = np.vstack(acc[k])
        ll = log_loss(P, Y)
        sk = (mkt_ll - ll) / mkt_ll * 100
        yh = (Y == 0).astype(float)
        print(f"{k:10s} {ll:9.5f} {rps(P, Y):7.4f} {ece(P[:, 0], yh):7.4f} "
              f"{np.mean(P.argmax(1) == Y) * 100:6.1f}% {sk:+12.2f}%")
    print("=" * 74)
    for name, b in bets.items():
        if not b:
            print(f"{name:8s} bahis yok")
            continue
        arr = np.array(b)
        roi = arr[:, 0].mean()
        print(f"{name:8s} n={len(b):5d}  ROI={roi*100:+6.2f}%  ortCLV={arr[:,1].mean()*100:+5.2f}%  "
              f"ortKenar={arr[:,2].mean()*100:5.2f}%  toplam={arr[:,0].sum():+7.1f}u")
    print("=" * 74)
    print("Not: pozitif skill + pozitif ROI + pozitif CLV = model gerçekten işe yarıyor.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--leagues", nargs="+", default=["E0", "D1", "I1", "SP1", "F1"])
    ap.add_argument("--start-season", type=int, default=2013)
    ap.add_argument("--min-train", type=int, default=3000)
    a = ap.parse_args()
    main(a.csv, a.leagues, a.start_season, a.min_train)
