"""
Matches.csv -> app/model_data/params.json  (lige özel Dixon-Coles + kalibrasyon)

Her lig için:
  - Dixon-Coles fit (son ~N gün, zaman ağırlıklı)
  - iç holdout üzerinde LOJİSTİK KALİBRASYON: 1/X/2, Ü2.5, KG-var
  - Elo'dan lig gücü (cross-lig eşleşmede terfi eden takım için)
  - 1X2 / Ü2.5 / KG-var için piyasaya karşı beceri raporu

Çalıştır:  python scripts/export_params.py --csv <Matches.csv> --days 1000
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.dixon_coles import DixonColes, build_matrix

OUT = Path(__file__).resolve().parents[1] / "app" / "model_data" / "params.json"
RES = {"H": 0, "D": 1, "A": 2}

# football-data.co.uk bölüm kodu -> (ülke, insan-okur isim, kademe)
DIVISION_MAP = {
    "E0": ("ENG", "Premier League", 1), "E1": ("ENG", "Championship", 2),
    "E2": ("ENG", "League One", 3), "E3": ("ENG", "League Two", 4),
    "SC0": ("SCO", "Scottish Premiership", 1), "SC1": ("SCO", "Scottish Championship", 2),
    "D1": ("GER", "Bundesliga", 1), "D2": ("GER", "2. Bundesliga", 2),
    "I1": ("ITA", "Serie A", 1), "I2": ("ITA", "Serie B", 2),
    "SP1": ("ESP", "La Liga", 1), "SP2": ("ESP", "La Liga 2", 2),
    "F1": ("FRA", "Ligue 1", 1), "F2": ("FRA", "Ligue 2", 2),
    "N1": ("NED", "Eredivisie", 1), "B1": ("BEL", "Pro League", 1),
    "P1": ("POR", "Primeira Liga", 1), "T1": ("TUR", "Super Lig", 1),
    "G1": ("GRE", "Super League", 1), "AUT": ("AUT", "Bundesliga (AUT)", 1),
    "SUI": ("SUI", "Super League (SUI)", 1), "DEN": ("DEN", "Superliga", 1),
    "SWE": ("SWE", "Allsvenskan", 1), "NOR": ("NOR", "Eliteserien", 1),
    "FIN": ("FIN", "Veikkausliiga", 1), "IRL": ("IRL", "Premier Division", 1),
    "POL": ("POL", "Ekstraklasa", 1), "ROM": ("ROU", "Liga I", 1),
    "RUS": ("RUS", "Premier League (RUS)", 1), "USA": ("USA", "MLS", 1),
    "MEX": ("MEX", "Liga MX", 1), "BRA": ("BRA", "Serie A (BRA)", 1),
    "ARG": ("ARG", "Primera Division (ARG)", 1), "CHN": ("CHN", "Super League (CHN)", 1),
    "JAP": ("JPN", "J1 League", 1), "EC": ("XX", "EC", 1),
}
LEAGUE_TO_CODE = {v[1]: k for k, v in DIVISION_MAP.items()}
API_CODE = {  # football-data.org competition kodu
    "Premier League": "PL", "Championship": "ELC", "Bundesliga": "BL1",
    "Serie A": "SA", "La Liga": "PD", "Ligue 1": "FL1", "Eredivisie": "DED",
    "Primeira Liga": "PPL", "Serie A (BRA)": "BSA",
}


def season_of(d: pd.Timestamp) -> str:
    y = d.year
    return f"{y}-{str(y + 1)[2:]}" if d.month >= 7 else f"{y - 1}-{str(y)[2:]}"


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_platt(p_raw: np.ndarray, y: np.ndarray) -> list[float]:
    """1B lojistik kalibrasyon: p_cal = sigmoid(a*logit(p)+b).
    Küçük örneklemde kimliğe (a=1,b=0) çekilir — aşırı uyum blow-up'ını önler.
    """
    n = len(y)
    if n < 150:
        return [1.0, 0.0]
    x = logit(p_raw)
    # kimliğe doğru L2 düzenlileştirme; örneklem büyüdükçe zayıflar
    lam = 40.0 / n
    a, b = 1.0, 0.0
    for _ in range(80):
        z = a * x + b
        q = 1.0 / (1.0 + np.exp(-z))
        g_a = np.mean((q - y) * x) + lam * (a - 1.0)
        g_b = np.mean(q - y) + lam * b
        h_a = np.mean(q * (1 - q) * x * x) + lam + 1e-6
        h_b = np.mean(q * (1 - q)) + lam + 1e-6
        a -= g_a / h_a
        b -= g_b / h_b
        if abs(g_a) + abs(g_b) < 1e-7:
            break
    # makul aralık dışına taşmayı engelle
    a = float(np.clip(a, 0.4, 2.2))
    b = float(np.clip(b, -1.2, 1.2))
    return [round(a, 4), round(b, 4)]


def apply_platt(p, ab):
    a, b = ab
    z = a * logit(np.asarray(p)) + b
    return 1.0 / (1.0 + np.exp(-z))


def log_loss(p, y):
    p = np.clip(p, 1e-9, 1)
    p = p / p.sum(axis=1, keepdims=True)
    return float(-np.log(p[np.arange(len(y)), y]).mean())


def bin_ll(p, y):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def dc_matrices(params, home, away):
    p = params
    out = []
    for h, a in zip(home, away):
        if h in p.attack and a in p.attack:
            lam = math.exp(p.attack[h] - p.defence[a] + p.home_adv)
            mu = math.exp(p.attack[a] - p.defence[h])
        else:
            lam, mu = 1.35, 1.10
        out.append(build_matrix(min(max(lam, .05), 6), min(max(mu, .05), 6), p.rho))
    return out


def m_1x2(m):
    h = np.tril(m, -1).sum(); d = np.trace(m); a = np.triu(m, 1).sum()
    s = h + d + a
    return np.array([h / s, d / s, a / s])


def m_over25(m):
    n = m.shape[0]
    o = sum(m[i, j] for i in range(n) for j in range(n) if i + j >= 3)
    return float(o)


def m_btts(m):
    n = m.shape[0]
    return float(sum(m[i, j] for i in range(1, n) for j in range(1, n)))


def fit_league(df: pd.DataFrame, name: str, days: int) -> tuple[dict, dict] | None:
    df = df.sort_values("date").reset_index(drop=True)
    if len(df) < 300:
        return None
    cutoff = df.date.max() - pd.Timedelta(days=days)
    df = df[df.date >= cutoff].reset_index(drop=True)
    if len(df) < 250:
        return None

    # holdout: son %20
    k = int(len(df) * 0.8)
    tr, ho = df.iloc[:k], df.iloc[k:]

    def fit_dc(d):
        teams = sorted(set(d.home) | set(d.away))
        da = (d.date.max() - d.date).dt.total_seconds().to_numpy() / 86400.0
        return DixonColes(xi=0.0045).fit(d.home.to_numpy(), d.away.to_numpy(),
                                         d.hg.to_numpy(float), d.ag.to_numpy(float), da, teams)

    p_tr = fit_dc(tr)
    mats = dc_matrices(p_tr, ho.home.to_numpy(), ho.away.to_numpy())
    p1x2 = np.array([m_1x2(m) for m in mats])
    pov = np.array([m_over25(m) for m in mats])
    pbt = np.array([m_btts(m) for m in mats])
    y = ho.y.to_numpy()
    y_ov = ((ho.hg + ho.ag) >= 3).to_numpy().astype(float)
    y_bt = ((ho.hg >= 1) & (ho.ag >= 1)).to_numpy().astype(float)

    calib = {
        "home": fit_platt(p1x2[:, 0], (y == 0).astype(float)),
        "draw": fit_platt(p1x2[:, 1], (y == 1).astype(float)),
        "away": fit_platt(p1x2[:, 2], (y == 2).astype(float)),
        "over25": fit_platt(pov, y_ov),
        "btts": fit_platt(pbt, y_bt),
    }

    # tam veriyle final fit
    p_full = fit_dc(df)
    gmean = float((df.hg.mean() + df.ag.mean()) / 2.0)
    try:
        elo = pd.concat([df["home_elo"], df["away_elo"]]).dropna()
        strength = float(elo.mean()) if len(elo) > 20 else 1500.0
    except Exception:
        strength = 1500.0

    league = {
        "home_adv": round(float(p_full.home_adv), 4),
        "rho": round(float(p_full.rho), 4),
        "goal_mean": round(gmean, 3),
        "strength": round(strength, 1),
        "n": int(len(df)),
        "calib": calib,
        "teams": {t: [round(float(p_full.attack[t]), 4), round(float(p_full.defence[t]), 4)]
                  for t in sorted(set(df.home) | set(df.away))},
    }

    # holdout raporu (kalibrasyon SONRASI, piyasaya karşı)
    mkt = ho[["oh", "od", "oa"]].to_numpy(float)
    valid = np.isfinite(mkt).all(axis=1)
    rep = {"league": name, "n_ho": int(valid.sum())}
    if valid.sum() > 30:
        mp = 1.0 / mkt[valid]
        mp = mp / mp.sum(axis=1, keepdims=True)
        cal = np.column_stack([
            apply_platt(p1x2[valid, 0], calib["home"]),
            apply_platt(p1x2[valid, 1], calib["draw"]),
            apply_platt(p1x2[valid, 2], calib["away"]),
        ])
        cal = cal / cal.sum(axis=1, keepdims=True)
        rep["ll_model"] = round(log_loss(cal, y[valid]), 4)
        rep["ll_market"] = round(log_loss(mp, y[valid]), 4)
        rep["skill_1x2"] = round((rep["ll_market"] - rep["ll_model"]) / rep["ll_market"] * 100, 2)
        if np.isfinite(ho.get("ov25", pd.Series(np.nan, index=ho.index)).to_numpy(float)).any():
            mo = 1.0 / ho.ov25.to_numpy(float)[valid]
            po = apply_platt(pov[valid], calib["over25"])
            rep["ll_ov_model"] = round(bin_ll(po, y_ov[valid]), 4)
            rep["ll_ov_market"] = round(bin_ll(np.clip(mo, 1e-6, 1 - 1e-6), y_ov[valid]), 4)
            rep["skill_ov25"] = round(
                (rep["ll_ov_market"] - rep["ll_ov_model"]) / rep["ll_ov_market"] * 100, 2)
    return league, rep


def main(csv: str, days: int) -> None:
    raw = pd.read_csv(csv, low_memory=False)
    raw = raw[raw.MatchDate.notna() & raw.FTHome.notna() & raw.FTAway.notna()]
    raw["date"] = pd.to_datetime(raw.MatchDate, errors="coerce")
    raw = raw[raw.date.notna()]
    raw["home"] = raw.HomeTeam.astype(str)
    raw["away"] = raw.AwayTeam.astype(str)
    raw["hg"] = raw.FTHome.astype(int)
    raw["ag"] = raw.FTAway.astype(int)
    raw["y"] = raw.FTResult.map(RES)
    raw["oh"] = pd.to_numeric(raw.get("OddHome"), errors="coerce")
    raw["od"] = pd.to_numeric(raw.get("OddDraw"), errors="coerce")
    raw["oa"] = pd.to_numeric(raw.get("OddAway"), errors="coerce")
    raw["ov25"] = pd.to_numeric(raw.get("Over25"), errors="coerce")
    raw["home_elo"] = pd.to_numeric(raw.get("HomeElo"), errors="coerce")
    raw["away_elo"] = pd.to_numeric(raw.get("AwayElo"), errors="coerce")

    out: dict = {"leagues": {}, "by_code": {}, "generated": pd.Timestamp.utcnow().isoformat()}
    reports = []
    for code, (country, name, tier) in DIVISION_MAP.items():
        sub = raw[raw.Division == code]
        if len(sub) < 300:
            continue
        r = fit_league(sub, name, days)
        if r is None:
            continue
        league, rep = r
        league["country"], league["tier"] = country, tier
        out["leagues"][name] = league
        ac = API_CODE.get(name)
        if ac:
            out["by_code"][ac] = name
        reports.append(rep)
        sk = rep.get("skill_1x2")
        so = rep.get("skill_ov25")
        print(f"  {name:26s} n={league['n']:5d}  ha={league['home_adv']:+.2f} "
              f"rho={league['rho']:+.2f}  1X2 skill={sk if sk is not None else '  -':>6}%"
              f"  Ü2.5 skill={so if so is not None else '  -':>6}%")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    kb = OUT.stat().st_size / 1024

    # toplam beceri (holdout ağırlıklı)
    def wavg(key_ll_m, key_ll_x, key_n):
        rs = [r for r in reports if key_ll_m in r]
        if not rs:
            return None
        n = sum(r[key_n] for r in rs)
        m = sum(r[key_ll_m] * r[key_n] for r in rs) / n
        x = sum(r[key_ll_x] * r[key_n] for r in rs) / n
        return round((x - m) / x * 100, 2), round(m, 4), round(x, 4)

    print("\n" + "=" * 66)
    r1 = wavg("ll_model", "ll_market", "n_ho")
    ro = wavg("ll_ov_model", "ll_ov_market", "n_ho")
    if r1:
        print(f"1X2  : model {r1[1]}  piyasa {r1[2]}  skill {r1[0]:+.2f}%")
    if ro:
        print(f"Ü2.5 : model {ro[1]}  piyasa {ro[2]}  skill {ro[0]:+.2f}%")
    print(f"{OUT}  ({kb:.0f} KB, {len(out['leagues'])} lig, kalibrasyonlu)")
    print("=" * 66)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--days", type=int, default=1000)
    a = ap.parse_args()
    main(a.csv, a.days)
