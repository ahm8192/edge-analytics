"""Değer tespiti (madde 76, 81, 84, 88)."""
from __future__ import annotations
from dataclasses import dataclass
from .devig import implied_from_book, fair_price


@dataclass
class EdgeResult:
    selection: str
    model_prob: float
    market_prob: float
    taken_price: float
    fair_price: float
    edge_pct: float          # (model_prob * price) - 1  => beklenen getiri
    prob_gap: float          # model - piyasa
    is_value: bool
    confidence: str          # low | medium | high


MIN_EDGE = 0.02              # %2 altı gürültüdür, oynama


def compute_edge(model_probs: dict[str, float], book_prices: dict[str, float],
                 best_prices: dict[str, float] | None = None,
                 min_edge: float = MIN_EDGE,
                 sample_confidence: float = 1.0) -> list[EdgeResult]:
    """
    book_prices : referans (keskin) kitabın oranları -> piyasa olasılığı buradan
    best_prices : oynanacak en iyi oran (madde 84). Yoksa book_prices kullanılır.
    """
    market = implied_from_book(book_prices, method="shin")
    take = best_prices or book_prices
    out = []
    for sel, mp in model_probs.items():
        if sel not in take:
            continue
        price = take[sel]
        ev = mp * price - 1.0
        gap = mp - market.get(sel, 0.0)
        conf = "high" if sample_confidence > 0.8 and ev > 0.05 else \
               "medium" if sample_confidence > 0.5 and ev > min_edge else "low"
        out.append(EdgeResult(
            selection=sel, model_prob=mp, market_prob=market.get(sel, 0.0),
            taken_price=price, fair_price=fair_price(mp),
            edge_pct=ev, prob_gap=gap,
            is_value=ev >= min_edge and conf != "low", confidence=conf))
    return sorted(out, key=lambda r: -r.edge_pct)
