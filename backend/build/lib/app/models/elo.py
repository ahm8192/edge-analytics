"""Elo/Glicko benzeri temel derecelendirme (madde 63, 64). Basit ama sağlam baseline."""
from __future__ import annotations
import math
from dataclasses import dataclass, field


@dataclass
class EloConfig:
    k_base: float = 20.0
    home_adv: float = 60.0          # Elo puanı cinsinden
    goal_diff_boost: bool = True    # farklı galibiyet daha çok puan
    initial: float = 1500.0
    regress_to_mean: float = 0.25   # sezon başı ortalamaya çekme (madde 52)


class EloRatings:
    def __init__(self, cfg: EloConfig = EloConfig()):
        self.cfg = cfg
        self.r: dict[str, float] = {}

    def get(self, team: str) -> float:
        return self.r.setdefault(team, self.cfg.initial)

    def expected_home(self, home: str, away: str) -> float:
        d = self.get(home) + self.cfg.home_adv - self.get(away)
        return 1.0 / (1.0 + 10 ** (-d / 400.0))

    def update(self, home: str, away: str, hg: int, ag: int) -> None:
        exp_h = self.expected_home(home, away)
        actual = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        k = self.cfg.k_base
        if self.cfg.goal_diff_boost:
            gd = abs(hg - ag)
            k *= math.sqrt(max(1, gd)) if gd > 1 else 1.0
        delta = k * (actual - exp_h)
        self.r[home] = self.get(home) + delta
        self.r[away] = self.get(away) - delta

    def new_season(self) -> None:
        """Sezon başında ortalamaya çekme (madde 52: regression to the mean)."""
        if not self.r:
            return
        mean = sum(self.r.values()) / len(self.r)
        a = self.cfg.regress_to_mean
        self.r = {t: v * (1 - a) + mean * a for t, v in self.r.items()}
