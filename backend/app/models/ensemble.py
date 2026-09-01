"""
Model birleştirme (madde 67, 64).

Tek model her zaman bir yerde kördür. Farklı AİLELERDEN modellerin
ortalaması, aynı ailenin on varyantından iyidir.

Ağırlıklar doğrulama setinde log loss'u minimize ederek öğrenilir —
elle atanmaz.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from scipy.optimize import minimize

from .metrics import multiclass_log_loss


@dataclass
class EnsembleWeights:
    names: list[str]
    weights: np.ndarray
    validation_log_loss: float
    baseline_log_loss: float
    fitted_at: str = ""

    @property
    def skill(self) -> float:
        """Baseline'a (piyasa oranı) göre kazanım. Negatifse model işe yaramıyor."""
        return (self.baseline_log_loss - self.validation_log_loss) / self.baseline_log_loss

    def to_dict(self) -> dict:
        return {"names": self.names, "weights": self.weights.tolist(),
                "validation_log_loss": self.validation_log_loss,
                "baseline_log_loss": self.baseline_log_loss,
                "skill": self.skill, "fitted_at": self.fitted_at}


class ProbabilityEnsemble:
    """
    Log-alan (log-space) ağırlıklı birleştirme.
    Olasılıkları doğrudan ortalamak, aşırı güvenli tahminleri fazla ödüllendirir;
    logaritmik havuzlama daha muhafazakâr ve pratikte daha iyi kalibre olur.
    """

    def __init__(self, names: list[str]):
        self.names = names
        self.weights: np.ndarray | None = None
        self.meta: EnsembleWeights | None = None

    def fit(self, preds: list[np.ndarray], y_idx: np.ndarray,
            baseline_probs: np.ndarray | None = None) -> EnsembleWeights:
        """
        preds: her modelin (n, 3) olasılık matrisi
        y_idx: gerçek sonuç indeksi (0=ev, 1=beraberlik, 2=deplasman)
        """
        k = len(preds)
        stack = np.stack([np.clip(p, 1e-9, 1.0) for p in preds])   # (k, n, 3)

        def loss(w_raw: np.ndarray) -> float:
            w = _softmax(w_raw)
            combined = _log_pool(stack, w)
            return multiclass_log_loss(combined, y_idx)

        res = minimize(loss, np.zeros(k), method="Nelder-Mead",
                       options={"maxiter": 500, "xatol": 1e-4})
        self.weights = _softmax(res.x)

        combined = _log_pool(stack, self.weights)
        val_ll = multiclass_log_loss(combined, y_idx)
        base_ll = (multiclass_log_loss(baseline_probs, y_idx)
                   if baseline_probs is not None else val_ll)

        self.meta = EnsembleWeights(self.names, self.weights, val_ll, base_ll)
        return self.meta

    def predict(self, preds: list[np.ndarray]) -> np.ndarray:
        if self.weights is None:
            raise RuntimeError("Önce fit çağrılmalı")
        stack = np.stack([np.clip(p, 1e-9, 1.0) for p in preds])
        return _log_pool(stack, self.weights)

    def set_manual_weights(self, weights: dict[str, float]) -> None:
        """ELITE: kullanıcı kendi ağırlığını kurabilir (madde: custom_weights)."""
        w = np.array([weights.get(n, 0.0) for n in self.names], dtype=float)
        if w.sum() <= 0:
            raise ValueError("Ağırlık toplamı pozitif olmalı")
        self.weights = w / w.sum()


def _log_pool(stack: np.ndarray, w: np.ndarray) -> np.ndarray:
    logp = np.tensordot(w, np.log(stack), axes=(0, 0))   # (n, 3)
    p = np.exp(logp)
    return p / p.sum(axis=1, keepdims=True)


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


def blend_with_market(model_probs: np.ndarray, market_probs: np.ndarray,
                      model_weight: float = 0.35) -> np.ndarray:
    """
    madde 76, 88: piyasa çok güçlü bir tahmincidir.
    Modeli piyasayla harmanlamak neredeyse her zaman log loss'u düşürür.
    Kenar payı ancak harmanlanmış olasılık hâlâ piyasadan saparsa gerçektir.
    """
    w = np.clip(model_weight, 0.0, 1.0)
    logp = w * np.log(np.clip(model_probs, 1e-9, 1)) + \
           (1 - w) * np.log(np.clip(market_probs, 1e-9, 1))
    p = np.exp(logp)
    return p / p.sum(axis=-1, keepdims=True)
