"""
Özellik seçimi (madde 74).

500 özellikli model gürültü ezberler. Kural: eklenen her özellik,
kendi ağırlığını doğrulama setinde taşımak zorunda.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

MAX_FEATURES = 60


def drop_constant(df: pd.DataFrame, threshold: float = 0.995) -> list[str]:
    """Tek değere sıkışmış kolonlar bilgi taşımaz."""
    drop = []
    for c in df.columns:
        vc = df[c].value_counts(normalize=True, dropna=False)
        if len(vc) and vc.iloc[0] >= threshold:
            drop.append(c)
    return drop


def drop_correlated(df: pd.DataFrame, threshold: float = 0.95) -> list[str]:
    """
    Yüksek korelasyonlu ikizlerden birini at.
    İkisini de tutmak modeli kararsız yapar, önem skorlarını böler.
    """
    num = df.select_dtypes(include=[np.number])
    if num.shape[1] < 2:
        return []
    corr = num.corr().abs()
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    return [c for c in upper.columns if any(upper[c] > threshold)]


def stability_selection(X: pd.DataFrame, y: np.ndarray, folds: list,
                        importance_fn, keep_ratio: float = 0.5) -> list[str]:
    """
    Özelliği tek bir eğitimin önem skoruna göre seçmek yanıltıcıdır.
    Katlar arasında TUTARLI biçimde önemli olanlar seçilir.
    """
    counts = pd.Series(0, index=X.columns, dtype=int)
    for train_idx, _ in folds:
        imp = importance_fn(X.iloc[train_idx], y[train_idx])
        top = imp.sort_values(ascending=False).head(int(len(imp) * keep_ratio))
        counts[top.index] += 1
    threshold = max(1, int(len(folds) * 0.6))
    return counts[counts >= threshold].index.tolist()


def apply_budget(selected: list[str], max_features: int = MAX_FEATURES) -> list[str]:
    if len(selected) <= max_features:
        return selected
    return selected[:max_features]


def prune(df: pd.DataFrame, y: np.ndarray, folds: list,
          importance_fn) -> tuple[pd.DataFrame, dict]:
    report = {}
    const = drop_constant(df)
    df2 = df.drop(columns=const)
    report["dropped_constant"] = const

    corr = drop_correlated(df2)
    df3 = df2.drop(columns=corr)
    report["dropped_correlated"] = corr

    keep = stability_selection(df3, y, folds, importance_fn)
    keep = apply_budget(keep)
    report["kept"] = keep
    report["final_count"] = len(keep)
    return df3[keep], report
