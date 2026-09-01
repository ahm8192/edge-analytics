"""
Maç bağlamı (madde 29, 30, 34, 37, 38, 39, 40, 41, 44).

Bu etkenlerin tek tek etkisi küçüktür (%1-3). Birlikte ise gol beklentisini
%15'e kadar kaydırabilir ve kenar payı zaten %2-5 bandındadır.
"""
from __future__ import annotations
import datetime as dt
import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class ContextEffect:
    label: str
    value: str
    lambda_multiplier_home: float = 1.0
    lambda_multiplier_away: float = 1.0
    note: str | None = None

    @property
    def impact(self) -> float:
        """Toplam gol beklentisine net etki (UI'da gösterilir)."""
        return (self.lambda_multiplier_home + self.lambda_multiplier_away) / 2 - 1.0


# --- Dinlenme ve yoğunluk (madde 38, 39) ------------------------------
def rest_effect(rest_days_home: float, rest_days_away: float,
                matches_last_10d_home: int, matches_last_10d_away: int) -> ContextEffect:
    def penalty(rest: float, load: int) -> float:
        p = 1.0
        if rest < 3:
            p *= 1.0 - 0.045 * (3 - rest)      # 2 gün dinlenme ~%4.5 düşüş
        if load >= 3:
            p *= 1.0 - 0.03 * (load - 2)
        return float(np.clip(p, 0.82, 1.0))

    h = penalty(rest_days_home, matches_last_10d_home)
    a = penalty(rest_days_away, matches_last_10d_away)
    diff = rest_days_home - rest_days_away
    return ContextEffect(
        label="Dinlenme",
        value=f"{rest_days_home:.0f} - {rest_days_away:.0f} gün",
        lambda_multiplier_home=h, lambda_multiplier_away=a,
        note=("Ev sahibi belirgin daha dinlenmiş" if diff >= 2 else
              "Deplasman belirgin daha dinlenmiş" if diff <= -2 else None))


def travel_effect(distance_km: float, timezone_shift: int) -> ContextEffect:
    """madde 29, 44: uzun seyahat ve saat dilimi kayması deplasmanı yorar."""
    p = 1.0 - min(0.05, distance_km / 100_000) - 0.015 * abs(timezone_shift)
    return ContextEffect("Seyahat", f"{distance_km:.0f} km",
                         1.0, float(np.clip(p, 0.88, 1.0)),
                         f"{abs(timezone_shift)} saat dilimi farkı" if timezone_shift else None)


def international_break_effect(returning_players_home: int,
                               returning_players_away: int) -> ContextEffect:
    """madde 29: milli takımdan dönen oyuncu sayısı."""
    h = 1.0 - 0.008 * returning_players_home
    a = 1.0 - 0.008 * returning_players_away
    return ContextEffect("Milli ara dönüşü",
                         f"{returning_players_home} - {returning_players_away} oyuncu",
                         h, a)


# --- Hava, zemin, rakım (madde 40, 41, 42) -----------------------------
def weather_effect(wind_kph: float | None, precip_mm: float | None,
                   temp_c: float | None) -> ContextEffect:
    m = 1.0
    parts = []
    if wind_kph and wind_kph > 20:
        m *= 1.0 - 0.004 * (wind_kph - 20)
        parts.append(f"{wind_kph:.0f} km/s rüzgâr")
    if precip_mm and precip_mm > 1:
        m *= 1.0 - 0.010 * min(precip_mm, 10)
        parts.append(f"{precip_mm:.1f} mm yağış")
    if temp_c is not None and (temp_c > 30 or temp_c < 0):
        m *= 0.97
        parts.append(f"{temp_c:.0f}°C")
    m = float(np.clip(m, 0.85, 1.0))
    return ContextEffect("Hava", ", ".join(parts) or "normal", m, m)


def altitude_effect(altitude_m: float, away_home_altitude: float) -> ContextEffect:
    """madde 41: rakım farkı deplasmanı orantısız etkiler."""
    diff = altitude_m - away_home_altitude
    if diff < 800:
        return ContextEffect("Rakım", f"{altitude_m:.0f} m", 1.0, 1.0)
    penalty = 1.0 - min(0.12, 0.00006 * diff)
    return ContextEffect("Rakım", f"{altitude_m:.0f} m", 1.0, penalty,
                         f"Deplasman {diff:.0f} m daha yüksekte oynuyor")


def surface_effect(surface: str, away_usual_surface: str) -> ContextEffect:
    if surface == away_usual_surface:
        return ContextEffect("Zemin", surface, 1.0, 1.0)
    return ContextEffect("Zemin", surface, 1.0, 0.97,
                         "Deplasman alışık olmadığı zeminde")


