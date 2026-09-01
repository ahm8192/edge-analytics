"""
Pipeline sağlık kontrolü (madde 14).

Veri boru hattı gürültüsüzce bozulur: sağlayıcı bir alanı yeniden adlandırır,
xG kolonu null gelmeye başlar, bir lig eksik akar. Model çalışmaya devam eder
ve yanlış tahmin üretir. Bu dosya o sessizliği kırar.
"""
from __future__ import annotations
import datetime as dt
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    severity: str = "warn"      # info | warn | critical


@dataclass
class HealthReport:
    checks: list[Check] = field(default_factory=list)
    ran_at: str = ""

    @property
    def critical_failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed and c.severity == "critical"]

    @property
    def should_halt(self) -> bool:
        return len(self.critical_failures) > 0

    def summary(self) -> dict:
        return {"ran_at": self.ran_at,
                "passed": sum(c.passed for c in self.checks),
                "total": len(self.checks),
                "halt": self.should_halt,
                "failures": [{"name": c.name, "detail": c.detail,
                              "severity": c.severity}
                             for c in self.checks if not c.passed]}


def run_all(conn) -> HealthReport:
    now = dt.datetime.now(dt.timezone.utc)
    r = HealthReport(ran_at=now.isoformat())

    r.checks.append(_freshness(conn, now))
    r.checks.append(_volume_drop(conn))
    r.checks.append(_null_rate(conn, "shot_event", "xg", max_null=0.02))
    r.checks.append(_orphan_matches(conn))
    r.checks.append(_odds_coverage(conn))
    r.checks.append(_duplicate_matches(conn))
    r.checks.append(_source_disagreement(conn))
    r.checks.append(_impossible_values(conn))

    for c in r.checks:
        if not c.passed:
            log.log(logging.ERROR if c.severity == "critical" else logging.WARNING,
                    "SAĞLIK: %s — %s", c.name, c.detail)
    return r


def _freshness(conn, now) -> Check:
    row = conn.execute(
        "SELECT MAX(finished_at) FROM ingest_run WHERE status = 'ok'").fetchone()
    if not row or not row[0]:
        return Check("tazelik", False, "Hiç başarılı akış yok", "critical")
    last = dt.datetime.fromisoformat(row[0])
    hours = (now - last).total_seconds() / 3600
    return Check("tazelik", hours < 12,
                 f"Son başarılı akış {hours:.1f} saat önce",
                 "critical" if hours > 36 else "warn")


def _volume_drop(conn) -> Check:
    """Bugünkü satır sayısı son 7 günün yarısının altındaysa bir şey kırılmıştır."""
    rows = conn.execute(
        """SELECT DATE(started_at) d, SUM(row_count) n FROM ingest_run
           WHERE started_at >= DATE('now','-8 day') GROUP BY d ORDER BY d""").fetchall()
    if len(rows) < 3:
        return Check("hacim", True, "Karşılaştırma için yeterli geçmiş yok", "info")
    today = rows[-1][1] or 0
    prior = [r[1] or 0 for r in rows[:-1]]
    median = sorted(prior)[len(prior) // 2]
    ok = today >= median * 0.5
    return Check("hacim", ok, f"Bugün {today}, medyan {median}",
                 "critical" if today == 0 else "warn")


def _null_rate(conn, table: str, column: str, max_null: float) -> Check:
    row = conn.execute(
        f"""SELECT COUNT(*), SUM(CASE WHEN {column} IS NULL THEN 1 ELSE 0 END)
            FROM {table} WHERE observed_at >= DATE('now','-3 day')""").fetchone()
    total, nulls = row[0] or 0, row[1] or 0
    if total == 0:
        return Check(f"{table}.{column} boşluk", True, "Yeni satır yok", "info")
    rate = nulls / total
    return Check(f"{table}.{column} boşluk", rate <= max_null,
                 f"%{rate*100:.1f} null ({nulls}/{total})",
                 "critical" if rate > 0.25 else "warn")


def _orphan_matches(conn) -> Check:
    """Yaklaşan maçın model çıktısı yoksa uygulamada boş ekran olur."""
    n = conn.execute(
        """SELECT COUNT(*) FROM match m
           WHERE m.kickoff_utc BETWEEN DATETIME('now') AND DATETIME('now','+2 day')
             AND NOT EXISTS (SELECT 1 FROM prediction p WHERE p.match_id = m.id)"""
    ).fetchone()[0]
    return Check("model çıktısı eksik maç", n == 0,
                 f"{n} maçın tahmini yok", "critical" if n > 5 else "warn")


def _odds_coverage(conn) -> Check:
    n = conn.execute(
        """SELECT COUNT(*) FROM match m
           WHERE m.kickoff_utc BETWEEN DATETIME('now') AND DATETIME('now','+2 day')
             AND NOT EXISTS (SELECT 1 FROM odds_snapshot o WHERE o.match_id = m.id)"""
    ).fetchone()[0]
    return Check("oran kapsamı", n == 0, f"{n} maçın oranı yok", "warn")


def _duplicate_matches(conn) -> Check:
    """madde 6: takım eşleme bozulursa aynı maç iki kayıt olarak akar."""
    n = conn.execute(
        """SELECT COUNT(*) FROM (
             SELECT home_team_id, away_team_id, DATE(kickoff_utc) d, COUNT(*) c
             FROM match GROUP BY home_team_id, away_team_id, d HAVING c > 1)"""
    ).fetchone()[0]
    return Check("mükerrer maç", n == 0, f"{n} mükerrer kayıt",
                 "critical" if n > 0 else "info")


def _source_disagreement(conn) -> Check:
    """madde 1: çözülmemiş kaynak çelişkileri birikiyorsa veri güvenilmez."""
    n = conn.execute(
        """SELECT COUNT(*) FROM source_conflict
           WHERE resolution = 'unresolved'
             AND detected_at >= DATE('now','-7 day')""").fetchone()[0]
    return Check("kaynak çelişkisi", n < 20, f"{n} çözülmemiş çelişki", "warn")


def _impossible_values(conn) -> Check:
    """Aralık dışı değerler sessiz bozulmanın en net işaretidir."""
    bad = conn.execute(
        """SELECT
             (SELECT COUNT(*) FROM shot_event WHERE xg < 0 OR xg > 1) +
             (SELECT COUNT(*) FROM odds_snapshot WHERE price <= 1.0 OR price > 1000) +
             (SELECT COUNT(*) FROM match WHERE home_goals < 0 OR home_goals > 20)"""
    ).fetchone()[0]
    return Check("aralık dışı değer", bad == 0, f"{bad} imkânsız değer",
                 "critical" if bad > 0 else "info")
