#!/usr/bin/env python3
"""Gerçek veriyi şemaya yükler. Çalıştır: python load_data.py <csv_kok_dizini>"""
from __future__ import annotations
import datetime as dt, json, logging, sqlite3, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.ingest.providers.footballdata_csv import FootballDataCsvProvider

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("load")


def init_db(path: str) -> sqlite3.Connection:
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    for f in ("app/db/schema.sql", "app/db/schema_billing.sql"):
        conn.executescript(open(f).read())
    # football-data.co.uk maç toplamı verir, olay bazlı vermez;
    # bu yüzden şut/korner için ek tablo
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
    """)
    conn.execute("INSERT INTO source(code,kind,trust_weight) VALUES('football_data_csv','stats',1.0)")
    conn.commit()
    return conn


def main(root: str, db_path: str = "edge.db"):
    conn = init_db(db_path)
    provider = FootballDataCsvProvider(root)

    files = provider.discover()
    log.info("%d CSV dosyası bulundu", len(files))

    leagues, teams, refs, books = {}, {}, {}, {}
    n_match = n_odds = n_stats = 0
    run = conn.execute(
        "INSERT INTO ingest_run(source_id,started_at,status) VALUES(1,?,'partial')",
        (dt.datetime.now(dt.timezone.utc).isoformat(),))
    run_id = run.lastrowid

    for raw in provider.fetch_matches(dt.date(1993, 1, 1), dt.date(2030, 1, 1)):
        n = provider.normalize_match(raw)
        if n["home_goals"] is None:
            continue

        lid = leagues.get(n["league_code"])
        if lid is None:
            lid = conn.execute(
                """INSERT INTO league(name,country,tier,gender,age_group,
                       data_quality,strength_coef) VALUES(?,?,?,'M','senior',1.0,1.0)""",
                (n["league_code"], n["league_country"], n["league_tier"])).lastrowid
            leagues[n["league_code"]] = lid

        def team(name):
            key = (lid, name)
            if key not in teams:
                tid = conn.execute(
                    "INSERT INTO team(canonical_name,country) VALUES(?,?)",
                    (name, n["league_country"])).lastrowid
                conn.execute(
                    """INSERT OR IGNORE INTO team_alias(source_id,external_id,
                           raw_name,team_id,confidence) VALUES(1,?,?,?,1.0)""",
                    (f"{n['league_code']}:{name}", name, tid))
                teams[key] = tid
            return teams[key]

        h, a = team(n["home_external_id"]), team(n["away_external_id"])

        try:
            mid = conn.execute(
                """INSERT INTO match(league_id,season,kickoff_utc,home_team_id,
                       away_team_id,stage,status,home_goals,away_goals)
                   VALUES(?,?,?,?,?,'league','finished',?,?)""",
                (lid, n["season"], n["kickoff_utc"], h, a,
                 n["home_goals"], n["away_goals"])).lastrowid
        except sqlite3.IntegrityError:
            continue
        n_match += 1

        conn.execute(
            """INSERT OR IGNORE INTO match_source_record(match_id,source_id,
                   ingest_run_id,observed_at,payload_json,payload_hash)
               VALUES(?,1,?,?,?,?)""",
            (mid, run_id, raw.observed_at.isoformat(),
             json.dumps(raw.payload, default=str), raw.payload_hash))

        if n["home_shots"] is not None:
            conn.execute(
                """INSERT OR REPLACE INTO match_stats VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (mid, n["home_shots"], n["away_shots"], n["home_shots_target"],
                 n["away_shots_target"], n["home_corners"], n["away_corners"],
                 n["home_yellow"], n["away_yellow"], n["home_red"], n["away_red"],
                 n["kickoff_utc"]))
            n_stats += 1

        if n.get("referee"):
            rname = str(n["referee"]).strip()
            if rname and rname not in refs:
                refs[rname] = conn.execute(
                    "INSERT INTO referee(name) VALUES(?)", (rname,)).lastrowid
            if rname:
                conn.execute(
                    "INSERT OR REPLACE INTO match_officials VALUES(?,?)",
                    (mid, refs[rname]))

        od = provider.normalize_odds(raw)
        for q in od["quotes"]:
            code = q["bookmaker_code"]
            if code not in books:
                books[code] = conn.execute(
                    "INSERT INTO bookmaker(code,is_sharp) VALUES(?,?)",
                    (code, int(q["is_sharp"]))).lastrowid
            for sel, price in q["prices"].items():
                conn.execute(
                    """INSERT INTO odds_snapshot(match_id,bookmaker_id,market,line,
                           selection,price,captured_at,is_closing)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (mid, books[code], q["market"], q.get("line"), sel, price,
                     n["kickoff_utc"], int(q["is_closing"])))
                n_odds += 1

        if n_match % 5000 == 0:
            conn.commit()
            log.info("  %d maç işlendi...", n_match)

    conn.execute(
        "UPDATE ingest_run SET finished_at=?,status='ok',row_count=? WHERE id=?",
        (dt.datetime.now(dt.timezone.utc).isoformat(), n_match, run_id))
    conn.commit()

    log.info("\n=== YÜKLEME TAMAM ===")
    log.info("lig: %d | takım: %d | hakem: %d | bahisçi: %d",
             len(leagues), len(teams), len(refs), len(books))
    log.info("maç: %d | istatistik: %d | oran satırı: %d", n_match, n_stats, n_odds)
    return conn


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data")