# --- Seyirci ve motivasyon (madde 31, 32, 33, 34, 37) ------------------
def crowd_effect(crowd_status: str, base_home_adv: float) -> ContextEffect:
    factor = {"normal": 1.0, "restricted": 0.6, "closed": 0.25}.get(crowd_status, 1.0)
    return ContextEffect("Seyirci", crowd_status,
                         1.0 + (base_home_adv - 1.0) * factor, 1.0,
                         "Ev avantajı seyircisiz maçta belirgin düşer"
                         if factor < 1 else None)


def motivation_effect(home_stakes: float, away_stakes: float,
                      games_remaining: int) -> ContextEffect:
    """
    madde 33, 34: sezon sonunda hedefi biten takım ile küme hattındaki takım
    aynı motivasyonla oynamaz. stakes 0-1: 0 = hedefi bitmiş, 1 = kritik.
    Etki sadece sezonun son çeyreğinde devreye girer.
    """
    if games_remaining > 8:
        return ContextEffect("Motivasyon", "sezon ortası", 1.0, 1.0)
    intensity = np.clip((8 - games_remaining) / 8, 0, 1)
    h = 1.0 + 0.10 * intensity * (home_stakes - 0.5)
    a = 1.0 + 0.10 * intensity * (away_stakes - 0.5)
    gap = home_stakes - away_stakes
    return ContextEffect(
        "Motivasyon", f"{home_stakes:.0%} - {away_stakes:.0%}",
        float(h), float(a),
        "Ev sahibinin kaybedecek çok şeyi var" if gap > 0.4 else
        "Deplasmanın kaybedecek çok şeyi var" if gap < -0.4 else None)


def derby_effect(is_derby: bool) -> ContextEffect:
    """
    madde 37: derbide form istatistikleri zayıflar. Beklentiyi değiştirmiyoruz;
    BELİRSİZLİĞİ artırıyoruz — bu Kelly tutarını düşürür.
    """
    return ContextEffect("Derbi", "evet" if is_derby else "hayır", 1.0, 1.0,
                         "Form verisi derbide daha az açıklayıcı — güven düşürüldü"
                         if is_derby else None)


def two_leg_effect(leg: int | None, first_leg_margin: int | None) -> ContextEffect:
    """madde 36: rövanşta ilk maç sonucu oyunu belirler."""
    if leg != 2 or first_leg_margin is None:
        return ContextEffect("Eleme", "tek maç", 1.0, 1.0)
    if abs(first_leg_margin) >= 3:
        return ContextEffect("Eleme", f"ilk maç {first_leg_margin:+d}", 0.93, 0.93,
                             "Tur büyük ölçüde belli — tempo düşer")
    if first_leg_margin < 0:
        return ContextEffect("Eleme", f"ilk maç {first_leg_margin:+d}", 1.08, 0.98,
                             "Ev sahibi açığı kapatmak zorunda")
    return ContextEffect("Eleme", f"ilk maç {first_leg_margin:+d}", 1.0, 1.04)


# --- Toplama ----------------------------------------------------------
def apply_all(lambda_home: float, lambda_away: float,
              effects: list[ContextEffect]) -> tuple[float, float, list[dict]]:
    """
    Tüm etkileri çarpımsal uygular ve UI için döküm üretir (madde 100).
    Çarpımsal seçildi çünkü etkiler oransaldır ve toplamsalda negatife düşebilir.
    """
    lh, la = lambda_home, lambda_away
    breakdown = []
    for e in effects:
        before = (lh + la) / 2
        lh *= e.lambda_multiplier_home
        la *= e.lambda_multiplier_away
        after = (lh + la) / 2
        breakdown.append({
            "label": e.label, "value": e.value,
            "impact": (after / before - 1.0) if before > 0 else 0.0,
            "note": e.note,
        })
    return float(np.clip(lh, 0.05, 6.0)), float(np.clip(la, 0.05, 6.0)), breakdown


def confidence_penalty(effects: list[ContextEffect], is_derby: bool = False,
                       lineup_coverage: float = 1.0) -> float:
    """
    Bağlam ne kadar sıradışıysa modele o kadar az güvenilir.
    Bu sayı doğrudan Kelly tutarını ölçekler.
    """
    penalty = 1.0
    for e in effects:
        penalty *= 1.0 - min(0.15, abs(e.impact) * 0.5)
    if is_derby:
        penalty *= 0.85
    penalty *= 0.6 + 0.4 * lineup_coverage
    return float(np.clip(penalty, 0.25, 1.0))
