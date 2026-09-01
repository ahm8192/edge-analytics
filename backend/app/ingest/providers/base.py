"""
Veri sağlayıcı soyutlaması (madde 1, 2, 4, 6, 12, 14).

Her sağlayıcı bu arayüzü uygular. Kazanç: yeni sağlayıcı eklemek 100 satır,
sağlayıcı değiştirmek tek satır. Bir sağlayıcıya kilitlenmek bu projede
en pahalı mimari hatadır — fiyatları artırır, API'yi bozar, kapanır.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Hız sınırı
# ---------------------------------------------------------------------
class RateLimiter:
    """
    Kayan pencere. Sağlayıcının limitini aşmak hesabın askıya alınmasıyla
    sonuçlanır ve maç günü veri gelmemesi modelden daha pahalıdır.
    """

    def __init__(self, max_calls: int, per_seconds: float):
        self.max_calls = max_calls
        self.per_seconds = per_seconds
        self._calls: deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > self.per_seconds:
            self._calls.popleft()
        if len(self._calls) >= self.max_calls:
            sleep_for = self.per_seconds - (now - self._calls[0]) + 0.05
            log.debug("Hız sınırı: %.2f sn bekleniyor", sleep_for)
            time.sleep(max(0.0, sleep_for))
            return self.acquire()
        self._calls.append(time.monotonic())


def with_retry(fn, attempts: int = 4, base_delay: float = 1.0,
               retry_on=(TimeoutError, ConnectionError)):
    """Üstel geri çekilme. 429 ve 5xx için sağlayıcı sınıfı kendi kontrolünü ekler."""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except retry_on as e:
            last = e
            delay = base_delay * (2 ** i)
            log.warning("Deneme %d/%d başarısız (%s), %.1f sn sonra", i + 1, attempts, e, delay)
            time.sleep(delay)
    raise last if last else RuntimeError("Yeniden deneme tükendi")


# ---------------------------------------------------------------------
# Ham kayıt
# ---------------------------------------------------------------------
@dataclass
class RawRecord:
    """
    Sağlayıcıdan gelen ham veri, DEĞİŞTİRİLMEDEN saklanır.
    Sebep: normalizasyon mantığında hata bulursan geçmişi yeniden işleyebilirsin.
    Sadece normalize edilmiş hâli saklarsan o veri kaybolmuştur.
    """
    source_code: str
    entity: str                    # match | shot | lineup | odds | news
    external_id: str
    payload: dict[str, Any]
    observed_at: dt.datetime

    @property
    def payload_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:32]


@dataclass
class ProviderCapabilities:
    """
    Hangi sağlayıcı neyi verebiliyor. Orkestratör buna bakarak
    hangi sağlayıcıdan neyi çekeceğine karar verir.
    """
    matches: bool = False
    shot_events: bool = False       # olay bazlı veri — madde 2
    xg: bool = False
    lineups: bool = False
    injuries: bool = False
    odds: bool = False
    odds_history: bool = False      # madde 7 — en değerli özellik
    live: bool = False
    leagues_covered: list[int] = field(default_factory=list)
    typical_delay_minutes: int = 0
    xg_model_name: str | None = None   # madde 47


# ---------------------------------------------------------------------
# Sağlayıcı arayüzü
# ---------------------------------------------------------------------
class Provider(ABC):
    code: str
    capabilities: ProviderCapabilities
    trust_weight: float = 1.0

    def __init__(self, api_key: str | None = None,
                 rate_limit: tuple[int, float] = (60, 60.0)):
        self.api_key = api_key
        self.limiter = RateLimiter(*rate_limit)
        self._call_count = 0
        self._error_count = 0

    # --- alt sınıfın uygulayacakları ---------------------------------
    @abstractmethod
    def fetch_matches(self, date_from: dt.date,
                      date_to: dt.date) -> Iterable[RawRecord]: ...

    def fetch_shot_events(self, external_match_id: str) -> Iterable[RawRecord]:
        return []

    def fetch_lineups(self, external_match_id: str) -> Iterable[RawRecord]:
        return []

    def fetch_injuries(self, external_team_id: str) -> Iterable[RawRecord]:
        return []

    def fetch_odds(self, external_match_id: str,
                   markets: list[str]) -> Iterable[RawRecord]:
        return []

    # --- normalizasyon: ham -> kanonik sözlük ------------------------
    @abstractmethod
    def normalize_match(self, raw: RawRecord) -> dict: ...

    def normalize_shot(self, raw: RawRecord) -> dict:
        raise NotImplementedError

    def normalize_odds(self, raw: RawRecord) -> dict:
        raise NotImplementedError

    # --- ortak yardımcılar --------------------------------------------
    def _record(self, entity: str, external_id: str, payload: dict) -> RawRecord:
        return RawRecord(self.code, entity, str(external_id), payload,
                         dt.datetime.now(dt.timezone.utc))

    @property
    def health(self) -> dict:
        rate = self._error_count / max(self._call_count, 1)
        return {"source": self.code, "calls": self._call_count,
                "errors": self._error_count, "error_rate": rate,
                "degraded": rate > 0.15}


# ---------------------------------------------------------------------
# Takım eşleme (madde 6)
# ---------------------------------------------------------------------
def normalize_team_name(name: str) -> str:
    """
    Eşleme için sadeleştirilmiş ad. Bu fonksiyon yalnızca ADAY üretir;
    kesin eşleme team_alias tablosundan gelir ve elle onaylanır.
    Otomatik eşlemeye güvenmek mükerrer maç kayıtlarının bir numaralı sebebidir.
    """
    s = name.lower().strip()
    for ch, rep in (("ı", "i"), ("ğ", "g"), ("ü", "u"), ("ş", "s"),
                    ("ö", "o"), ("ç", "c"), ("é", "e"), ("á", "a")):
        s = s.replace(ch, rep)
    noise = ["fc", "sc", "ac", "cf", "sk", "as", "afc", "cd", "ud",
             "spor kulubu", "kulubu", "футбол", "1907", "1903"]
    tokens = [t for t in s.replace(".", " ").replace("-", " ").split()
              if t not in noise]
    return " ".join(tokens)


def resolve_team(conn, source_code: str, external_id: str,
                 raw_name: str) -> int | None:
    """
    Önce alias tablosuna bakar. Yoksa ad benzerliğiyle ADAY üretir ve
    düşük güvenle kaydeder — ama eşleşme onaylanana kadar None döner.
    """
    row = conn.execute(
        """SELECT ta.team_id FROM team_alias ta JOIN source s ON s.id = ta.source_id
           WHERE s.code = ? AND ta.external_id = ?""",
        (source_code, str(external_id))).fetchone()
    if row:
        return int(row[0])

    target = normalize_team_name(raw_name)
    candidates = conn.execute("SELECT id, canonical_name FROM team").fetchall()
    for tid, cname in candidates:
        if normalize_team_name(cname) == target:
            conn.execute(
                """INSERT OR IGNORE INTO team_alias(source_id, external_id,
                       raw_name, team_id, confidence)
                   VALUES ((SELECT id FROM source WHERE code=?),?,?,?,?)""",
                (source_code, str(external_id), raw_name, tid, 0.8))
            conn.commit()
            return int(tid)

    log.warning("Eşleşmeyen takım: %s (%s/%s) — elle eşleme gerekiyor",
                raw_name, source_code, external_id)
    return None


def store_raw(conn, match_id: int, source_code: str, run_id: int | None,
              raw: RawRecord) -> None:
    """Ham kayıt köken bilgisiyle saklanır (madde 1, 4)."""
    conn.execute(
        """INSERT OR IGNORE INTO match_source_record(
               match_id, source_id, ingest_run_id, observed_at,
               payload_json, payload_hash)
           VALUES (?, (SELECT id FROM source WHERE code=?), ?, ?, ?, ?)""",
        (match_id, source_code, run_id, raw.observed_at.isoformat(),
         json.dumps(raw.payload, default=str), raw.payload_hash))
