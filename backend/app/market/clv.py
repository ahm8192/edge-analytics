"""
Closing Line Value (madde 76, 77) — asıl başarı ölçütün.
Kâr şansa bağlıdır; CLV değildir. 200 bahiste pozitif CLV varsa sistem çalışıyordur.
"""
from __future__ import annotations
import numpy as np
from .devig import implied_from_book


def clv_pct(taken_price: float, closing_price: float) -> float:
    """Alınan oran kapanıştan yüksekse pozitif."""
    return taken_price / closing_price - 1.0


def clv_prob(taken_price: float, closing_prices: dict[str, float],
             selection: str) -> float:
    """Marj temizlenmiş olasılık farkı — fiyat oranından daha dürüst ölçü."""
    fair = implied_from_book(closing_prices, method="shin")
    return (1.0 / taken_price) - fair.get(selection, 0.0)


def clv_summary(records: list[dict]) -> dict:
    """records: [{taken_price, closing_price, stake, pnl}]"""
    if not records:
        return {"n": 0}
    c = np.array([clv_pct(r["taken_price"], r["closing_price"]) for r in records])
    beat = float((c > 0).mean())
    stake = np.array([r["stake"] for r in records], float)
    pnl = np.array([r.get("pnl", 0.0) for r in records], float)
    return {
        "n": len(records),
        "mean_clv": float(c.mean()),
        "median_clv": float(np.median(c)),
        "beat_close_rate": beat,
        "roi": float(pnl.sum() / stake.sum()) if stake.sum() else 0.0,
        # madde 99: kaç bahiste anlamlı sonuç? std/sqrt(n) ile
        "clv_stderr": float(c.std(ddof=1) / np.sqrt(len(c))) if len(c) > 1 else None,
        "is_significant": bool(len(c) > 30 and
                               c.mean() > 2 * c.std(ddof=1) / np.sqrt(len(c))),
    }
