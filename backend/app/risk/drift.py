"""
Model sağlığı ve konsept kayması (madde 96, 97).
Model sessizce bozulur. Alarm yoksa aylarca kaybedersin.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from ..models.metrics import log_loss, brier
from ..models.calibration import expected_calibration_error


@dataclass
class HealthThresholds:
    log_loss_warn: float = 1.08    # baseline'a oran
    log_loss_halt: float = 1.15
    ece_warn: float = 0.04
    ece_halt: float = 0.08
    min_clv_warn: float = 0.0
    min_n: int = 50


def assess(p: np.ndarray, y: np.ndarray, baseline_ll: float,
           mean_clv: float | None = None,
           th: HealthThresholds = HealthThresholds()) -> dict:
    n = len(p)
    if n < th.min_n:
        return {"n": n, "alarm_level": "insufficient_data",
                "message": f"Karar için en az {th.min_n} örnek gerekli (madde 99)."}

    ll = log_loss(p, y)
    ratio = ll / baseline_ll
    ece = expected_calibration_error(p, y)

    level, msgs = "ok", []
    if ratio >= th.log_loss_halt:
        level = "halt"; msgs.append("Log loss baseline'ın çok üstünde — bahis durdur.")
    elif ratio >= th.log_loss_warn:
        level = "warn"; msgs.append("Log loss bozuluyor — yeniden eğitim gerekli.")

    if ece >= th.ece_halt:
        level = "halt"; msgs.append("Kalibrasyon çöktü — olasılıklar güvenilmez.")
    elif ece >= th.ece_warn and level == "ok":
        level = "warn"; msgs.append("Kalibrasyon kayıyor — recalibrate et.")

    if mean_clv is not None and mean_clv < th.min_clv_warn and level == "ok":
        level = "warn"; msgs.append("CLV negatif — piyasayı yenemiyorsun (madde 77).")

    return {"n": n, "log_loss": ll, "baseline_log_loss": baseline_ll,
            "ll_ratio": ratio, "brier": brier(p, y), "ece": ece,
            "mean_clv": mean_clv, "alarm_level": level,
            "message": " ".join(msgs) or "Model sağlıklı."}


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index — girdi dağılımı kaydı mı? >0.25 ciddi kayma."""
    edges = np.percentile(expected, np.linspace(0, 100, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    e = np.histogram(expected, edges)[0] / len(expected)
    a = np.histogram(actual, edges)[0] / len(actual)
    e, a = np.clip(e, 1e-6, None), np.clip(a, 1e-6, None)
    return float(np.sum((a - e) * np.log(a / e)))
