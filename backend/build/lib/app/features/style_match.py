"""
Taktik stil eşleşmesi ve formasyon uyumu (madde 21, 22).

Temel fikir: takım gücü mutlak değil, göreceli. Yüksek pres yapan takım,
arkadan oyun kuran rakibe karşı istatistiğinin üstünde oynar; topu rakibe
bırakan bir takıma karşı ise presi boşa düşer.

Bu etkiler küçüktür (%2-6). Ama kenar payı zaten %2-5 bandında olduğu için
işaret değiştirecek kadar büyüktür.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass


# --------------------------------------------------------------------
# Stil profili
# --------------------------------------------------------------------
@dataclass
class StyleProfile:
    """
    Dört eksende normalize edilmiş stil (0-1).
    Ham metrikten değil, LİG İÇİNDE yüzdelik dilimden hesaplanır —
    Premier Lig'in "yavaş" takımı başka ligde hızlı olabilir.
    """
    press_intensity: float      # 1 = agresif pres (düşük PPDA)
    possession: float           # 1 = topa çok sahip
    directness: float           # 1 = uzun/dikey oyun
    field_position: float       # 1 = yüksek blok (field tilt)
    sample_matches: int = 0

    @property
    def confidence(self) -> float:
        """10 maçın altında stil profili gürültüdür."""
        return float(np.clip(self.sample_matches / 15.0, 0.0, 1.0))

    @property
    def archetype(self) -> str:
        """UI'da gösterilecek insan-okur etiket."""
        if self.press_intensity > 0.65 and self.possession > 0.6:
            return "yüksek pres + top hâkimiyeti"
        if self.press_intensity > 0.65:
            return "yüksek pres, dikey oyun"
        if self.possession > 0.65 and self.directness < 0.4:
            return "sabırlı top hâkimiyeti"
        if self.possession < 0.35 and self.directness > 0.6:
            return "alçak blok, kontratak"
        if self.field_position < 0.35:
            return "derin savunma"
        return "dengeli"


def build_profile(ppda: float, possession_pct: float,
                  pass_length_avg: float, field_tilt: float,
                  league_stats: dict, sample_matches: int) -> StyleProfile:
    """
    league_stats: her metrik için {'mean': x, 'std': y} — lig içi normalizasyon.
    PPDA ters çevrilir: düşük PPDA = yüksek pres.
    """
    def z(value: float, key: str, invert: bool = False) -> float:
        s = league_stats.get(key, {"mean": value, "std": 1.0})
        sd = max(s.get("std", 1.0), 1e-6)
        score = (value - s["mean"]) / sd
        if invert:
            score = -score
        return float(np.clip(0.5 + score / 4.0, 0.0, 1.0))   # ±2σ -> 0-1

    return StyleProfile(
        press_intensity=z(ppda, "ppda", invert=True),
        possession=z(possession_pct, "possession"),
        directness=z(pass_length_avg, "pass_length"),
        field_position=z(field_tilt, "field_tilt"),
        sample_matches=sample_matches,
    )


# --------------------------------------------------------------------
# Eşleşme etkileri (madde 21)
# --------------------------------------------------------------------
@dataclass
class StyleMatchup:
    home_multiplier: float
    away_multiplier: float
    label: str
    explanation: str
    confidence: float

    @property
    def impact(self) -> float:
        return (self.home_multiplier + self.away_multiplier) / 2 - 1.0


# Etki katsayıları. Küçük tutuldu; taktik eşleşme gerçek ama abartılan bir etkendir.
PRESS_VS_BUILDUP = 0.055      # pres yapan, arkadan kuran rakibe karşı kazanır
PRESS_VS_DIRECT = -0.035      # pres, uzun top oynayan rakibe karşı boşa düşer
LOWBLOCK_VS_POSSESSION = 0.030  # alçak blok, sabırlı rakibi yavaşlatır
PACE_SUM_EFFECT = 0.045       # iki takım da hızlıysa toplam gol artar


