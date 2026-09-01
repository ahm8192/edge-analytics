"""
Aşırı yayılım (overdispersion) düzeltmesi (madde 60).

Poisson varsayımı: varyans = ortalama. Futbolda varyans genelde biraz DAHA
BÜYÜKTÜR (kırmızı kart, taktik çöküş, 5-0'lar). Bu, alt/üst marketlerinde
sistematik hataya yol açar: Poisson yüksek skorları eksik tahmin eder.
"""
from __future__ import annotations
import numpy as np
from scipy.stats import nbinom, poisson
from scipy.optimize import minimize_scalar


def dispersion_ratio(counts: np.ndarray) -> float:
    """>1 ise aşırı yayılım var. Futbolda tipik 1.05-1.20."""
    c = np.asarray(counts, float)
    m = c.mean()
    return float(c.var(ddof=1) / m) if m > 0 else 1.0


def fit_dispersion(counts: np.ndarray) -> float:
    """Negatif binom 'size' parametresini olabilirlikle bulur."""
    c = np.asarray(counts, float)
    mean = c.mean()
    if mean <= 0:
        return 1e6

    def nll(log_r: float) -> float:
        r = np.exp(log_r)
        p = r / (r + mean)
        return -np.sum(nbinom.logpmf(c, r, p))

    res = minimize_scalar(nll, bounds=(-2, 8), method="bounded")
    return float(np.exp(res.x))


def pmf(k: np.ndarray, mean: float, size: float | None) -> np.ndarray:
    """size None veya çok büyükse Poisson'a döner (aynı şeydir)."""
    if size is None or size > 500:
        return poisson.pmf(k, mean)
    p = size / (size + mean)
    return nbinom.pmf(k, size, p)


def score_matrix(lam: float, mu: float, rho: float, size: float | None,
                 max_goals: int = 12) -> np.ndarray:
    """Dixon-Coles tau düzeltmesi negatif binom üzerinde de uygulanır."""
    from .dixon_coles import tau
    ks = np.arange(max_goals + 1)
    h = pmf(ks, lam, size)
    a = pmf(ks, mu, size)
    m = np.outer(h, a)
    for x in range(2):
        for y in range(2):
            m[x, y] *= tau(x, y, lam, mu, rho)
    return m / m.sum()
