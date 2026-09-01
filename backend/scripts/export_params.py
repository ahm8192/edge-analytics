"""
edge.db'den her lig için Dixon-Coles parametrelerini çıkarır -> app/model_data/params.json

Bu dosya Docker imajına gömülür; canlı sunucu her maç için buradan
gerçek (takıma özel) gol beklentisi üretir. Ağ/DB gerekmez, milisaniyede biter.

Çalıştır:  python scripts/export_params.py --db <edge.db> --days 900
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from app.models.dixon_coles import DixonColes

OUT = Path(__file__).resolve().parents[1] / "app" / "model_data" / "params.json"

# football-data.co.uk lig adı -> football-data.org competition kodu
LEAGUE_TO_CODE = {
    "Premier League": "PL", "Championship": "ELC",
    "Bundesliga": "BL1", "2. Bundesliga": "BL2",
    "Serie A": "SA", "Serie B": "SB",
    "La Liga": "PD", "La Liga 2": "SD",
    "Ligue 1": "FL1", "Ligue 2": "FL2",
    "Eredivisie": "DED", "Primeira Liga": "PPL",
    "Pro League": "BSA_BE", "Super Lig": "TR1",
    "Serie A (BRA)": "BSA", "Super League": "GR1",
    "Scottish Premiership": "SC0", "Primera Division (ARG)": "ARG",
}


def fit_league(conn, league: str, days: int) -> dict | None:
    df = pd.read_sql_query(
        """SELECT m.kickoff_utc, th.canonical_name AS home, ta.canonical_name AS away,
                  m.home_goals AS hg, m.away_goals AS ag
           FROM match m
           JOIN team th ON th.id = m.home_team_id
           JOIN team ta ON ta.id = m.away_team_id
           JOIN league l ON l.id = m.league_id
           WHERE l.name = ? AND m.status = 'finished'
           ORDER BY m.kickoff_utc""",
        conn, params=(league,),
    )
    if len(df) < 200:
        return None
    df["date"] = pd.to_datetime(df.kickoff_utc, format="ISO8601", utc=True)
    cutoff = df.date.max() - pd.Timedelta(days=days)
    df = df[df.date >= cutoff].reset_index(drop=True)
    if len(df) < 150:
        return None

    teams = sorted(set(df.home) | set(df.away))
    days_ago = (df.date.max() - df.date).dt.total_seconds().to_numpy() / 86400.0

    model = DixonColes(xi=0.0045)
    p = model.fit(df.home.to_numpy(), df.away.to_numpy(),
                  df.hg.to_numpy(float), df.ag.to_numpy(float), days_ago, teams)

    # gol ortalamaları — modelde olmayan takım için taban
    gmean = float((df.hg.mean() + df.ag.mean()) / 2.0)
    return {
        "home_adv": round(float(p.home_adv), 4),
        "rho": round(float(p.rho), 4),
        "goal_mean": round(gmean, 3),
        "n": int(len(df)),
        "teams": {
            t: [round(float(p.attack[t]), 4), round(float(p.defence[t]), 4)]
            for t in teams
        },
    }


def main(db: str, days: int) -> None:
    conn = sqlite3.connect(db)
    leagues = [r[0] for r in conn.execute("SELECT name FROM league ORDER BY name")]
    out: dict = {"leagues": {}, "by_code": {}}
    for lg in leagues:
        try:
            res = fit_league(conn, lg, days)
        except Exception as e:  # noqa: BLE001
            print(f"  {lg}: HATA {e}")
            continue
        if res is None:
            continue
        out["leagues"][lg] = res
        code = LEAGUE_TO_CODE.get(lg)
        if code:
            out["by_code"][code] = lg
        print(f"  {lg:26s} n={res['n']:5d}  {len(res['teams'])} takım  "
              f"ha={res['home_adv']:+.3f} rho={res['rho']:+.3f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"\n{OUT}  ({kb:.0f} KB, {len(out['leagues'])} lig)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="edge.db")
    ap.add_argument("--days", type=int, default=900)
    a = ap.parse_args()
    main(a.db, a.days)
