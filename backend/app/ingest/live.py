"""
Canlı bahis ve gecikme yönetimi (madde 85).

Canlı bahiste rakibin model değil, HIZ. Bahisçinin veri akışı seninkinden
0.5-3 saniye önde olur; sen gördüğünde fiyat çoktan düzeltilmiştir.

Bu modülün asıl işi kazandırmak değil, KAYBETTİRMEMEK: verinin bayat
olduğu anı tespit edip bahsi engellemek.
"""
from __future__ import annotations
import datetime as dt
import logging
from collections import deque
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)


# --------------------------------------------------------------------
# Gecikme bütçesi
# --------------------------------------------------------------------
@dataclass
class LatencyBudget:
    """
    Toplam gecikme = veri sağlayıcı gecikmesi + ağ + işleme + kullanıcı tepkisi.
    Bahisçinin kendi akışı genelde 1-2 sn önde. Bütçe aşılırsa bahis kapatılır.
    """
    max_total_ms: int = 2500
    max_data_age_ms: int = 1800
    max_processing_ms: int = 300
    assumed_book_advantage_ms: int = 1200

    def evaluate(self, data_age_ms: float, processing_ms: float,
                 network_rtt_ms: float) -> "LatencyVerdict":
        total = data_age_ms + processing_ms + network_rtt_ms
        reasons = []
        if data_age_ms > self.max_data_age_ms:
            reasons.append(f"veri {data_age_ms:.0f} ms bayat")
        if processing_ms > self.max_processing_ms:
            reasons.append(f"işleme {processing_ms:.0f} ms")
        if total > self.max_total_ms:
            reasons.append(f"toplam {total:.0f} ms bütçe dışı")

        deficit = total - self.assumed_book_advantage_ms
        return LatencyVerdict(
            total_ms=total,
            allowed=not reasons,
            deficit_ms=deficit,
            reasons=reasons,
        )


@dataclass
class LatencyVerdict:
    total_ms: float
    allowed: bool
    deficit_ms: float
    reasons: list[str] = field(default_factory=list)

    @property
    def message(self) -> str:
        if self.allowed:
            return f"Gecikme {self.total_ms:.0f} ms — bahis açık."
        return "Canlı bahis kapalı: " + ", ".join(self.reasons)


class LatencyMonitor:
    """Kayan pencerede gecikme ölçer. p95 kullanılır; ortalama yanıltıcıdır."""

    def __init__(self, window: int = 50):
        self._samples: deque[float] = deque(maxlen=window)

    def record(self, ms: float) -> None:
        self._samples.append(ms)

    @property
    def p95(self) -> float:
        return float(np.percentile(self._samples, 95)) if self._samples else 0.0

    @property
    def median(self) -> float:
        return float(np.median(self._samples)) if self._samples else 0.0

    def is_degraded(self, threshold_ms: float = 2000) -> bool:
        return self.p95 > threshold_ms


# --------------------------------------------------------------------
# Maç içi durum ve lambda güncelleme
# --------------------------------------------------------------------
@dataclass
class LiveState:
    minute: int
    home_goals: int
    away_goals: int
    home_red_cards: int = 0
    away_red_cards: int = 0
    observed_at: dt.datetime = field(default_factory=lambda:
                                     dt.datetime.now(dt.timezone.utc))

    @property
    def minutes_remaining(self) -> float:
        # 90 + tahmini uzatma. Geç dakikalarda uzatma oransal olarak büyür.
        base = max(0, 90 - self.minute)
        stoppage = 4.5 if self.minute > 80 else 1.5 if self.minute > 40 else 0.0
        return base + stoppage

    @property
    def score_diff(self) -> int:
        return self.home_goals - self.away_goals

    def age_ms(self, now: dt.datetime | None = None) -> float:
        now = now or dt.datetime.now(dt.timezone.utc)
        return (now - self.observed_at).total_seconds() * 1000


# Skor durumuna göre tempo değişimi. Öndeki takım yavaşlar, geride olan açılır.
GAME_STATE_EFFECT = {
    0: (1.00, 1.00),
    1: (0.94, 1.10),      # ev 1 önde: ev yavaşlar, deplasman baskı yapar
    2: (0.88, 1.14),
    3: (0.80, 1.10),      # fark açıldı: iki taraf da tempoyu düşürür
}


