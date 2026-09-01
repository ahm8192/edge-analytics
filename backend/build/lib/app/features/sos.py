"""
Rakip gücü düzeltmesi (madde 55) ve ligler arası ölçek (madde 57).

Ham istatistik yanıltıcıdır: küme hattıyla oynayıp 2.1 xG üreten takım ile
şampiyonluk yarışıyla oynayıp 1.6 üreten takım, ikincisi daha iyidir.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def opponent_adjusted(values: np.ndarray, opponent_strength: np.ndarray,
                      league_mean: float | None = None) -> np.ndarray:
    """
    Basit çarpımsal düzeltme: değer / rakibin göreli gücü.
    opponent_strength 1.0 = lig ortalaması rakip.
    """
    s = np.clip(np.asarray(opponent_strength, float), 0.3, 3.0)
    adj = np.asarray(values, float) / s
    if league_mean is not None and league_mean > 0:
        adj = adj / league_mean
    return adj


def iterative_ratings(df: pd.DataFrame, value_col: str,
                      team_col: str = "team_id", opp_col: str = "opponent_id",
                      weight_col: str | None = None,
                      iterations: int = 25) -> pd.Series:
    """
    Rakip gücünü ve takım gücünü aynı anda çözer (basit alternating least squares).
    "Kimin karşısında ürettin" ile "sen ne kadar iyisin" birbirine bağlıdır;
    tek geçişte çözülmez, yakınsatmak gerekir.
    """
    teams = pd.unique(pd.concat([df[team_col], df[opp_col]]))
    strength = pd.Series(1.0, index=teams, dtype=float)
    w = df[weight_col].to_numpy() if weight_col else np.ones(len(df))

    for _ in range(iterations):
        adjusted = df[value_col].to_numpy() / strength[df[opp_col]].to_numpy()
        new = (pd.DataFrame({"t": df[team_col], "v": adjusted * w, "w": w})
               .groupby("t").apply(lambda g: g["v"].sum() / max(g["w"].sum(), 1e-9)))
        new = new / new.mean()
        if np.allclose(new.reindex(strength.index).fillna(1.0), strength, atol=1e-6):
            strength = new.reindex(strength.index).fillna(1.0)
            break
        strength = new.reindex(strength.index).fillna(1.0)

    return strength


def league_scale(league_coefs: dict[int, float], from_league: int,
                 to_league: int) -> float:
    """
    Ligler arası taşıma katsayısı (madde 57).
    2. ligden çıkan takımın istatistiği 1. lige olduğu gibi taşınamaz.
    """
    a = league_coefs.get(from_league, 1.0)
    b = league_coefs.get(to_league, 1.0)
    return float(a / b) if b > 0 else 1.0
