"""
Sıfırdan veritabanı kurulumu ve toplu yükleme.

Kullanım:
    python scripts/bootstrap.py --csv rawdata/Matches.csv --division T1 --db edge.db
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

import pandas as pd

from app.ingest.providers.footballdata_csv import FootballDataCsvProvider, DIVISION_MAP

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("bootstrap")


def init_db(db_path: str, schema_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    for f in ("schema.sql", "schema_billing.sql"):
        conn.executescript((schema_dir / f).read_text())
    # Model çıktısı tablosu (API'nin okuduğu)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS match_model_output (
            match_id INTEGER PRIMARY KEY REFERENCES match(id),
            lambda_home REAL NOT NULL, lambda_away REAL NOT NULL,
            rho REAL NOT NULL, model_confidence REAL NOT NULL,
            model_version TEXT NOT NULL, computed_at TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn


def load(conn: sqlite3.Connection, provider: FootballDataCsvProvider,
         divisions: list[str], date_from: dt.date, date_to: dt.date) -> dict:
    stats = {"matches": 0, "odds": 0, "teams": 0, "skipped": 0}

    conn.execute("INSERT OR IGNORE INTO source(code, kind, trust_weight) VALUES (?,?,?)",
                 (provider.code, "stats", provider.trust_weight))
    for bk, sharp in (("market_avg", 1), ("market_best", 0)):
        conn.execute("INSERT OR IGNORE INTO bookmaker(code, is_sharp) VALUES (?,?)",
                     (bk, sharp))

    run = conn.execute(
        """INSERT INTO ingest_run(source_id, started_at, status)
           VALUES ((SELECT id FROM source WHERE code=?), ?, 'partial')""",
        (provider.code, dt.datetime.now(dt.timezone.utc).isoformat()))
    run_id = run.lastrowid

    league_ids: dict[str, int] = {}
    team_ids: dict[str, int] = {}

    for raw in provider.fetch_matches(date_from, date_to, divisions):
        n = provider.normalize_match(raw)

        lg = n["league_code"]
        if lg not in league_ids:
            cur = conn.execute(
                """INSERT INTO league(name, country, tier, data_quality, strength_coef)
                   VALUES (?,?,?,?,?)""",
                (n["league_name"], n["league_country"], n["league_tier"], 1.0, 1.0))
            league_ids[lg] = cur.lastrowid

        for side in ("home", "away"):
            name = n[f"{side}_raw_name"]
            if name not in team_ids:
                cur = conn.execute(
                    "INSERT INTO team(canonical_name, country) VALUES (?,?)",
                    (name, n["league_country"]))
                team_ids[name] = cur.lastrowid
                conn.execute(
                    """INSERT OR IGNORE INTO team_alias(source_id, external_id,
                           raw_name, team_id, confidence)
                       VALUES ((SELECT id FROM source WHERE code=?),?,?,?,1.0)""",
                    (provider.code, name, name, team_ids[name]))
                stats["teams"] += 1

        try:
            cur = conn.execute(
                """INSERT INTO match(league_id, season, kickoff_utc, home_team_id,
                       away_team_id, status, home_goals, away_goals)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (league_ids[lg], n["season"], n["kickoff_utc"],
                 team_ids[n["home_raw_name"]], team_ids[n["away_raw_name"]],
                 n["status"], n["home_goals"], n["away_goals"]))
            match_id = cur.lastrowid
        except sqlite3.IntegrityError:
            stats["skipped"] += 1
            continue

        conn.execute(
            """INSERT OR IGNORE INTO match_source_record(match_id, source_id,
                   ingest_run_id, observed_at, payload_json, payload_hash)
               VALUES (?, (SELECT id FROM source WHERE code=?), ?, ?, ?, ?)""",
            (match_id, provider.code, run_id, raw.observed_at.isoformat(),
             json.dumps(raw.payload, default=str), raw.payload_hash))

        od = provider.normalize_odds(raw)
        for q in od["quotes"]:
            for sel, price in q["prices"].items():
                conn.execute(
                    """INSERT INTO odds_snapshot(match_id, bookmaker_id, market, line,
                           selection, price, captured_at, is_closing)
                       VALUES (?, (SELECT id FROM bookmaker WHERE code=?), ?,?,?,?,?,1)""",
                    (match_id, q["bookmaker_code"], q["market"], q["line"],
                     sel, price, n["kickoff_utc"]))
                stats["odds"] += 1

        stats["matches"] += 1
        if stats["matches"] % 1000 == 0:
            conn.commit()
            log.info("  %d maç yüklendi...", stats["matches"])

    conn.execute("UPDATE ingest_run SET finished_at=?, status='ok', row_count=? WHERE id=?",
                 (dt.datetime.now(dt.timezone.utc).isoformat(),
                  stats["matches"], run_id))
    conn.commit()
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--db", default="edge.db")
    ap.add_argument("--division", nargs="+", default=["T1"])
    ap.add_argument("--from", dest="date_from", default="2000-01-01")
    ap.add_argument("--to", dest="date_to", default="2030-01-01")
    a = ap.parse_args()

    schema_dir = Path(__file__).resolve().parents[1] / "app" / "db"
    Path(a.db).unlink(missing_ok=True)

    conn = init_db(a.db, schema_dir)
    provider = FootballDataCsvProvider(a.csv)

    log.info("Ligler: %s", ", ".join(
        f"{d} ({DIVISION_MAP.get(d, ('','?'))[1]})" for d in a.division))

    stats = load(conn, provider, a.division,
                 dt.date.fromisoformat(a.date_from), dt.date.fromisoformat(a.date_to))

    log.info("\nYükleme tamam:")
    for k, v in stats.items():
        log.info("  %-10s %d", k, v)
    conn.close()


if __name__ == "__main__":
    main()
