"""Oran profili -> tarihsel sonuç. `scripts/odds_empirical.py` çıktısını kullanır.

227k maç üzerinde eğitildi. Piyasayı YENMEZ (logloss ~eşit) ama piyasadan
biraz daha iyi kalibre (ECE 0.0065 vs 0.0125). Bizim modelimiz piyasadan
kötü olduğu için servis edilen olasılığı buna demirliyoruz.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

_DATA: dict | None = None


def _load() -> dict:
    global _DATA
    if _DATA is None:
        p = Path(__file__).parent / "model_data" / "odds_empirical.json"
        try:
            _DATA = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _DATA = {}
    return _DATA


def available() -> bool:
    return bool(_load().get("logit"))


def _devig(oh: float, od: float, oa: float) -> tuple[float, float, float, float]:
    ih, idr, ia = 1.0 / oh, 1.0 / od, 1.0 / oa
    s = ih + idr + ia
    return ih / s, idr / s, ia / s, s - 1.0


def _features(oh, od, oa, over25, under25, elo_diff) -> dict:
    ih, idr, ia, margin = _devig(oh, od, oa)
    if over25 and under25 and over25 > 1.0 and under25 > 1.0:
        oo, ou = 1.0 / over25, 1.0 / under25
        ou_over = oo / (oo + ou)
    else:
        ou_over = 0.5
    return {
        "imp_h": ih, "imp_d": idr, "imp_a": ia, "margin": margin,
        "spread": ih - ia, "fav_imp": max(ih, ia),
        "home_fav": 1.0 if ih >= ia else 0.0,
        "ou_over": ou_over, "elo_diff": float(elo_diff or 0.0),
    }


def empirical_probs(oh: float, od: float, oa: float,
                    over25: float | None = None, under25: float | None = None,
                    elo_diff: float = 0.0) -> dict:
    """Oranlardan kalibre {H,D,A}. Model yoksa düz devig döner."""
    d = _load()
    lg = d.get("logit")
    feats = _features(oh, od, oa, over25, under25, elo_diff)
    if not lg:
        return {"H": feats["imp_h"], "D": feats["imp_d"], "A": feats["imp_a"]}
    names, mu, sd = lg["features"], lg["mean"], lg["std"]
    x = [(feats[n] - mu[i]) / sd[i] for i, n in enumerate(names)]
    z = [b + sum(ci * xi for ci, xi in zip(coef, x))
         for coef, b in zip(lg["coef"], lg["intercept"])]
    mx = max(z)
    e = [math.exp(v - mx) for v in z]
    se = sum(e)
    p = [v / se for v in e]
    return {"H": p[0], "D": p[1], "A": p[2]}


def similar(oh: float, od: float, oa: float) -> dict | None:
    """Bu oran profiline benzer tarihsel maçların gerçekleşen oranı + n."""
    d = _load()
    bins = d.get("bins") or {}
    if not bins:
        return None
    ih, _, _, _ = _devig(oh, od, oa)
    step = d.get("bin_step", 0.025)
    key = f"{round(round(ih / step) * step, 3):.3f}"
    b = bins.get(key)
    if not b or b["n"] < 80:
        return None
    return {"H": b["h"], "D": b["d"], "A": b["a"], "n": int(b["n"])}
