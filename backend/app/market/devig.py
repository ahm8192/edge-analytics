"""
Marj temizleme (madde 78, 79, 80).
Oranı 1/x yapıp toplamı 1'e bölmek EN KÖTÜ yöntemdir: marj eşit dağılmaz,
favoriye az, sürprize çok yüklenir. Shin veya power yöntemi kullan.
"""
from __future__ import annotations
import numpy as np
from scipy.optimize import brentq


def overround(prices: list[float]) -> float:
    return sum(1.0 / p for p in prices)


def margin_pct(prices: list[float]) -> float:
    return overround(prices) - 1.0


def devig_multiplicative(prices: list[float]) -> np.ndarray:
    """En basit. Referans olarak tut, üretimde kullanma."""
    raw = np.array([1.0 / p for p in prices])
    return raw / raw.sum()


def devig_power(prices: list[float]) -> np.ndarray:
    """
    p_i ∝ (1/o_i)^k, sum = 1 olacak şekilde k çözülür.
    Marjı favori-longshot eğrisine göre dağıtır (madde 80).
    """
    raw = np.array([1.0 / p for p in prices])
    if len(raw) < 2:
        return raw
    f = lambda k: np.sum(raw ** k) - 1.0
    try:
        k = brentq(f, 0.5, 3.0, xtol=1e-10)
    except ValueError:
        return devig_multiplicative(prices)
    out = raw ** k
    return out / out.sum()


def devig_shin(prices: list[float], max_iter: int = 200) -> np.ndarray:
    """
    Shin (1993): marjı 'bilgili bahisçi oranı' z ile modeller.
    Favori-longshot bias'ını teorik temelle düzeltir.
    """
    raw = np.array([1.0 / p for p in prices])
    s = raw.sum()
    if s <= 1.0:
        return raw / s
    z = 0.01
    for _ in range(max_iter):
        num = np.sqrt(z ** 2 + 4 * (1 - z) * raw ** 2 / s)
        p = (num - z) / (2 * (1 - z))
        p = p / p.sum()
        z_new = np.clip(((p * s - raw) / (p * (s - 1) + 1e-12)).mean(), 1e-6, 0.5)
        if abs(z_new - z) < 1e-10:
            break
        z = z_new
    return p


def fair_price(prob: float) -> float:
    return 1.0 / max(prob, 1e-9)


def implied_from_book(prices: dict[str, float], method: str = "shin") -> dict[str, float]:
    keys = list(prices)
    vals = [prices[k] for k in keys]
    fn = {"shin": devig_shin, "power": devig_power,
          "mult": devig_multiplicative}[method]
    return dict(zip(keys, map(float, fn(vals))))
