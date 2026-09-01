"""
Sağlayıcı kaydı ve orkestrasyon (madde 1, 12, 14).

İki sağlayıcıdan aynı veriyi çekmek israf değil, sigortadır:
biri bozulduğunda fark edersin ve çalışmaya devam edersin.
"""
from __future__ import annotations
import datetime as dt
import logging

from .base import Provider, store_raw, resolve_team

log = logging.getLogger(__name__)


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        self._providers[provider.code] = provider
        log.info("Sağlayıcı kayıtlı: %s", provider.code)

    def get(self, code: str) -> Provider:
        return self._providers[code]

    def all(self) -> list[Provider]:
        return list(self._providers.values())

    def capable_of(self, capability: str) -> list[Provider]:
        return [p for p in self._providers.values()
                if getattr(p.capabilities, capability, False)]

    def trust_map(self) -> dict[str, float]:
        return {p.code: p.trust_weight for p in self._providers.values()}

    def health(self) -> list[dict]:
        return [p.health for p in self._providers.values()]


def orchestrate(registry: ProviderRegistry, conn,
                date_from: dt.date, date_to: dt.date) -> dict:
    """
    Tam bir akış turu:
      1. Maçları TÜM yetkin sağlayıcılardan çek (çapraz doğrulama için)
      2. Ham kayıtları köken bilgisiyle sakla
      3. Çelişkileri uzlaştır
      4. Olay verisini birincil sağlayıcıdan çek
    """
    from ..reconcile import reconcile_match

    run_id = _start_run(conn, "orchestrator")
    stats = {"matches": 0, "shots": 0, "errors": 0, "conflicts": 0}

    match_providers = registry.capable_of("matches")
    if not match_providers:
        log.error("Maç verisi verebilen sağlayıcı yok")
        return stats

    seen: dict[str, int] = {}

    for provider in match_providers:
        try:
            for raw in provider.fetch_matches(date_from, date_to):
                norm = provider.normalize_match(raw)
                home = resolve_team(conn, provider.code,
                                    norm["home_external_id"], norm["home_raw_name"])
                away = resolve_team(conn, provider.code,
                                    norm["away_external_id"], norm["away_raw_name"])
                if home is None or away is None:
                    continue    # eşleşmemiş takım — elle onay bekliyor

                match_id = _upsert_match(conn, norm, home, away)
                seen[norm["external_id"]] = match_id
                store_raw(conn, match_id, provider.code, run_id, raw)
                stats["matches"] += 1
        except Exception as e:
            stats["errors"] += 1
            log.exception("%s maç akışı başarısız: %s", provider.code, e)

    # Çelişki uzlaştırma — hangi sağlayıcının hangi alanı kazandığı loglanır
    trust = registry.trust_map()
    for match_id in set(seen.values()):
        try:
            res = reconcile_match(conn, match_id,
                                  ["home_goals", "away_goals", "status", "kickoff_utc"],
                                  trust)
            stats["conflicts"] += res["conflicts"]
        except Exception as e:
            log.warning("Uzlaştırma hatası (%s): %s", match_id, e)

    # Olay verisi: en iyi xG kaynağından
    shot_providers = sorted(registry.capable_of("shot_events"),
                            key=lambda p: -p.trust_weight)
    if shot_providers:
        primary = shot_providers[0]
        for ext_id, match_id in seen.items():
            try:
                for raw in primary.fetch_shot_events(ext_id):
                    store_raw(conn, match_id, primary.code, run_id, raw)
                    stats["shots"] += 1
            except Exception:
                stats["errors"] += 1

    _finish_run(conn, run_id, stats)
    return stats


def _start_run(conn, source_code: str) -> int:
    cur = conn.execute(
        """INSERT INTO ingest_run(source_id, started_at, status)
           VALUES ((SELECT id FROM source WHERE code=?), ?, 'partial')""",
        (source_code, dt.datetime.now(dt.timezone.utc).isoformat()))
    conn.commit()
    return int(cur.lastrowid)


def _finish_run(conn, run_id: int, stats: dict) -> None:
    status = "ok" if stats["errors"] == 0 else "partial"
    conn.execute(
        """UPDATE ingest_run SET finished_at=?, status=?, row_count=?
           WHERE id=?""",
        (dt.datetime.now(dt.timezone.utc).isoformat(), status,
         stats["matches"] + stats["shots"], run_id))
    conn.commit()


def _upsert_match(conn, norm: dict, home_id: int, away_id: int) -> int:
    row = conn.execute(
        """SELECT id FROM match WHERE home_team_id=? AND away_team_id=?
           AND DATE(kickoff_utc)=DATE(?)""",
        (home_id, away_id, norm["kickoff_utc"])).fetchone()
    if row:
        conn.execute(
            """UPDATE match SET status=?, home_goals=?, away_goals=?
               WHERE id=?""",
            (norm["status"], norm["home_goals"], norm["away_goals"], row[0]))
        conn.commit()
        return int(row[0])

    cur = conn.execute(
        """INSERT INTO match(league_id, season, kickoff_utc, home_team_id,
               away_team_id, status, home_goals, away_goals)
           VALUES (?,?,?,?,?,?,?,?)""",
        (norm.get("league_id", 1), norm.get("season", ""), norm["kickoff_utc"],
         home_id, away_id, norm["status"], norm["home_goals"], norm["away_goals"]))
    conn.commit()
    return int(cur.lastrowid)
