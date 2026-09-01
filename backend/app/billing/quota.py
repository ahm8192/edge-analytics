"""Ücretsiz katman kota sayacı. Sunucu tarafında tutulur; istemci sayacı sadece UI."""
from __future__ import annotations
import datetime as dt
import sqlite3

from .tiers import Tier, quota_for


class QuotaExceeded(Exception):
    def __init__(self, key: str, limit: int, resets_at: dt.datetime):
        self.key, self.limit, self.resets_at = key, limit, resets_at
        super().__init__(f"{key} kotası doldu ({limit}/gün)")


def _window_start(now: dt.datetime, hours: int = 24) -> dt.datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def consume(conn: sqlite3.Connection, user_id: int, tier: Tier,
            key: str, amount: int = 1) -> tuple[int, int]:
    """
    Kotadan düşer. (kalan, limit) döner. Limit -1 ise sınırsız.
    Atomik olsun diye tek UPDATE ... WHERE ile yazılır.
    """
    limit = quota_for(tier, key)
    if limit < 0:
        return (-1, -1)

    now = dt.datetime.now(dt.timezone.utc)
    ws = _window_start(now).isoformat()

    conn.execute(
        """INSERT INTO usage_quota(user_id, quota_key, period_start, used, limit_value)
           VALUES (?,?,?,0,?)
           ON CONFLICT(user_id, quota_key, period_start) DO UPDATE SET limit_value=?""",
        (user_id, key, ws, limit, limit))

    cur = conn.execute(
        """UPDATE usage_quota SET used = used + ?
           WHERE user_id=? AND quota_key=? AND period_start=? AND used + ? <= limit_value""",
        (amount, user_id, key, ws, amount))

    if cur.rowcount == 0:
        conn.commit()
        raise QuotaExceeded(key, limit, _window_start(now) + dt.timedelta(days=1))

    used = conn.execute(
        "SELECT used FROM usage_quota WHERE user_id=? AND quota_key=? AND period_start=?",
        (user_id, key, ws)).fetchone()[0]
    conn.commit()
    return (limit - used, limit)


def peek(conn: sqlite3.Connection, user_id: int, tier: Tier, key: str) -> tuple[int, int]:
    limit = quota_for(tier, key)
    if limit < 0:
        return (-1, -1)
    ws = _window_start(dt.datetime.now(dt.timezone.utc)).isoformat()
    row = conn.execute(
        "SELECT used FROM usage_quota WHERE user_id=? AND quota_key=? AND period_start=?",
        (user_id, key, ws)).fetchone()
    used = row[0] if row else 0
    return (max(0, limit - used), limit)
