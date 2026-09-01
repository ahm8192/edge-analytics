"""
Kadro bazlı güç (madde 16-19, 23-26, 30).

Takım gücü diye bir şey aslında yoktur; sahaya çıkan 11 kişi vardır.
Aynı forma altında %30 farklı bir kadro çıkabilir.
"""
from __future__ import annotations
import datetime as dt
import numpy as np
import pandas as pd

from .leakage import SafeQuery, AsOfContext

# Pozisyona göre eksikliğin gol beklentisine etkisi (madde 17).
# Kaleci istisnai: hücuma katkısı yok ama savunmaya etkisi büyük.
POSITION_IMPACT = {
    "GK":  {"attack": 0.02, "defence": 0.34},
    "CB":  {"attack": 0.05, "defence": 0.22},
    "FB":  {"attack": 0.10, "defence": 0.14},
    "DM":  {"attack": 0.10, "defence": 0.20},
    "CM":  {"attack": 0.16, "defence": 0.14},
    "AM":  {"attack": 0.24, "defence": 0.06},
    "W":   {"attack": 0.24, "defence": 0.06},
    "ST":  {"attack": 0.30, "defence": 0.03},
}
DEFAULT_IMPACT = {"attack": 0.15, "defence": 0.12}

# Transfer adaptasyonu (madde 19): yeni oyuncu ilk haftalarda katkısının
# tamamını veremez. Eğri: 0 günde %55, ~90 günde tam.
ADAPTATION_FULL_DAYS = 90
ADAPTATION_FLOOR = 0.55


def adaptation_factor(days_at_club: float | None) -> float:
    if days_at_club is None or days_at_club >= ADAPTATION_FULL_DAYS:
        return 1.0
    t = max(0.0, days_at_club) / ADAPTATION_FULL_DAYS
    return ADAPTATION_FLOOR + (1 - ADAPTATION_FLOOR) * np.sqrt(t)


def availability_probability(news: pd.DataFrame, player_id: int,
                             kickoff: dt.datetime) -> float:
    """
    Haberlerden oynama olasılığı. En son haber kazanır ama güvenine göre
    yumuşatılır — "şüpheli" haberi kesin yokluk demek değildir.
    """
    rows = news[news["player_id"] == player_id]
    if rows.empty:
        return 1.0
    last = rows.sort_values("published_at").iloc[-1]
    kind = last["kind"]
    conf = float(last.get("confidence", 0.5))

    base = {"injury": 0.05, "suspension": 0.0, "doubt": 0.55, "return": 0.85}
    p = base.get(kind, 1.0)

    ret = last.get("expected_return")
    if kind == "injury" and ret:
        try:
            if pd.Timestamp(ret) <= pd.Timestamp(kickoff):
                p = 0.5   # dönüş tarihi geldi ama teyit yok
        except Exception:
            pass

    # Düşük güvenli haber, tam yokluk varsaymaz
    return float(np.clip(1.0 - conf * (1.0 - p), 0.0, 1.0))


def squad_strength(ratings: pd.DataFrame, expected_lineup: pd.DataFrame,
                   news: pd.DataFrame, kickoff: dt.datetime) -> dict:
    """
    Beklenen kadronun hücum/savunma toplam katkısı.

    expected_lineup: player_id, position, is_starter, days_at_club
    ratings:         player_id, off_contrib, def_contrib, minutes_sample, uncertainty
    """
    merged = expected_lineup.merge(ratings, on="player_id", how="left")

    off = 0.0
    dfc = 0.0
    missing_impact = {"attack": 0.0, "defence": 0.0}
    uncertainty = 0.0
    known = 0

    for _, r in merged.iterrows():
        pos = str(r.get("position") or "").upper()
        imp = POSITION_IMPACT.get(pos, DEFAULT_IMPACT)
        avail = availability_probability(news, int(r["player_id"]), kickoff)
        adapt = adaptation_factor(r.get("days_at_club"))

        o = r.get("off_contrib")
        d = r.get("def_contrib")
        if pd.isna(o) or pd.isna(d):
            # Derecesi olmayan oyuncu — pozisyon ortalaması varsayılır,
            # ama belirsizlik artar (madde 26, 53)
            uncertainty += 0.05
            continue

        known += 1
        weight = avail * adapt * (1.0 if r.get("is_starter", 1) else 0.35)
        off += float(o) * weight
        dfc += float(d) * weight

        if avail < 0.5:
            missing_impact["attack"] += imp["attack"] * (1 - avail)
            missing_impact["defence"] += imp["defence"] * (1 - avail)

        # Az dakikalı oyuncunun derecesi gürültülüdür (madde 26, 53)
        sample = float(r.get("minutes_sample") or 0)
        if sample < 900:
            uncertainty += 0.04 * (1 - sample / 900)

    coverage = known / max(len(merged), 1)
    return {
        "attack_total": off,
        "defence_total": dfc,
        "missing_attack_impact": missing_impact["attack"],
        "missing_defence_impact": missing_impact["defence"],
        "lineup_coverage": coverage,
        "uncertainty": float(np.clip(uncertainty, 0.0, 1.0)),
        "confidence": float(np.clip(coverage * (1 - uncertainty), 0.0, 1.0)),
    }


def squad_depth(ratings: pd.DataFrame, top_n: int = 11) -> float:
    """
    madde 23: yoğun fikstürde belirleyici olan ilk 11 değil, 12-18 arasıdır.
    12-18 ortalamasının ilk 11 ortalamasına oranı.
    """
    if len(ratings) < top_n + 4:
        return 0.5
    s = (ratings["off_contrib"].fillna(0) + ratings["def_contrib"].fillna(0)) \
        .sort_values(ascending=False)
    first = s.iloc[:top_n].mean()
    bench = s.iloc[top_n:top_n + 7].mean()
    return float(np.clip(bench / first, 0.0, 1.5)) if first > 0 else 0.5


def rotation_risk(days_to_next_match: float | None,
                  next_match_importance: float,
                  current_importance: float) -> float:
    """
    madde 30: sıradaki maç daha önemliyse ve arada 3 günden az varsa,
    bu maçta kadro düşer. 0-1 arası risk.
    """
    if days_to_next_match is None or days_to_next_match > 4:
        return 0.0
    gap = np.clip((4 - days_to_next_match) / 4, 0, 1)
    importance_gap = np.clip(next_match_importance - current_importance, 0, 1)
    return float(gap * importance_gap)


def suspension_risk(yellow_cards: int, threshold: int = 4) -> float:
    """madde 25: kart sınırındaki oyuncu bir sonraki maç için korunabilir."""
    if yellow_cards >= threshold - 1:
        return 0.35
    return 0.0
