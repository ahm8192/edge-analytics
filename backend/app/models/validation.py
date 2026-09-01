"""
Zaman serisi doğrulama (madde 68, 69, 73).
Rastgele k-fold burada YASAK: geleceği görüp geçmişi tahmin etmiş olursun.
"""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass
from typing import Callable, Iterator
import numpy as np


@dataclass
class Fold:
    train_idx: np.ndarray
    test_idx: np.ndarray
    train_end: dt.datetime
    test_end: dt.datetime


def walk_forward(dates: np.ndarray, initial_days: int = 540,
                 step_days: int = 14, embargo_days: int = 1) -> Iterator[Fold]:
    """
    İleri yürüyen doğrulama. embargo: eğitim sonu ile test başı arasına boşluk
    koyar; aynı gün oynanan maçların bilgi sızdırmasını engeller.
    """
    order = np.argsort(dates)
    d = dates[order]
    start, end = d[0], d[-1]
    cut = start + dt.timedelta(days=initial_days)

    while cut < end:
        test_end = cut + dt.timedelta(days=step_days)
        tr = order[d <= cut]
        te = order[(d > cut + dt.timedelta(days=embargo_days)) & (d <= test_end)]
        if len(te) > 0:
            yield Fold(tr, te, cut, test_end)
        cut = test_end


def evaluate_walk_forward(dates, fit_fn: Callable, predict_fn: Callable,
                          score_fn: Callable, **kw) -> list[dict]:
    """Her kat için skor döndürür. Katlar arası VARYANS, ortalamadan önemlidir."""
    results = []
    for f in walk_forward(dates, **kw):
        model = fit_fn(f.train_idx)
        p = predict_fn(model, f.test_idx)
        results.append({"train_end": f.train_end.isoformat(),
                        "n_train": len(f.train_idx), "n_test": len(f.test_idx),
                        "score": score_fn(p, f.test_idx)})
    return results