def evaluate(home: StyleProfile, away: StyleProfile) -> list[StyleMatchup]:
    """Her eşleşme boyutu ayrı bir etki üretir; hepsi çarpımsal birleşir."""
    out: list[StyleMatchup] = []
    conf = min(home.confidence, away.confidence)

    # 1) Pres, oyun kurma tarzıyla karşılaşınca
    for attacker, defender, side in ((home, away, "home"), (away, home, "away")):
        buildup = defender.possession * (1 - defender.directness)
        gain = attacker.press_intensity * buildup * PRESS_VS_BUILDUP
        loss = attacker.press_intensity * defender.directness * PRESS_VS_DIRECT
        net = (gain + loss) * conf
        if abs(net) < 0.008:
            continue
        h = 1 + net if side == "home" else 1.0
        a = 1 + net if side == "away" else 1.0
        out.append(StyleMatchup(
            h, a,
            "Pres eşleşmesi",
            ("Presi rakibin oyun kurma tarzına iyi oturuyor" if net > 0
             else "Rakip uzun toplarla presi atlıyor"),
            conf))

    # 2) Alçak blok, topa sahip rakibe karşı
    for defender, attacker, side in ((home, away, "away"), (away, home, "home")):
        if defender.field_position < 0.4 and attacker.possession > 0.6:
            net = (0.4 - defender.field_position) * attacker.possession \
                  * LOWBLOCK_VS_POSSESSION * conf
            h = 1 - net if side == "home" else 1.0
            a = 1 - net if side == "away" else 1.0
            out.append(StyleMatchup(
                h, a, "Alçak blok",
                "Rakip derin savunuyor — alan bulmak zorlaşacak", conf))

    # 3) Tempo toplamı: iki takım da dikey oynuyorsa maç açılır
    pace = (home.directness + away.directness) / 2
    if pace > 0.6 or pace < 0.35:
        net = (pace - 0.5) * PACE_SUM_EFFECT * 2 * conf
        out.append(StyleMatchup(
            1 + net, 1 + net, "Tempo",
            "İki takım da dikey oynuyor — maç açık geçer" if net > 0
            else "İki takım da kontrollü — maç kapalı geçer", conf))

    return out


# --------------------------------------------------------------------
# Formasyon uyumu (madde 22)
# --------------------------------------------------------------------
# Sayısal üstünlük matrisi. Değerler küçük ve simetrik olmayan biçimde kurulmuş;
# futbolda "taş-kağıt-makas" ilişkisi zayıf ama sıfır değil.
FORMATION_EDGE = {
    # (hücum eden, savunan): hücum çarpanı
    ("3-5-2", "4-4-2"): 0.030,   # kanat sayısı üstünlüğü
    ("3-4-3", "4-2-3-1"): 0.025,
    ("4-3-3", "3-5-2"): 0.030,   # kanat forvet, stoperi dışarı çeker
    ("4-2-3-1", "4-4-2"): 0.020,  # orta saha 3'e 2
    ("4-4-2", "4-3-3"): -0.025,
    ("5-3-2", "4-3-3"): -0.015,
    ("4-3-3", "5-4-1"): -0.020,  # kalabalık savunmayı açmak zor
}

# Stoper sayısı ile forvet sayısı eşleşmesi
BACKLINE = {"3-5-2": 3, "3-4-3": 3, "5-3-2": 5, "5-4-1": 5,
            "4-4-2": 4, "4-3-3": 4, "4-2-3-1": 4, "4-1-4-1": 4}
FORWARDS = {"3-5-2": 2, "3-4-3": 3, "5-3-2": 2, "5-4-1": 1,
            "4-4-2": 2, "4-3-3": 3, "4-2-3-1": 1, "4-1-4-1": 1}


def formation_matchup(home_formation: str, away_formation: str,
                      confidence: float = 0.7) -> StyleMatchup | None:
    """
    Formasyon verisi genelde tahminidir (beklenen 11'den türetilir).
    Bu yüzden güven çarpanı düşük tutulur ve etki küçüktür.
    """
    h = FORMATION_EDGE.get((home_formation, away_formation), 0.0)
    a = FORMATION_EDGE.get((away_formation, home_formation), 0.0)

    # Sayısal eşleşme: 3 stoperli takım tek forvete karşı adam fazlası savunur
    hb, af = BACKLINE.get(home_formation, 4), FORWARDS.get(away_formation, 2)
    ab, hf = BACKLINE.get(away_formation, 4), FORWARDS.get(home_formation, 2)
    if hb - af >= 2:
        a -= 0.020          # deplasman hücumu boğuluyor
    if ab - hf >= 2:
        h -= 0.020

    if abs(h) < 0.008 and abs(a) < 0.008:
        return None

    return StyleMatchup(
        1 + h * confidence, 1 + a * confidence,
        "Formasyon",
        f"{home_formation} - {away_formation}",
        confidence)


def to_context_effects(matchups: list[StyleMatchup]) -> list:
    """features/context.py'nin beklediği ContextEffect formatına çevirir."""
    from .context import ContextEffect
    return [ContextEffect(m.label, m.explanation,
                          m.home_multiplier, m.away_multiplier, None)
            for m in matchups]
