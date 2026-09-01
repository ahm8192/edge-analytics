"""Zaman ağırlığı ve sezon süreksizliği (madde 11, 54, 52)."""
from __future__ import annotations
import datetime as dt
import numpy as np
import pandas as pd

# xi -> yarı ömür ilişkisi: half_life = ln(2) / xi
HALF_LIFE_PRESETS = {
    "fast": 0.0110,     # ~63 gün — hızlı değişen ligler, kadro oynaklığı yüksek
    "standard": 0.0045,  # ~154 gün — varsayılan
    "slow": 0.0025,     # ~277 gün — istikrarlı üst ligler
}


def half_life_days(xi: float) -> float:
    return float(np.log(2) / xi)


def exponential(days_ago: np.ndarray, xi: float = 0.0045) -> np.ndarray:
    return np.exp(-xi * np.asarray(days_ago, dtype=float))


def with_season_break(days_ago: np.ndarray, season_gaps: np.ndarray,
                      xi: float = 0.0045,
                      break_penalty: float = 0.75) -> np.ndarray:
    """
    madde 11: sezon arası takvim günü olarak yakın görünse de bilgi olarak
    uzaktır. Transfer, teknik direktör, hazırlık — takım aynı takım değildir.
    Aradan geçen her sezon arası ağırlığı ayrıca kırpar.
    """
    w = exponential(days_ago, xi)
    return w * (break_penalty ** np.asarray(season_gaps, dtype=float))


def effective_sample_size(weights: np.ndarray) -> float:
    """
    Ağırlıklı örneklemin "kaç maça denk" olduğu.
    500 maç var ama etkin 40 ise, model o kadar veriye sahip değildir.
    Kelly'yi ölçekleyen model_confidence bundan türer.
    """
    w = np.asarray(weights, dtype=float)
    if w.sum() == 0:
        return 0.0
    return float(w.sum() ** 2 / np.sum(w ** 2))


def confidence_from_ess(ess: float, target: float = 60.0) -> float:
    """
    Etkin örneklemi 0-1 arası güvene çevirir.
    60 maç civarı doygunluk; altı hızla düşer.
    """
    return float(np.clip(ess / target, 0.0, 1.0) ** 0.5)


def days_between(dates: pd.Series, reference: dt.datetime) -> np.ndarray:
    ts = pd.to_datetime(dates, utc=True, errors="coerce")
    ref = pd.Timestamp(reference, tz="UTC") if reference.tzinfo is None \
        else pd.Timestamp(reference)
    return ((ref - ts).dt.total_seconds() / 86400.0).to_numpy()
