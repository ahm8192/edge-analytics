"""
Stake yönetimi (madde 89, 90, 92, 93).
Tam Kelly matematiksel olarak optimaldir ama model hatasına aşırı duyarlıdır.
Model %2 yanılırsa tam Kelly seni batırır. Çeyrek Kelly standarttır.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class StakeConfig:
    fraction: float = 0.25        # çeyrek Kelly
    max_pct_bankroll: float = 0.02   # tek maça en fazla %2 (madde 90)
    min_stake: float = 10.0
    round_to: float = 5.0
    max_open_exposure: float = 0.15  # aynı anda açık toplam risk


def kelly_fraction(prob: float, price: float) -> float:
    """f* = (bp - q) / b ; b = price - 1"""
    b = price - 1.0
    if b <= 0:
        return 0.0
    f = (prob * b - (1.0 - prob)) / b
    return max(0.0, f)


def stake(prob: float, price: float, bankroll: float,
          cfg: StakeConfig = StakeConfig(),
          open_exposure: float = 0.0,
          model_confidence: float = 1.0) -> dict:
    f_full = kelly_fraction(prob, price)
    f = f_full * cfg.fraction * model_confidence   # güven düşükse stake düşer

    capped_by = None
    if f > cfg.max_pct_bankroll:
        f, capped_by = cfg.max_pct_bankroll, "max_pct_bankroll"

    room = cfg.max_open_exposure - open_exposure
    if f > room:
        f, capped_by = max(0.0, room), "max_open_exposure"

    amount = bankroll * f
    if amount < cfg.min_stake:
        return {"stake": 0.0, "kelly_full": f_full, "kelly_used": f,
                "skipped": True, "reason": "min_stake_altinda"}

    amount = round(amount / cfg.round_to) * cfg.round_to
    return {"stake": float(amount), "kelly_full": f_full, "kelly_used": f,
            "pct_bankroll": amount / bankroll, "capped_by": capped_by,
            "skipped": False}


def martingale_guard(recent_results: list[str], proposed: float,
                     avg_stake: float) -> str | None:
    """
    madde 93: kayıp sonrası stake artırma tespiti.
    Kullanıcı manuel stake giriyorsa uyarı üretir.
    """
    if len(recent_results) < 2:
        return None
    losing_streak = 0
    for r in reversed(recent_results):
        if r == "lose":
            losing_streak += 1
        else:
            break
    if losing_streak >= 2 and proposed > avg_stake * 1.5:
        return (f"{losing_streak} maçlık kayıp serisinden sonra stake'i "
                f"artırıyorsun. Bu martingale davranışıdır ve bankroll'u sıfırlar.")
    return None
