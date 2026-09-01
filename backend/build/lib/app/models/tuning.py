"""
Hiperparametre araması (madde 70, 73).

Kural: arama SADECE doğrulama setinde yapılır. Test seti bir kez,
en sonda, tek seferlik açılır. Test setine bakarak parametre seçmek
en sık yapılan ve en pahalı hatadır.
"""
from __future__ import annotations
import itertools
import logging
import numpy as np
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)


@dataclass
class TuningResult:
    best_params: dict
    best_score: float
    all_results: list[dict]
    fold_variance: float

    @property
    def is_stable(self) -> bool:
        """
        Katlar arası varyans yüksekse "en iyi" parametre şanstır.
        Ortalamaya bakıp varyansı görmezden gelmek overfit'in ta kendisidir.
        """
        return self.fold_variance < abs(self.best_score) * 0.15


def grid_search(param_grid: dict[str, list], fit_eval: Callable[[dict], list[float]],
                minimize: bool = True) -> TuningResult:
    keys = list(param_grid)
    results = []

    for values in itertools.product(*(param_grid[k] for k in keys)):
        params = dict(zip(keys, values))
        fold_scores = fit_eval(params)
        results.append({
            "params": params,
            "mean": float(np.mean(fold_scores)),
            "std": float(np.std(fold_scores)),
            "folds": fold_scores,
        })
        log.info("%s -> %.5f (±%.5f)", params, results[-1]["mean"], results[-1]["std"])

    results.sort(key=lambda r: r["mean"] if minimize else -r["mean"])
    best = results[0]
    return TuningResult(best["params"], best["mean"], results, best["std"])


DEFAULT_GRIDS = {
    "dixon_coles": {"xi": [0.0025, 0.0035, 0.0045, 0.0065, 0.0090]},
    "gbdt": {
        "learning_rate": [0.02, 0.04],
        "num_leaves": [7, 15, 31],
        "min_data_in_leaf": [40, 80, 150],
        "lambda_l2": [1.0, 5.0, 15.0],
    },
    "ensemble": {"model_weight_vs_market": [0.20, 0.35, 0.50]},
}
