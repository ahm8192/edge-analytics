"""
Bayesçi hiyerarşik takım gücü (madde 62).

Neden gerekli: sezon başında bir takımın 4 maçı vardır. Maksimum olabilirlik
o 4 maça aşırı uyar ve saçma güçler üretir. Hiyerarşik model, takım gücünü
lig ortalamasına doğru "büzer" (shrinkage) ve veri arttıkça bırakır.

PyMC varsa tam Bayes, yoksa ampirik Bayes (kapalı form büzülme) kullanılır.
İkisi de aynı arayüzü döndürür.
"""
from __future__ import annotations
import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass

log = logging.getLogger(__name__)

try:
    import pymc as pm
    HAS_PYMC = True
except ImportError:                                  # pragma: no cover
    HAS_PYMC = False


@dataclass
class HierarchicalParams:
    attack: dict[str, float]
    defence: dict[str, float]
    attack_sd: dict[str, float]      # belirsizlik -> güven aralığı (madde 75)
    defence_sd: dict[str, float]
    home_adv: float
    league_mean_goals: float
    method: str

    def confidence(self, team: str) -> float:
        """Belirsizlik ne kadar büyükse güven o kadar düşük."""
        sd = (self.attack_sd.get(team, 0.5) + self.defence_sd.get(team, 0.5)) / 2
        return float(np.clip(1.0 - sd / 0.6, 0.15, 1.0))


def fit_empirical_bayes(df: pd.DataFrame, weights: np.ndarray | None = None,
                        prior_strength: float = 8.0) -> HierarchicalParams:
    """
    Ampirik Bayes büzülmesi. Hızlı, bağımlılıksız, pratikte çok işe yarar.

    prior_strength: kaç maçlık "sanal lig ortalaması" eklendiği.
    8 maç = takımın ilk 8 maçı ağırlıklı olarak lig ortalamasına yakın çıkar.
    """
    w = np.ones(len(df)) if weights is None else np.asarray(weights, float)
    teams = pd.unique(pd.concat([df.home_team, df.away_team]))

    league_home = float(np.average(df.home_goals, weights=w))
    league_away = float(np.average(df.away_goals, weights=w))
    league_mean = (league_home + league_away) / 2
    home_adv = float(np.log(max(league_home, 1e-6) / max(league_away, 1e-6)))

    attack, defence, a_sd, d_sd = {}, {}, {}, {}
    for t in teams:
        h = df.home_team == t
        a = df.away_team == t

        scored = np.concatenate([df.loc[h, "home_goals"], df.loc[a, "away_goals"]])
        conceded = np.concatenate([df.loc[h, "away_goals"], df.loc[a, "home_goals"]])
        ww = np.concatenate([w[h.to_numpy()], w[a.to_numpy()]])
        n = ww.sum()

        # Büzülme: gözlem az ise lig ortalamasına yakın
        shrink = n / (n + prior_strength)
        atk_raw = np.average(scored, weights=ww) if n > 0 else league_mean
        dfc_raw = np.average(conceded, weights=ww) if n > 0 else league_mean

        atk = shrink * atk_raw + (1 - shrink) * league_mean
        dfc = shrink * dfc_raw + (1 - shrink) * league_mean

        attack[t] = float(np.log(max(atk, 0.05) / league_mean))
        defence[t] = float(-np.log(max(dfc, 0.05) / league_mean))

        # Poisson varyansı ≈ ortalama; standart hata sqrt(lambda/n)
        a_sd[t] = float(np.sqrt(max(atk, 0.05) / max(n, 1)) / max(league_mean, 0.05))
        d_sd[t] = float(np.sqrt(max(dfc, 0.05) / max(n, 1)) / max(league_mean, 0.05))

    return HierarchicalParams(attack, defence, a_sd, d_sd, home_adv,
                              league_mean, "empirical_bayes")


def fit_full_bayes(df: pd.DataFrame, draws: int = 1000,
                   tune: int = 1000) -> HierarchicalParams:   # pragma: no cover
    """Tam Bayes. Yavaş (dakikalar) ama belirsizliği dürüstçe verir."""
    if not HAS_PYMC:
        log.warning("PyMC yok — ampirik Bayes'e düşülüyor")
        return fit_empirical_bayes(df)

    teams = pd.unique(pd.concat([df.home_team, df.away_team]))
    idx = {t: i for i, t in enumerate(teams)}
    h = df.home_team.map(idx).to_numpy()
    a = df.away_team.map(idx).to_numpy()
    n = len(teams)

    with pm.Model() as model:
        sd_att = pm.HalfNormal("sd_att", 0.3)
        sd_def = pm.HalfNormal("sd_def", 0.3)
        # Merkezlenmemiş parametreleme: örnekleyici için çok daha kararlı
        att_raw = pm.Normal("att_raw", 0, 1, shape=n)
        def_raw = pm.Normal("def_raw", 0, 1, shape=n)
        att = pm.Deterministic("att", att_raw * sd_att - (att_raw * sd_att).mean())
        dfc = pm.Deterministic("dfc", def_raw * sd_def - (def_raw * sd_def).mean())

        home_adv = pm.Normal("home_adv", 0.25, 0.15)
        intercept = pm.Normal("intercept", 0.1, 0.5)

        lam = pm.math.exp(intercept + home_adv + att[h] - dfc[a])
        mu = pm.math.exp(intercept + att[a] - dfc[h])

        pm.Poisson("hg", lam, observed=df.home_goals.to_numpy())
        pm.Poisson("ag", mu, observed=df.away_goals.to_numpy())

        trace = pm.sample(draws=draws, tune=tune, chains=2, progressbar=False,
                          target_accept=0.9)

    post = trace.posterior
    att_m = post["att"].mean(("chain", "draw")).values
    def_m = post["dfc"].mean(("chain", "draw")).values
    att_s = post["att"].std(("chain", "draw")).values
    def_s = post["dfc"].std(("chain", "draw")).values

    return HierarchicalParams(
        {t: float(att_m[i]) for t, i in idx.items()},
        {t: float(def_m[i]) for t, i in idx.items()},
        {t: float(att_s[i]) for t, i in idx.items()},
        {t: float(def_s[i]) for t, i in idx.items()},
        float(post["home_adv"].mean()),
        float(df[["home_goals", "away_goals"]].mean().mean()),
        "full_bayes")
