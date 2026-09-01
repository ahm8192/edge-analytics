"""
openfootball/football.json -> SQLite şeması yükleyici.

Bu ÜCRETSİZ bir tohum veri kaynağıdır: sonuç var, oran ve xG YOK.
Modeli ayağa kaldırmak ve boru hattını doğrulamak için yeterli;
kenar payı hesabı için oran verisi ayrıca gerekir.

Kullanım:
    python scripts/load_openfootball.py --data-dir data/raw --db edge.db
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import sqlite3

LEAGUE_META = {
    "en.1": ("Premier League", "England", 1, 1.00),
    "en.2": ("Championship", "England", 2, 0.78),
    "de.1": ("Bundesliga", "Germany", 1, 0.97),
    "es.1": ("La Liga", "Spain", 1, 0.98),
    "it.1": ("Serie A", "Italy", 1, 0.96),
    "fr.1": ("Ligue 1", "France", 1, 0.92),
    "tr.1": ("Süper Lig", "Turkey", 1, 0.82),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--schema", default="app/db/schema.sql")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    schema = pathlib.Path(args.schema)
    if schema.exists():
        conn.executescript(schema.read_text())

    conn.execute("""INSERT OR IGNORE INTO source(code, kind, trust_weight)
                    VALUES ('openfootball', 'stats', 0.6)""")

    league_ids, team_ids = {}, {}
    inserted = skipped = 0

    for path in sorted(pathlib.Path(args.data_dir).glob("*.json")):
        season, code = path.stem.split("_", 1)
        if code not in LEAGUE_META:
            continue
        name, country, tier, strength = LEAGUE_META[code]

        lid = league_ids.get(code) or _upsert_league(conn, name, country, tier, strength)
        league_ids[code] = lid

        for m in json.load(open(path)).get("matches", []):
            score = (m.get("score") or {}).get("ft")
            if not score or len(score) != 2:
                skipped += 1
                continue

            hid = team_ids.setdefault(m["team1"], _upsert_team(conn, m["team1"], country))
            aid = team_ids.setdefault(m["team2"], _upsert_team(conn, m["team2"], country))

            kickoff = f"{m['date']}T{m.get('time', '15:00')}:00+00:00"
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO match(league_id, season, kickoff_utc,
                           home_team_id, away_team_id, status, home_goals, away_goals)
                       VALUES (?,?,?,?,?,'finished',?,?)""",
                    (lid, season, kickoff, hid, aid, int(score[0]), int(score[1])))
                inserted += conn.total_changes and 1 or 0
            except sqlite3.IntegrityError:
                skipped += 1

    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM match").fetchone()[0]
    t = conn.execute("SELECT COUNT(*) FROM team").fetchone()[0]
    print(f"Yüklendi: {n} maç, {t} takım, {len(league_ids)} lig (atlanan {skipped})")
    conn.close()


def _upsert_league(conn, name, country, tier, strength) -> int:
    row = conn.execute("SELECT id FROM league WHERE name=? AND country=?",
                       (name, country)).fetchone()
    if row:
        return int(row[0])
    cur = conn.execute(
        """INSERT INTO league(name, country, tier, gender, age_group,
                              data_quality, strength_coef)
           VALUES (?,?,?, 'M', 'senior', 0.6, ?)""",
        (name, country, tier, strength))
    return int(cur.lastrowid)


def _upsert_team(conn, name, country) -> int:
    row = conn.execute("SELECT id FROM team WHERE canonical_name=?", (name,)).fetchone()
    if row:
        return int(row[0])
    cur = conn.execute(
        "INSERT INTO team(canonical_name, country) VALUES (?,?)", (name, country))
    return int(cur.lastrowid)


if __name__ == "__main__":
    main()
