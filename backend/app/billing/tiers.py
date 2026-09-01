"""
Özellik matrisi: 100 maddelik kontrol listesinin hangi maddesi hangi katmanda.

Tasarım ilkesi: ücretsiz katman GERÇEKTEN işe yaramalı.
Kırık bir ürünün kilidini satmıyoruz; çalışan bir üründe derinlik satıyoruz.
Ücretsiz kullanıcı doğru kalibre edilmiş olasılık görür.
Abone, o olasılığı PARAYA çeviren katmanı görür: edge, CLV, stake, denetim.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class Tier(str, Enum):
    FREE = "FREE"
    PRO = "PRO"
    ELITE = "ELITE"

    @property
    def rank(self) -> int:
        return {"FREE": 0, "PRO": 1, "ELITE": 2}[self.value]

    def covers(self, required: "Tier") -> bool:
        return self.rank >= required.rank


class Feature(str, Enum):
    # --- Ücretsiz çekirdek ---------------------------------------------
    BASIC_1X2 = "basic_1x2"                    # md 59,61 Dixon-Coles 1X2
    BASIC_FORM = "basic_form"                  # md 53,54 son maçlar + decay
    SINGLE_BOOK_DEVIG = "single_book_devig"    # md 78 tek kitap marj temizleme
    MATCH_LIST = "match_list"

    # --- PRO -------------------------------------------------------------
    ALL_MARKETS = "all_markets"                # md 46 O/U, AH, BTTS, korner
    ENSEMBLE_MODEL = "ensemble_model"          # md 67 model birleşimi
    CALIBRATED_PROB = "calibrated_prob"        # md 71 isotonic/Platt kalibrasyon
    EDGE_DETECTION = "edge_detection"          # md 81 model > piyasa filtresi
    KELLY_STAKE = "kelly_stake"                # md 89,90 çeyrek Kelly
    BANKROLL_MANAGER = "bankroll_manager"      # md 90,92,93
    BET_LOG = "bet_log"                        # md 94,98 her tahmini kaydet
    CLV_TRACKING = "clv_tracking"              # md 77 asıl başarı ölçütü
    ODDS_MOVEMENT = "odds_movement"            # md 7,83 açılış->kapanış eğrisi
    SQUAD_ADJUSTMENT = "squad_adjustment"      # md 16,17,18 kadro bazlı güç
    INJURY_IMPACT = "injury_impact"            # md 8,17
    CONTEXT_ADJUST = "context_adjust"          # md 31-45 hakem/hava/rakım/fikstür
    VALUE_ALERTS = "value_alerts"              # push bildirim
    NO_ADS = "no_ads"

    # --- ELITE -----------------------------------------------------------
    MULTI_BOOK_COMPARE = "multi_book_compare"  # md 84 en iyi oran avı
    SHARP_MOVE_SIGNAL = "sharp_move_signal"    # md 83 keskin para hareketi
    MODEL_EXPLAIN = "model_explain"            # md 100 SHAP / katkı dökümü
    MONTE_CARLO = "monte_carlo"                # md 91 drawdown simülasyonu
    BACKTEST_LAB = "backtest_lab"              # md 68,69 walk-forward laboratuvar
    CORRELATION_CHECK = "correlation_check"    # md 87 kombine korelasyon uyarısı
    PORTFOLIO_BREAKDOWN = "portfolio_breakdown"# md 95 lig/market bazında performans
    DATA_EXPORT = "data_export"                # CSV / API
    CUSTOM_MODEL_WEIGHTS = "custom_weights"    # kendi ensemble ağırlığın


FEATURE_TIER: dict[Feature, Tier] = {
    Feature.BASIC_1X2: Tier.FREE,
    Feature.BASIC_FORM: Tier.FREE,
    Feature.SINGLE_BOOK_DEVIG: Tier.FREE,
    Feature.MATCH_LIST: Tier.FREE,

    Feature.ALL_MARKETS: Tier.PRO,
    Feature.ENSEMBLE_MODEL: Tier.PRO,
    Feature.CALIBRATED_PROB: Tier.PRO,
    Feature.EDGE_DETECTION: Tier.PRO,
    Feature.KELLY_STAKE: Tier.PRO,
    Feature.BANKROLL_MANAGER: Tier.PRO,
    Feature.BET_LOG: Tier.PRO,
    Feature.CLV_TRACKING: Tier.PRO,
    Feature.ODDS_MOVEMENT: Tier.PRO,
    Feature.SQUAD_ADJUSTMENT: Tier.PRO,
    Feature.INJURY_IMPACT: Tier.PRO,
    Feature.CONTEXT_ADJUST: Tier.PRO,
    Feature.VALUE_ALERTS: Tier.PRO,
    Feature.NO_ADS: Tier.PRO,

    Feature.MULTI_BOOK_COMPARE: Tier.ELITE,
    Feature.SHARP_MOVE_SIGNAL: Tier.ELITE,
    Feature.MODEL_EXPLAIN: Tier.ELITE,
    Feature.MONTE_CARLO: Tier.ELITE,
    Feature.BACKTEST_LAB: Tier.ELITE,
    Feature.CORRELATION_CHECK: Tier.ELITE,
    Feature.PORTFOLIO_BREAKDOWN: Tier.ELITE,
    Feature.DATA_EXPORT: Tier.ELITE,
    Feature.CUSTOM_MODEL_WEIGHTS: Tier.ELITE,
}


@dataclass(frozen=True)
class Quota:
    key: str
    limit: int          # -1 = sınırsız
    window_hours: int


QUOTAS: dict[Tier, tuple[Quota, ...]] = {
    Tier.FREE:  (Quota("match_analysis", 3, 24),
                 Quota("odds_refresh", 10, 24)),
    Tier.PRO:   (Quota("match_analysis", -1, 24),
                 Quota("odds_refresh", 300, 24)),
    Tier.ELITE: (Quota("match_analysis", -1, 24),
                 Quota("odds_refresh", -1, 24)),
}


def allows(tier: Tier, feature: Feature) -> bool:
    return tier.covers(FEATURE_TIER[feature])


def quota_for(tier: Tier, key: str) -> int:
    for q in QUOTAS[tier]:
        if q.key == key:
            return q.limit
    return 0


def feature_flags(tier: Tier) -> dict[str, bool]:
    """İstemciye gönderilen düz bayrak sözlüğü."""
    return {f.value: allows(tier, f) for f in Feature}
