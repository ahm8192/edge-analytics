"""
Gradient boosting (madde 65, 74).

Tabular veride genelde en iyi tekil model. Ama Dixon-Coles'un yerine değil,
YANINA konur: DC yapısal (gol üretimi Poisson'dur) bilgiyi taşır,
GBDT yapının kaçırdığı etkileşimleri yakalar.
"""
from __future__ import annotations
import logging
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:                       # pragma: no cover
    HAS_LGB = False
    from sklearn.ensemble import HistGradientBoostingClassifier


OUTCOME_INDEX = {"HOME": 0, "DRAW": 1, "AWAY": 2}


class GbdtOutcomeModel:
    """
    1X2 için çok sınıflı sınıflandırıcı.
    Çıktısı HAM olasılıktır — kalibrasyon ayrı adımdır (madde 71).
    """

    def __init__(self, params: dict | None = None):
        self.params = params or {
            "objective": "multiclass",
            "num_class": 3,
            "learning_rate": 0.03,
            "num_leaves": 15,          # küçük tutuldu: veri az, overfit kolay
            "min_data_in_leaf": 80,
            "feature_fraction": 0.7,
            "bagging_fraction": 0.8,
            "bagging_freq": 1,
            "lambda_l2": 5.0,
            "verbosity": -1,
        }
        self.model = None
        self.feature_names: list[str] = []

    def fit(self, X: pd.DataFrame, y: np.ndarray,
            sample_weight: np.ndarray | None = None,
            X_valid: pd.DataFrame | None = None,
            y_valid: np.ndarray | None = None,
            num_round: int = 800) -> "GbdtOutcomeModel":
        self.feature_names = list(X.columns)

        if not HAS_LGB:
            log.warning("lightgbm yok, sklearn HistGradientBoosting kullanılıyor")
            self.model = HistGradientBoostingClassifier(
                max_iter=400, learning_rate=0.04, max_leaf_nodes=15,
                min_samples_leaf=80, l2_regularization=5.0)
            self.model.fit(X, y, sample_weight=sample_weight)
            return self

        train = lgb.Dataset(X, label=y, weight=sample_weight)
        valid = [lgb.Dataset(X_valid, label=y_valid, reference=train)] \
            if X_valid is not None else None

        self.model = lgb.train(
            self.params, train, num_boost_round=num_round,
            valid_sets=valid,
            callbacks=[lgb.early_stopping(60, verbose=False)] if valid else None,
        )
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if not HAS_LGB:
            return self.model.predict_proba(X)
        p = self.model.predict(X, num_iteration=getattr(self.model, "best_iteration", None))
        return np.asarray(p).reshape(len(X), 3)

    def importance(self) -> pd.Series:
        if not HAS_LGB:
            return pd.Series(0.0, index=self.feature_names)
        return pd.Series(self.model.feature_importance("gain"),
                         index=self.feature_names).sort_values(ascending=False)

    def explain(self, X: pd.DataFrame, top_k: int = 6) -> list[dict]:
        """
        madde 100: hangi etken olasılığı ne yönde itti.
        SHAP varsa onu, yoksa gain önemini kullanır.
        """
        if not HAS_LGB:
            return []
        try:
            contrib = self.model.predict(X, pred_contrib=True)
            row = np.asarray(contrib)[0]
            n = len(self.feature_names)
            # çok sınıflıda her sınıf için ayrı blok gelir; ev sahibi bloğu alınır
            block = row[:n + 1][:n]
            order = np.argsort(-np.abs(block))[:top_k]
            return [{"feature": self.feature_names[i],
                     "value": float(X.iloc[0, i]),
                     "contribution": float(block[i])} for i in order]
        except Exception as e:                       # pragma: no cover
            log.warning("Katkı hesabı başarısız: %s", e)
            return []


class GbdtGoalsModel:
    """
    Gol sayısı için ayrı regresyon (Poisson amaç fonksiyonu).
    Çıktı lambda olarak Dixon-Coles matrisine beslenir — böylece
    tüm marketler yine tek matristen türer ve tutarlı kalır.
    """

    def __init__(self):
        self.params = {"objective": "poisson", "learning_rate": 0.03,
                       "num_leaves": 15, "min_data_in_leaf": 80,
                       "feature_fraction": 0.7, "lambda_l2": 5.0, "verbosity": -1}
        self.home_model = None
        self.away_model = None

    def fit(self, X: pd.DataFrame, home_goals: np.ndarray, away_goals: np.ndarray,
            sample_weight: np.ndarray | None = None, num_round: int = 600):
        if not HAS_LGB:                              # pragma: no cover
            raise RuntimeError("Poisson hedefi için lightgbm gerekli")
        self.home_model = lgb.train(self.params,
                                    lgb.Dataset(X, home_goals, weight=sample_weight),
                                    num_boost_round=num_round)
        self.away_model = lgb.train(self.params,
                                    lgb.Dataset(X, away_goals, weight=sample_weight),
                                    num_boost_round=num_round)
        return self

    def predict_lambdas(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        lh = np.clip(self.home_model.predict(X), 0.05, 6.0)
        la = np.clip(self.away_model.predict(X), 0.05, 6.0)
        return lh, la
