"""
Sinir ağı (madde 66) — KOŞULLU kullanım.

Dürüst uyarı, dosyanın en başında olsun: bu veri hacminde sinir ağı
büyük ihtimalle GBDT'yi geçmez. Tipik bir lig 380 maç/sezon üretir;
5 sezon 1900 maç eder. Derin öğrenme bu ölçekte avantaj sağlamaz.

Değerli olduğu tek yer: takım gömüleri (embedding). Bir takımı 8 boyutlu
vektörle temsil etmek, "kim kime karşı iyi oynar" ilişkisini GBDT'nin
yakalayamadığı biçimde öğrenebilir. Bunun için de büyük veri gerekir:
en az ~15.000 maç (çok ligli havuz).

`should_use_neural()` bu kararı senin yerine vermez, sana rakamı gösterir.
"""
from __future__ import annotations
import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass

log = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:                                   # pragma: no cover
    HAS_TORCH = False
    nn = object                                       # type: ignore


MIN_MATCHES_FOR_NEURAL = 15_000
MIN_TEAMS_FOR_EMBEDDING = 120


@dataclass
class NeuralViability:
    n_matches: int
    n_teams: int
    gbdt_log_loss: float | None
    verdict: str
    recommended: bool


def should_use_neural(n_matches: int, n_teams: int,
                      gbdt_log_loss: float | None = None) -> NeuralViability:
    """
    Karar yardımcısı. Eğitim koşmadan önce çağır.
    "Deneyelim" cazip gelir ama boşa geçen bir hafta pahalıdır.
    """
    if n_matches < MIN_MATCHES_FOR_NEURAL:
        return NeuralViability(
            n_matches, n_teams, gbdt_log_loss,
            f"{n_matches} maç var, en az {MIN_MATCHES_FOR_NEURAL} gerekir. "
            f"Bu ölçekte GBDT daha iyi ve çok daha hızlı eğitilir.",
            False)
    if n_teams < MIN_TEAMS_FOR_EMBEDDING:
        return NeuralViability(
            n_matches, n_teams, gbdt_log_loss,
            f"{n_teams} takım gömü öğrenmek için az. Çok ligli havuz kur.",
            False)
    return NeuralViability(
        n_matches, n_teams, gbdt_log_loss,
        "Veri ölçeği yeterli. GBDT'yi baseline al ve geçemezse bırak.",
        True)


