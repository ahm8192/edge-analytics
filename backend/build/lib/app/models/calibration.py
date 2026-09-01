"""
Kalibrasyon (madde 71): model %70 dediğinde gerçekten %70 çıkmalı.
Ham model çıktısı neredeyse hiçbir zaman kalibre değildir.
"""
from __future__ import annotations
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


class Calibrator:
    def __init__(self, method: str = "isotonic"):
        self.method = method
        self._m = None

    def fit(self, p: np.ndarray, y: np.ndarray) -> "Calibrator":
        p = np.clip(p, 1e-6, 1 - 1e-6)
        if self.method == "isotonic":
            self._m = IsotonicRegression(out_of_bounds="clip").fit(p, y)
        else:  # Platt
            self._m = LogisticRegression(C=1e6).fit(_logit(p).reshape(-1, 1), y)
        return self

    def transform(self, p: np.ndarray) -> np.ndarray:
        p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
        if self.method == "isotonic":
            out = self._m.predict(p)
        else:
            out = self._m.predict_proba(_logit(p).reshape(-1, 1))[:, 1]
        return np.clip(out, 1e-6, 1 - 1e-6)


def _logit(p):
    return np.log(p / (1 - p))


def reliability_curve(p: np.ndarray, y: np.ndarray, bins: int = 10):
    """Güvenilirlik eğrisi: UI'da 'model kalibre mi' grafiği."""
    edges = np.linspace(0, 1, bins + 1)
    idx = np.digitize(p, edges) - 1
    out = []
    for b in range(bins):
        m = idx == b
        if m.sum() == 0:
            continue
        out.append({"bin_center": float((edges[b] + edges[b + 1]) / 2),
                    "predicted": float(p[m].mean()),
                    "observed": float(y[m].mean()),
                    "n": int(m.sum())})
    return out


def expected_calibration_error(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    curve = reliability_curve(p, y, bins)
    n = len(p)
    return float(sum(c["n"] / n * abs(c["predicted"] - c["observed"]) for c in curve))