def live_lambdas(pre_match_home: float, pre_match_away: float,
                 state: LiveState) -> tuple[float, float]:
    """
    Maç öncesi gol beklentisini canlı duruma uyarlar.

    Üç düzeltme uygulanır:
      1. Kalan süre oranı (en büyük etken)
      2. Skor durumu — öndeki takım savunur (madde 56)
      3. Kırmızı kart — 10 kişi kalan takım belirgin düşer (madde 58)
    """
    remaining = state.minutes_remaining / 90.0
    lh = pre_match_home * remaining
    la = pre_match_away * remaining

    diff = abs(state.score_diff)
    lead_mult, trail_mult = GAME_STATE_EFFECT.get(min(diff, 3), (0.80, 1.10))
    if state.score_diff > 0:
        lh, la = lh * lead_mult, la * trail_mult
    elif state.score_diff < 0:
        lh, la = lh * trail_mult, la * lead_mult

    # Kırmızı kart: 10 kişi kalan takımın hücumu ~%30 düşer, yediği ~%25 artar
    for reds, is_home in ((state.home_red_cards, True), (state.away_red_cards, False)):
        for _ in range(reds):
            if is_home:
                lh *= 0.70
                la *= 1.25
            else:
                la *= 0.70
                lh *= 1.25

    return float(np.clip(lh, 0.01, 6.0)), float(np.clip(la, 0.01, 6.0))


def remaining_match_matrix(pre_home: float, pre_away: float,
                           state: LiveState, rho: float = -0.03):
    """
    Kalan sürede atılacak goller için skor matrisi.
    Nihai skor = mevcut skor + bu matris. 1X2 buradan hesaplanır.
    """
    from ..models.dixon_coles import build_matrix
    lh, la = live_lambdas(pre_home, pre_away, state)
    return build_matrix(lh, la, rho)


def live_1x2(pre_home: float, pre_away: float, state: LiveState,
             rho: float = -0.03) -> dict[str, float]:
    m = remaining_match_matrix(pre_home, pre_away, state, rho)
    n = m.shape[0]
    h = d = a = 0.0
    for i in range(n):
        for j in range(n):
            final = state.score_diff + (i - j)
            if final > 0:
                h += m[i, j]
            elif final == 0:
                d += m[i, j]
            else:
                a += m[i, j]
    return {"HOME": float(h), "DRAW": float(d), "AWAY": float(a)}


# --------------------------------------------------------------------
# Bahis kapısı
# --------------------------------------------------------------------
@dataclass
class LiveGate:
    budget: LatencyBudget = field(default_factory=LatencyBudget)
    monitor: LatencyMonitor = field(default_factory=LatencyMonitor)
    min_minutes_remaining: float = 8.0
    min_edge: float = 0.05          # canlıda eşik yüksek: gürültü çok
    blackout_after_event_s: float = 25.0

    _last_event_at: dt.datetime | None = None

    def note_event(self, when: dt.datetime | None = None) -> None:
        """Gol, kırmızı kart, penaltı — sonrasında kısa süre bahis kapalı."""
        self._last_event_at = when or dt.datetime.now(dt.timezone.utc)

    def check(self, state: LiveState, edge_pct: float,
              processing_ms: float, network_rtt_ms: float) -> LatencyVerdict:
        age = state.age_ms()
        self.monitor.record(age + processing_ms + network_rtt_ms)
        verdict = self.budget.evaluate(age, processing_ms, network_rtt_ms)

        extra = []
        if state.minutes_remaining < self.min_minutes_remaining:
            extra.append(f"{state.minutes_remaining:.0f} dk kaldı — model güvenilmez")
        if edge_pct < self.min_edge:
            extra.append(f"kenar %{edge_pct*100:.1f} < %{self.min_edge*100:.0f} eşiği")
        if self._last_event_at:
            since = (dt.datetime.now(dt.timezone.utc) - self._last_event_at).total_seconds()
            if since < self.blackout_after_event_s:
                extra.append(f"olay sonrası bekleme ({self.blackout_after_event_s - since:.0f} sn)")
        if self.monitor.is_degraded():
            extra.append(f"gecikme p95 {self.monitor.p95:.0f} ms")

        if extra:
            verdict.allowed = False
            verdict.reasons.extend(extra)
        return verdict
