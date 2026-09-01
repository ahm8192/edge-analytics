"""
Dixon-Coles gol modeli (madde 59, 61, 54, 55).

Poisson'un düşük skorlarda (0-0, 1-0, 0-1, 1-1) yaptığı hatayı tau
düzeltmesi ile kapatır. Zaman ağırlığı (decay) eski maçların etkisini azaltır.
Ev/deplasman hücum ve savunma gücü AYRI parametrelenir.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson

MAX_GOALS = 12


def tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    """Düşük skor korelasyon düzeltmesi."""
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def tau_vec(x: np.ndarray, y: np.ndarray, lam: np.ndarray,
            mu: np.ndarray, rho: float) -> np.ndarray:
    """
    tau'nun vektörleştirilmiş hâli. Skaler sürüm okunaklı ama walk-forward
    doğrulamada binlerce kez çağrılıyor; Python döngüsü orada dakikalara mal olur.
    """
    t = np.ones_like(lam, dtype=float)
    m00 = (x == 0) & (y == 0)
    m01 = (x == 0) & (y == 1)
    m10 = (x == 1) & (y == 0)
    m11 = (x == 1) & (y == 1)
    t[m00] = 1.0 - lam[m00] * mu[m00] * rho
    t[m01] = 1.0 + lam[m01] * rho
    t[m10] = 1.0 + mu[m10] * rho
    t[m11] = 1.0 - rho
    return t


def time_weight(days_ago: np.ndarray, xi: float = 0.0045) -> np.ndarray:
    """Üstel sönüm (madde 54). xi=0.0045 -> yarı ömür ~154 gün."""
    return np.exp(-xi * days_ago)


@dataclass
class DixonColesParams:
    teams: list[str]
    attack: dict[str, float]
    defence: dict[str, float]
    home_adv: float
    rho: float
    xi: float
    fitted_at: str = ""
    n_matches: int = 0
    version: str = "dc-1"

    def to_dict(self) -> dict:
        return {"teams": self.teams, "attack": self.attack, "defence": self.defence,
                "home_adv": self.home_adv, "rho": self.rho, "xi": self.xi,
                "fitted_at": self.fitted_at, "n_matches": self.n_matches,
                "version": self.version}


class DixonColes:
    def __init__(self, xi: float = 0.0045):
        self.xi = xi
        self.params: DixonColesParams | None = None

    # ---------------- eğitim ------------------------------------------
    def fit(self, home: np.ndarray, away: np.ndarray,
            hg: np.ndarray, ag: np.ndarray, days_ago: np.ndarray,
            teams: list[str]) -> DixonColesParams:
        """
        Vektörel olabilirlik. 55 takımlı bir lig için 112 parametre demek;
        döngülü uygulama walk-forward doğrulamada saatler sürer.
        Tau maskeleri bir kez hesaplanır, Poisson gammaln ile açılır.
        """
        n = len(teams)
        idx = {t: i for i, t in enumerate(teams)}
        h_i = np.array([idx[t] for t in home])
        a_i = np.array([idx[t] for t in away])
        w = time_weight(days_ago, self.xi)
        hg = np.asarray(hg, dtype=float)
        ag = np.asarray(ag, dtype=float)

        # Düşük skor maskeleri sabit — her yinelemede yeniden kurulmaz
        m00 = (hg == 0) & (ag == 0)
        m01 = (hg == 0) & (ag == 1)
        m10 = (hg == 1) & (ag == 0)
        m11 = (hg == 1) & (ag == 1)
        const = gammaln(hg + 1.0) + gammaln(ag + 1.0)

        x0 = np.concatenate([np.zeros(n), np.zeros(n), [0.25], [-0.05]])

        def nll(p):
            atk = p[:n] - p[:n].mean()      # kimlik kısıtı amaç fonksiyonunda
            dfc = p[n:2 * n]
            ha, rho = p[2 * n], p[2 * n + 1]

            lam = np.clip(np.exp(atk[h_i] - dfc[a_i] + ha), 1e-6, 12.0)
            mu = np.clip(np.exp(atk[a_i] - dfc[h_i]), 1e-6, 12.0)

            ll = (hg * np.log(lam) - lam + ag * np.log(mu) - mu - const)

            t = np.ones_like(lam)
            t[m00] = 1.0 - lam[m00] * mu[m00] * rho
            t[m01] = 1.0 + lam[m01] * rho
            t[m10] = 1.0 + mu[m10] * rho
            t[m11] = 1.0 - rho
            ll = ll + np.log(np.clip(t, 1e-9, None))

            # Hafif L2: az maçı olan takımın gücü patlamasın (madde 62 ruhu)
            penalty = 1e-3 * (np.sum(atk ** 2) + np.sum(dfc ** 2))
            return -np.sum(w * ll) + penalty

        bnds = [(-3, 3)] * (2 * n) + [(-1, 1), (-0.20, 0.20)]
        res = minimize(nll, x0, method="L-BFGS-B", bounds=bnds,
                       options={"maxiter": 500, "maxfun": 80_000})

        atk = res.x[:n] - res.x[:n].mean()
        self.params = DixonColesParams(
            teams=teams,
            attack={t: float(atk[i]) for t, i in idx.items()},
            defence={t: float(res.x[n + i]) for t, i in idx.items()},
            home_adv=float(res.x[2 * n]), rho=float(res.x[2 * n + 1]),
            xi=self.xi, n_matches=len(hg))
        return self.params

    # ---------------- tahmin ------------------------------------------
    def score_matrix(self, home_team: str, away_team: str,
                     home_adv_override: float | None = None) -> np.ndarray:
        p = self.params
        ha = p.home_adv if home_adv_override is None else home_adv_override
        lam = np.exp(p.attack[home_team] - p.defence[away_team] + ha)
        mu = np.exp(p.attack[away_team] - p.defence[home_team])
        return build_matrix(lam, mu, p.rho)


def build_matrix(lam: float, mu: float, rho: float,
                 max_goals: int = MAX_GOALS) -> np.ndarray:
    """Skor olasılık matrisi. Tüm marketler bundan türer."""
    h = poisson.pmf(np.arange(max_goals + 1), lam)
    a = poisson.pmf(np.arange(max_goals + 1), mu)
    m = np.outer(h, a)
    for x in range(2):
        for y in range(2):
            m[x, y] *= tau(x, y, lam, mu, rho)
    return m / m.sum()


# ---------------- market türetme (madde 46) ---------------------------
def market_1x2(m: np.ndarray) -> dict[str, float]:
    return {"HOME": float(np.tril(m, -1).sum()),
            "DRAW": float(np.trace(m)),
            "AWAY": float(np.triu(m, 1).sum())}


def market_over_under(m: np.ndarray, line: float = 2.5) -> dict[str, float]:
    n = m.shape[0]
    tot = np.add.outer(np.arange(n), np.arange(n))
    over = float(m[tot > line].sum())
    return {"OVER": over, "UNDER": 1.0 - over}


def market_btts(m: np.ndarray) -> dict[str, float]:
    yes = float(m[1:, 1:].sum())
    return {"YES": yes, "NO": 1.0 - yes}


def market_asian_handicap(m: np.ndarray, line: float) -> dict[str, float]:
    """line = ev sahibine verilen handikap (-0.5 => ev favori)."""
    n = m.shape[0]
    diff = np.subtract.outer(np.arange(n), np.arange(n)) + line
    return {"HOME": float(m[diff > 0].sum()),
            "PUSH": float(m[diff == 0].sum()),
            "AWAY": float(m[diff < 0].sum())}


def correct_score_top(m: np.ndarray, k: int = 5) -> list[tuple[str, float]]:
    flat = [(f"{i}-{j}", float(m[i, j])) for i in range(m.shape[0])
            for j in range(m.shape[1])]
    return sorted(flat, key=lambda t: -t[1])[:k]
