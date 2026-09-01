"""Kombine kuponlarda korelasyon uyarısı (madde 86, 87)."""
from __future__ import annotations
import numpy as np
from itertools import product

# Aynı maç içinde bilinen korelasyonlar
SAME_MATCH_CORR = {
    ("1X2:HOME", "OU2.5:OVER"): 0.15,
    ("1X2:HOME", "BTTS:YES"): -0.05,
    ("OU2.5:OVER", "BTTS:YES"): 0.62,
    ("1X2:DRAW", "OU2.5:UNDER"): 0.41,
}


def naive_parlay_prob(probs: list[float]) -> float:
    return float(np.prod(probs))


def parlay_from_matrix(matrices: list[np.ndarray],
                       conditions: list) -> float:
    """
    Aynı maçtan iki seçim varsa skor matrisinden ORTAK olasılığı hesapla.
    conditions: her biri (i,j) -> bool döndüren fonksiyon listesi.
    """
    total = 0.0
    m = matrices[0]
    n = m.shape[0]
    for i, j in product(range(n), range(n)):
        if all(c(i, j) for c in conditions):
            total += m[i, j]
    return float(total)


def parlay_warning(legs: list[dict]) -> dict:
    """legs: [{match_id, market, selection, prob, price}]"""
    by_match: dict = {}
    for l in legs:
        by_match.setdefault(l["match_id"], []).append(l)

    same_match = {k: v for k, v in by_match.items() if len(v) > 1}
    naive = naive_parlay_prob([l["prob"] for l in legs])
    combined_price = float(np.prod([l["price"] for l in legs]))

    # Her ayak bahisçi marjı taşır: n ayak = marj n kez uygulanır (madde 86)
    est_margin = 1.0 - naive * combined_price
    return {
        "naive_prob": naive,
        "combined_price": combined_price,
        "estimated_ev": naive * combined_price - 1.0,
        "stacked_margin_pct": est_margin,
        "correlated_legs": {str(k): len(v) for k, v in same_match.items()},
        "warning": ("Aynı maçtan birden fazla seçim var — bağımsız çarpım YANLIŞ. "
                    "Ortak olasılık skor matrisinden hesaplanmalı."
                    if same_match else
                    "Her ek ayak marjı katlar; tekli bahis matematiksel olarak üstündür."),
    }