# ---------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------
if HAS_TORCH:

    class TeamEmbeddingNet(nn.Module):
        """
        Takım gömüsü + bağlam özellikleri -> iki Poisson oranı.

        Çıktı olarak 1X2 olasılığı DEĞİL, lambda_home ve lambda_away üretir.
        Böylece skor matrisi yine Dixon-Coles ile kurulur ve tüm marketler
        tek kaynaktan türer. Bu tasarım tercihi önemli: ağ 1X2 öğrenirse
        alt/üst ile tutarsız olasılıklar üretebilir.
        """

        def __init__(self, n_teams: int, n_context: int,
                     embed_dim: int = 8, hidden: int = 32, dropout: float = 0.3):
            super().__init__()
            self.attack = nn.Embedding(n_teams, embed_dim)
            self.defence = nn.Embedding(n_teams, embed_dim)
            nn.init.normal_(self.attack.weight, 0.0, 0.05)
            nn.init.normal_(self.defence.weight, 0.0, 0.05)

            self.head = nn.Sequential(
                nn.Linear(embed_dim * 4 + n_context, hidden),
                nn.LayerNorm(hidden),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(hidden, hidden // 2),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(hidden // 2, 2),
            )
            self.home_adv = nn.Parameter(torch.tensor(0.25))

        def forward(self, home_idx, away_idx, context):
            ha, hd = self.attack(home_idx), self.defence(home_idx)
            aa, ad = self.attack(away_idx), self.defence(away_idx)
            x = torch.cat([ha, hd, aa, ad, context], dim=-1)
            out = self.head(x)
            # exp ile pozitif lambda; clamp patlamayı engeller
            lam_h = torch.exp(out[:, 0] + self.home_adv).clamp(0.05, 6.0)
            lam_a = torch.exp(out[:, 1]).clamp(0.05, 6.0)
            return lam_h, lam_a


    class NeuralGoalsModel:
        def __init__(self, teams: list[str], n_context: int, **kw):
            self.teams = teams
            self.idx = {t: i for i, t in enumerate(teams)}
            self.net = TeamEmbeddingNet(len(teams), n_context, **kw)
            self.context_cols: list[str] = []

        def fit(self, df: pd.DataFrame, context: pd.DataFrame,
                weights: np.ndarray | None = None,
                epochs: int = 120, lr: float = 3e-3,
                valid_fraction: float = 0.15, patience: int = 15):
            """
            Poisson negatif log-olabilirlik ile eğitim.
            Erken durdurma zorunlu — bu ölçekte ezberleme çok hızlı olur.
            """
            self.context_cols = list(context.columns)
            n = len(df)
            split = int(n * (1 - valid_fraction))    # kronolojik ayrım, karıştırma yok

            h = torch.tensor(df.home_team.map(self.idx).to_numpy(), dtype=torch.long)
            a = torch.tensor(df.away_team.map(self.idx).to_numpy(), dtype=torch.long)
            c = torch.tensor(context.fillna(0).to_numpy(), dtype=torch.float32)
            hg = torch.tensor(df.home_goals.to_numpy(), dtype=torch.float32)
            ag = torch.tensor(df.away_goals.to_numpy(), dtype=torch.float32)
            w = torch.tensor(weights if weights is not None else np.ones(n),
                             dtype=torch.float32)

            opt = torch.optim.AdamW(self.net.parameters(), lr=lr, weight_decay=1e-3)
            sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

            best, best_state, bad = float("inf"), None, 0
            for epoch in range(epochs):
                self.net.train()
                opt.zero_grad()
                lh, la = self.net(h[:split], a[:split], c[:split])
                loss = (_poisson_nll(lh, hg[:split]) + _poisson_nll(la, ag[:split]))
                loss = (loss * w[:split]).mean()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
                opt.step()
                sched.step()

                self.net.eval()
                with torch.no_grad():
                    vh, va = self.net(h[split:], a[split:], c[split:])
                    vloss = (_poisson_nll(vh, hg[split:]) +
                             _poisson_nll(va, ag[split:])).mean().item()

                if vloss < best - 1e-4:
                    best, bad = vloss, 0
                    best_state = {k: v.clone() for k, v in self.net.state_dict().items()}
                else:
                    bad += 1
                    if bad >= patience:
                        log.info("Erken durduruldu: epoch %d, doğrulama %.5f", epoch, best)
                        break

            if best_state:
                self.net.load_state_dict(best_state)
            return self

        def predict_lambdas(self, df: pd.DataFrame,
                            context: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
            self.net.eval()
            with torch.no_grad():
                h = torch.tensor(df.home_team.map(self.idx).fillna(0).to_numpy(),
                                 dtype=torch.long)
                a = torch.tensor(df.away_team.map(self.idx).fillna(0).to_numpy(),
                                 dtype=torch.long)
                c = torch.tensor(context[self.context_cols].fillna(0).to_numpy(),
                                 dtype=torch.float32)
                lh, la = self.net(h, a, c)
            return lh.numpy(), la.numpy()

        def team_vectors(self) -> pd.DataFrame:
            """
            Öğrenilen gömüler. Kümeleme yaparsan stil gruplarını görürsün —
            bu tek başına bile analitik değer taşır.
            """
            with torch.no_grad():
                atk = self.net.attack.weight.numpy()
                dfc = self.net.defence.weight.numpy()
            return pd.DataFrame(
                np.hstack([atk, dfc]), index=self.teams,
                columns=[f"atk_{i}" for i in range(atk.shape[1])] +
                        [f"def_{i}" for i in range(dfc.shape[1])])


    def _poisson_nll(rate, target):
        return rate - target * torch.log(rate.clamp_min(1e-8))

else:                                                  # pragma: no cover

    class NeuralGoalsModel:                            # type: ignore
        def __init__(self, *a, **kw):
            raise RuntimeError(
                "PyTorch kurulu değil. `pip install torch` ya da bu modeli atla — "
                "should_use_neural() zaten çoğu durumda atlamanı öneriyor.")
