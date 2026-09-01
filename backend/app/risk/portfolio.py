"""
Segment bazlı performans (madde 95, 99).

Toplam ROI yanıltıcıdır: bir markette kazanıp diğerinde kaybeden sistem
"başabaş" görünür ve iki gerçek birden gizlenir.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass

MIN_SEGMENT_N = 25


@dataclass
class SegmentReport:
    segment: str
    n: int
    staked: float
    pnl: float
    roi: float
    mean_clv: float | None
    clv_stderr: float | None

    @property
    def is_conclusive(self) -> bool:
        """Bu segment hakkında karar verilebilir mi?"""
        return self.n >= MIN_SEGMENT_N

    @property
    def verdict(self) -> str:
        if not self.is_conclusive:
            return f"Karar için yetersiz ({self.n}/{MIN_SEGMENT_N} bahis)"
        if self.mean_clv is None:
            return "Kapanış oranı verisi eksik"
        if self.clv_stderr and self.mean_clv > 2 * self.clv_stderr:
            return "Bu segmentte piyasayı yeniyorsun"
        if self.mean_clv < 0:
            return "Bu segmentte piyasanın altındasın — durdurmayı düşün"
        return "Pozitif ama henüz anlamlı değil"


def by_segment(bets: pd.DataFrame, key: str) -> list[SegmentReport]:
    """
    bets: n, stake, pnl, taken_price, closing_price + segment kolonu
    key: 'market' | 'league_id' | 'price_bucket' | 'edge_bucket'
    """
    out = []
    for seg, g in bets.groupby(key):
        staked = g.stake.sum()
        pnl = g.pnl.fillna(0).sum()
        with_close = g[g.closing_price.notna()]
        clv = (with_close.taken_price / with_close.closing_price - 1.0) \
            if len(with_close) else pd.Series(dtype=float)

        out.append(SegmentReport(
            segment=str(seg), n=len(g), staked=float(staked), pnl=float(pnl),
            roi=float(pnl / staked) if staked > 0 else 0.0,
            mean_clv=float(clv.mean()) if len(clv) else None,
            clv_stderr=float(clv.std(ddof=1) / np.sqrt(len(clv)))
            if len(clv) > 1 else None,
        ))
    return sorted(out, key=lambda r: -r.n)


def price_bucket(price: float) -> str:
    """Oran aralığı bazında ölçüm — favori ve sürpriz farklı davranır (madde 80)."""
    if price < 1.6:
        return "1.00-1.60 (ağır favori)"
    if price < 2.5:
        return "1.60-2.50"
    if price < 4.0:
        return "2.50-4.00"
    if price < 8.0:
        return "4.00-8.00"
    return "8.00+ (sürpriz)"


def edge_bucket(edge_pct: float) -> str:
    if edge_pct < 0.02:
        return "%0-2 (oynanmamalı)"
    if edge_pct < 0.05:
        return "%2-5"
    if edge_pct < 0.10:
        return "%5-10"
    return "%10+ (şüpheli — model hatası olabilir)"


def leak_detector(reports: list[SegmentReport]) -> list[str]:
    """
    Sistemin nerede para kaybettiğini söyler.
    Genelde tek bir segment tüm kârı yer.
    """
    warnings = []
    for r in reports:
        if not r.is_conclusive:
            continue
        if r.mean_clv is not None and r.mean_clv < -0.01:
            warnings.append(
                f"{r.segment}: ortalama CLV %{r.mean_clv*100:.1f} — "
                f"{r.n} bahiste piyasanın gerisinde. Bu segmenti kapat.")
        if r.roi < -0.15 and r.n >= 40:
            warnings.append(
                f"{r.segment}: %{r.roi*100:.0f} getiri, {r.n} bahis. "
                f"Şansla açıklanamayacak kadar kötü.")
    return warnings
