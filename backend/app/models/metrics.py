"""Değerlendirme metrikleri (madde 72): accuracy DEĞİL, log loss ve Brier."""
from __future__ import annotations
import numpy as np


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def multiclass_log_loss(P: np.ndarray, y_idx: np.ndarray) -> float:
    P = np.clip(P, 1e-12, 1.0)
    P = P / P.sum(axis=1, keepdims=True)
    return float(-np.mean(np.log(P[np.arange(len(y_idx)), y_idx])))


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def rps(P: np.ndarray, y_idx: np.ndarray) -> float:
    """Ranked Probability Score - sıralı 1X2 için log loss'tan daha adil."""
    n, k = P.shape
    Y = np.zeros_like(P); Y[np.arange(n), y_idx] = 1
    cP, cY = np.cumsum(P, axis=1), np.cumsum(Y, axis=1)
    return float(np.mean(np.sum((cP - cY) ** 2, axis=1) / (k - 1)))


def skill_vs_baseline(model_ll: float, baseline_ll: float) -> float:
    """Baseline'a (madde 64: sadece oranlar) göre kazanım. Pozitif = model işe yarıyor."""
    return (baseline_ll - model_ll) / baseline_ll
