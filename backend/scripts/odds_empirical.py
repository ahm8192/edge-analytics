"""100k+ tarihsel maçtan 'oran profili -> gerçek sonuç' çıkarımı.

Girdi: xgabora/Club-Football-Match-Data Matches.csv (OddHome/Draw/Away + FTResult).
Çıktı: backend/app/model_data/odds_empirical.json
  - bins:  devig(imp_home) kovası -> gerçekleşen {H,D,A} oranı + n
  - logit: standardize + multinomial lojistik (oran özellikleri -> sonuç)
  - metrics: test set logloss/brier (piyasa-devig baseline'a karşı)

Kullanım:
  scratchpad/ev/Scripts/python.exe backend/scripts/odds_empirical.py <Matches.csv>
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, brier_score_loss

OUT = Path(__file__).resolve().parents[1] / "app" / "model_data" / "odds_empirical.json"
SPLIT = pd.Timestamp("2021-01-01")
FEATURES = ["imp_h", "imp_d", "imp_a", "margin", "spread", "fav_imp",
            "home_fav", "ou_over", "elo_diff"]


def _devig3(oh, od, oa):
    ih, id_, ia = 1.0 / oh, 1.0 / od, 1.0 / oa
    s = ih + id_ + ia
    return ih / s, id_ / s, ia / s, s - 1.0


def main(csv_path: str) -> None:
    df = pd.read_csv(csv_path, low_memory=False)
    df["MatchDate"] = pd.to_datetime(df["MatchDate"], errors="coerce")
    need = ["OddHome", "OddDraw", "OddAway", "FTResult", "MatchDate"]
    df = df.dropna(subset=need)
    for c in ("OddHome", "OddDraw", "OddAway"):
        df = df[df[c] > 1.0]
    df = df[df["FTResult"].isin(["H", "D", "A"])].copy()
    print(f"kullanılan maç: {len(df):,}")

    ih, idr, ia, margin = _devig3(df["OddHome"].values, df["OddDraw"].values, df["OddAway"].values)
    df["imp_h"], df["imp_d"], df["imp_a"], df["margin"] = ih, idr, ia, margin
    df["spread"] = df["imp_h"] - df["imp_a"]
    df["fav_imp"] = np.maximum(df["imp_h"], df["imp_a"])
    df["home_fav"] = (df["imp_h"] >= df["imp_a"]).astype(float)

    if {"Over25", "Under25"}.issubset(df.columns):
        oo = 1.0 / df["Over25"].where(df["Over25"] > 1.0)
        ou = 1.0 / df["Under25"].where(df["Under25"] > 1.0)
        df["ou_over"] = (oo / (oo + ou)).fillna(0.5)
    else:
        df["ou_over"] = 0.5

    if {"HomeElo", "AwayElo"}.issubset(df.columns):
        df["elo_diff"] = ((df["HomeElo"] - df["AwayElo"]) / 400.0).clip(-1.5, 1.5).fillna(0.0)
    else:
        df["elo_diff"] = 0.0

    y = df["FTResult"].map({"H": 0, "D": 1, "A": 2}).values
    tr = df["MatchDate"] < SPLIT
    te = ~tr
    print(f"train {tr.sum():,}  test {te.sum():,}")

    # ---- 1) piyasa-devig baseline ----
    P_mkt = df[["imp_h", "imp_d", "imp_a"]].values
    ll_mkt = log_loss(y[te], P_mkt[te], labels=[0, 1, 2])

    # ---- 2) binli tablo (imp_h kovası -> gerçekleşen oran) ----
    STEP = 0.025
    def _bin(v): return round(round(v / STEP) * STEP, 3)
    btab: dict[float, list[float]] = {}
    for hb, yy in zip(df.loc[tr, "imp_h"].map(_bin).values, y[tr]):
        c = btab.setdefault(hb, [1.0, 1.0, 1.0])  # Laplace
        c[yy] += 1.0
    bins = {f"{k:.3f}": {"h": v[0] / sum(v), "d": v[1] / sum(v), "a": v[2] / sum(v),
                         "n": int(sum(v) - 3)} for k, v in sorted(btab.items())}
    def _bin_pred(hv):
        b = bins.get(f"{_bin(hv):.3f}")
        return [b["h"], b["d"], b["a"]] if b else [0.46, 0.27, 0.27]
    P_bin = np.array([_bin_pred(v) for v in df["imp_h"].values])
    ll_bin = log_loss(y[te], P_bin[te], labels=[0, 1, 2])

    # ---- 3) multinomial lojistik ----
    X = df[FEATURES].values.astype(float)
    mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
    Xs = (X - mu) / sd
    clf = LogisticRegression(C=1.0, max_iter=3000)
    clf.fit(Xs[tr], y[tr])
    P_log = clf.predict_proba(Xs)
    ll_log = log_loss(y[te], P_log[te], labels=[0, 1, 2])

    # ---- 4) lojistik + piyasa harmanı ----
    P_bl = 0.5 * P_log + 0.5 * P_mkt
    ll_bl = log_loss(y[te], P_bl[te], labels=[0, 1, 2])

    def _ece(P, col):
        p = P[te, col]; yy = (y[te] == col).astype(float)
        e = 0.0
        for lo in np.arange(0, 1, 0.05):
            m = (p >= lo) & (p < lo + 0.05)
            if m.sum() > 30:
                e += m.mean() * abs(p[m].mean() - yy[m].mean())
        return e

    print("\n=== test seti logloss (düşük = iyi) ===")
    print(f"  piyasa-devig : {ll_mkt:.4f}")
    print(f"  binli tablo  : {ll_bin:.4f}")
    print(f"  lojistik     : {ll_log:.4f}")
    print(f"  loj+piyasa   : {ll_bl:.4f}")
    print(f"  ECE(home) piyasa={_ece(P_mkt,0):.4f}  lojistik={_ece(P_log,0):.4f}")
    print(f"  Brier(home)  piyasa={brier_score_loss((y[te]==0), P_mkt[te,0]):.4f} "
          f"lojistik={brier_score_loss((y[te]==0), P_log[te,0]):.4f}")

    out = {
        "generated": datetime.utcnow().isoformat() + "Z",
        "n_train": int(tr.sum()), "n_test": int(te.sum()),
        "split": SPLIT.date().isoformat(),
        "bin_step": STEP,
        "metrics": {"logloss_market": ll_mkt, "logloss_bin": ll_bin,
                    "logloss_logit": ll_log, "logloss_blend": ll_bl},
        "bins": bins,
        "logit": {
            "classes": ["H", "D", "A"],
            "features": FEATURES,
            "mean": mu.tolist(), "std": sd.tolist(),
            "coef": clf.coef_.tolist(), "intercept": clf.intercept_.tolist(),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nyazıldı -> {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else str(Path(__file__).resolve().parents[1] / "scratchpad" / "data" / "Matches.csv"))
