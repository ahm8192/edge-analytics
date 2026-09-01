"""
Oran anlık görüntü takvimi (madde 7, 76, 83).

Oranı sabit aralıkla çekmek hem kotayı yakar hem de en önemli anı kaçırır.
Bilgi maça yaklaştıkça yoğunlaşır; örnekleme de öyle olmalı.

Kapanış oranı (madde 76) kaçırılırsa CLV hiç hesaplanamaz — bu yüzden
son pencerede sıklık en yüksektir.
"""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass


@dataclass
class SnapshotWindow:
    hours_before_min: float
    hours_before_max: float
    interval_minutes: int
    label: str


# Maça kalan süreye göre örnekleme sıklığı
SCHEDULE = [
    SnapshotWindow(72, 168, 360, "açılış takibi"),      # 6 saatte bir
    SnapshotWindow(24, 72, 120, "erken hareket"),        # 2 saatte bir
    SnapshotWindow(6, 24, 30, "kadro haberleri"),        # 30 dakikada bir
    SnapshotWindow(1, 6, 10, "yoğun dönem"),             # 10 dakikada bir
    SnapshotWindow(0.17, 1, 3, "kapanışa yakın"),        # 3 dakikada bir
    SnapshotWindow(0.0, 0.17, 1, "kapanış"),             # son 10 dk: dakikada bir
]


def interval_for(kickoff: dt.datetime, now: dt.datetime | None = None) -> int | None:
    """Şu an için kaç dakikada bir çekilmeli? None = çekme."""
    now = now or dt.datetime.now(dt.timezone.utc)
    hours = (kickoff - now).total_seconds() / 3600
    if hours < 0 or hours > 168:
        return None
    for w in SCHEDULE:
        if w.hours_before_min <= hours < w.hours_before_max:
            return w.interval_minutes
    return None


def is_closing_snapshot(kickoff: dt.datetime,
                        captured_at: dt.datetime,
                        tolerance_minutes: int = 5) -> bool:
    """
    Kapanış oranı = maç başlamadan hemen önceki son gözlem.
    Bu bayrak CLV hesabının temelidir; yanlış işaretlenirse tüm karne bozulur.
    """
    delta = (kickoff - captured_at).total_seconds() / 60
    return 0 <= delta <= tolerance_minutes


def due_matches(conn, now: dt.datetime | None = None) -> list[dict]:
    """Şu anda oran çekilmesi gereken maçlar. Zamanlayıcı bunu dakikada bir çağırır."""
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = conn.execute(
        """SELECT m.id, m.kickoff_utc,
                  (SELECT MAX(captured_at) FROM odds_snapshot o
                   WHERE o.match_id = m.id) AS last_capture
           FROM match m
           WHERE m.status = 'scheduled'
             AND m.kickoff_utc BETWEEN ? AND ?""",
        (now.isoformat(), (now + dt.timedelta(days=7)).isoformat())).fetchall()

    due = []
    for match_id, kickoff_str, last in rows:
        kickoff = dt.datetime.fromisoformat(kickoff_str)
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=dt.timezone.utc)
        interval = interval_for(kickoff, now)
        if interval is None:
            continue
        if last is None:
            due.append({"match_id": match_id, "kickoff": kickoff, "reason": "ilk"})
            continue
        last_dt = dt.datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=dt.timezone.utc)
        if (now - last_dt).total_seconds() / 60 >= interval:
            due.append({"match_id": match_id, "kickoff": kickoff,
                        "reason": f"{interval} dk aralık"})

    # Kapanışa en yakın olanlar önce — kota biterse en değerli veri alınmış olur
    return sorted(due, key=lambda d: d["kickoff"])


def estimate_daily_calls(match_count: int) -> int:
    """Kota planlaması: bir maç açılıştan kapanışa kaç çağrı tüketir."""
    per_match = sum(
        int((w.hours_before_max - w.hours_before_min) * 60 / w.interval_minutes)
        for w in SCHEDULE)
    return per_match * match_count // 7   # 7 güne yayılmış
