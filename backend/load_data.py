#!/usr/bin/env python3
"""
football-data.co.uk turevi tek CSV (xgabora/Club-Football-Match-Data-2000-2025,
data/Matches.csv) -> SQLite semasi.

Kullanim:
    python load_data.py <Matches.csv yolu> [edge.db]

Cikti: match + odds_snapshot + match_stats dolu bir SQLite dosyasi.
Model egitimi (scripts/train.py) bu dosyayi okur.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sqlite3
import sys

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("load")

# football-data.co.uk bolum kodu -> (ulke, insan-okur isim, kademe)
DIVISION_MAP: dict[str, tuple[str, str, int]] = {
    "E0": ("ENG", "Premier League", 1),
    "E1": ("ENG", "Championship", 2),
    "E2": ("ENG", "League One", 3),
    "E3": ("ENG", "League Two", 4),
    "SC0": ("SCO", "Scottish Premiership", 1),
    "SC1": ("SCO", "Scottish Championship", 2),
    "SC2": ("SCO", "Scottish League One", 3),
    "SC3": ("SCO", "Scottish League Two", 4),
    "D1": ("GER", "Bundesliga", 1),
    "D2": ("GER", "2. Bundesliga", 2),
    "I1": ("ITA", "Serie A", 1),
    "I2": ("ITA", "Serie B", 2),
    "SP1": ("ESP", "La Liga", 1),
    "SP2": ("ESP", "La Liga 2", 2),
    "F1": ("FRA", "Ligue 1", 1),
    "F2": ("FRA", "Ligue 2", 2),
    "N1": ("NED", "Eredivisie", 1),
    "B1": ("BEL", "Pro League", 1),
    "P1": ("POR", "Primeira Liga", 1),
    "T1": ("TUR", "Super Lig", 1),
    "G1": ("GRE", "Super League", 1),
    "AUT": ("AUT", "Bundesliga (AUT)", 1),
    "SUI": ("SUI", "Super League (SUI)", 1),
    "DEN": ("DEN", "Superliga", 1),
    "SWE": ("SWE", "Allsvenskan", 1),
    "NOR": ("NOR", "Eliteserien", 1),
    "FIN": ("FIN", "Veikkausliiga", 1),
    "IRL": ("IRL", "Premier Division", 1),
    "POL": ("POL", "Ekstraklasa", 1),
    "ROM": ("ROU", "Liga I", 1),
    "RUS": ("RUS", "Premier League (RUS)", 1),
    "USA": ("USA", "MLS", 1),
    "MEX": ("MEX", "Liga MX", 1),
    "BRA": ("BRA", "Serie A (BRA)", 1),
    "ARG": ("ARG", "Primera Division (ARG)", 1),
    "CHN": ("CHN", "Super League (CHN)", 1),
    "JAP": ("JPN", "J1 League", 1),
    "EC": ("XX", "EC", 1),
}


def _season_of(date: pd.Timestamp) -> str:
    y = date.year
    return f"{y}-{str(y + 1)[2:]}" if date.month >= 7 else f"{y - 1}-{str(y)[2:]}"


def _time_of(value) -> str:
    s = str(value or "").strip()
    if not s or s.lower() in ("nan", "none"):
        return "00:00:00"
    parts = s.split(":")
    if len(parts) == 2:
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:00"
    if len(parts) >= 3:
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{parts[2][:2].zfill(2)}"
    return "00:00:00"


def _i(v):
    return None if v is None or pd.isna(v) else int(v)


def _f(v):
    return None if v is None or pd.isna(v) else float(v)


def init_db(path: str) -> sqlite3.Connection:
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    for f in ("app/db/schema.sql", "app/db/schema_billing.sql"):
        conn.executescript(open(os.path.join(here, f), encoding="utf-8").read())
    conn.executescript("""
        CREATE TABLE match_stats (
            match_id INTEGER PRIMARY KEY REFERENCES match(id),
            home_shots INTEGER, away_shots INTEGER,
            home_shots_target INTEGER, away_shots_target INTEGER,
            home_corners INTEGER, away_corners INTEGER,
            home_yellow INTEGER, away_yellow INTEGER,
            home_red INTEGER, away_red INTEGER,
            observed_at TEXT NOT NULL);
        CREATE TABLE match_model_output (
            match_id INTEGER PRIMARY KEY REFERENCES match(id),
            lambda_home REAL, lambda_away REAL, rho REAL,
            model_confidence REAL, model_version TEXT);
        CREATE INDEX ix_match_league_time ON match(league_id, kickoff_utc);
    """)
    conn.execute(
        "INSERT INTO source(code,kind,trust_weight) VALUES('football_data_csv','stats',0.9)")
    conn.commit()
    return conn


def main(csv_path: str, db_path: str = "edge.db") -> None:
    conn = init_db(db_path)
    log.info("CSV okunuyor: %s", csv_path)
    df = pd.read_csv(csv_path, low_memory=False)
    df["MatchDate"] = pd.to_datetime(df["MatchDate"], errors="coerce")
    df = df[df["MatchDate"].notna() & df["FTHome"].notna() & df["FTAway"].notna()]
    log.info("%d oynanmis mac", len(df))

    run_id = conn.execute(
        "INSERT INTO ingest_run(source_id,started_at,status) VALUES(1,?,'partial')",
        (dt.datetime.now(dt.timezone.utc).isoformat(),)).lastrowid

    leagues: dict[str, int] = {}
    teams: dict[tuple[int, str], int] = {}
    books: dict[str, int] = {}
    n_match = n_odds = n_stats = 0

    for row in df.itertuples(index=False):
        div = str(row.Division)
        country, lname, tier = DIVISION_MAP.get(div, ("XX", div, 1))
        date = pd.Timestamp(row.MatchDate)
        kickoff = f"{date:%Y-%m-%d}T{_time_of(getattr(row, 'MatchTime', None))}+00:00"

        lid = leagues.get(lname)
        if lid is None:
            lid = conn.execute(
                """INSERT INTO league(name,country,tier,gender,age_group,
                       data_quality,strength_coef) VALUES(?,?,?,'M','senior',1.0,1.0)""",
                (lname, country, tier)).lastrowid
            leagues[lname] = lid

        def team(name: str) -> int:
            key = (lid, name)
            tid = teams.get(key)
            if tid is None:
                tid = conn.execute(
                    "INSERT INTO team(canonical_name,country) VALUES(?,?)",
                    (name, country)).lastrowid
                conn.execute(
                    """INSERT OR IGNORE INTO team_alias(source_id,external_id,
                           raw_name,team_id,confidence) VALUES(1,?,?,?,1.0)""",
                    (f"{div}:{name}", name, tid))
                teams[key] = tid
            return tid

        h, a = team(str(row.HomeTeam)), team(str(row.AwayTeam))
        try:
            mid = conn.execute(
                """INSERT INTO match(league_id,season,kickoff_utc,home_team_id,
                       away_team_id,stage,status,home_goals,away_goals)
                   VALUES(?,?,?,?,?,'league','finished',?,?)""",
                (lid, _season_of(date), kickoff, h, a,
                 int(row.FTHome), int(row.FTAway))).lastrowid
        except sqlite3.IntegrityError:
            continue
        n_match += 1

        conn.execute(
            """INSERT OR IGNORE INTO match_source_record(match_id,source_id,
                   ingest_run_id,observed_at,payload_json,payload_hash)
               VALUES(?,1,?,?,?,?)""",
            (mid, run_id, kickoff, "{}", f"{div}:{date:%Y%m%d}:{h}:{a}"))

        hs = _i(getattr(row, "HomeShots", None))
        if hs is not None:
            conn.execute(
                "INSERT OR REPLACE INTO match_stats VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (mid, hs, _i(row.AwayShots), _i(row.HomeTarget), _i(row.AwayTarget),
                 _i(getattr(row, "HomeCorners", None)), _i(getattr(row, "AwayCorners", None)),
                 _i(getattr(row, "HomeYellow", None)), _i(getattr(row, "AwayYellow", None)),
                 _i(getattr(row, "HomeRed", None)), _i(getattr(row, "AwayRed", None)),
                 kickoff))
            n_stats += 1

        # Oranlar: Odd* = piyasa ortalamasi (adil olasilik), Max* = en iyi oran (oynanacak fiyat)
        quotes = []
        if not pd.isna(getattr(row, "OddHome", float("nan"))):
            quotes.append(("market_avg", "1X2", None,
                           {"HOME": _f(row.OddHome), "DRAW": _f(row.OddDraw), "AWAY": _f(row.OddAway)}))
        if not pd.isna(getattr(row, "MaxHome", float("nan"))):
            quotes.append(("market_best", "1X2", None,
                           {"HOME": _f(row.MaxHome), "DRAW": _f(row.MaxDraw), "AWAY": _f(row.MaxAway)}))
        if not pd.isna(getattr(row, "Over25", float("nan"))):
            quotes.append(("market_avg", "OU", 2.5,
                           {"OVER": _f(row.Over25), "UNDER": _f(row.Under25)}))
        for code, market, line, prices in quotes:
            bid = books.get(code)
            if bid is None:
                bid = conn.execute(
                    "INSERT INTO bookmaker(code,is_sharp) VALUES(?,0)", (code,)).lastrowid
                books[code] = bid
            for sel, price in prices.items():
                if price is None:
                    continue
                conn.execute(
                    """INSERT INTO odds_snapshot(match_id,bookmaker_id,market,line,
                           selection,price,captured_at,is_closing)
                       VALUES(?,?,?,?,?,?,?,1)""",
                    (mid, bid, market, line, sel, price, kickoff))
                n_odds += 1

        if n_match % 20000 == 0:
            conn.commit()
            log.info("  %d mac islendi...", n_match)

    conn.execute(
        "UPDATE ingest_run SET finished_at=?,status='ok',row_count=? WHERE id=?",
        (dt.datetime.now(dt.timezone.utc).isoformat(), n_match, run_id))
    conn.commit()
    conn.execute("VACUUM")
    conn.commit()

    log.info("\n=== YUKLEME TAMAM ===")
    log.info("lig: %d | takim: %d | bahisci: %d", len(leagues), len(teams), len(books))
    log.info("mac: %d | istatistik: %d | oran satiri: %d", n_match, n_stats, n_odds)
    for name in sorted(leagues):
        c = conn.execute("SELECT COUNT(*) FROM match WHERE league_id=?", (leagues[name],)).fetchone()[0]
        log.info("  %-28s %6d mac", name, c)
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "edge.db")
