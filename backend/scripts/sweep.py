"""
Parametre taraması. KURAL: tarama doğrulama döneminde yapılır,
son iki sezon (holdout) hiç açılmaz. (madde 70, 73)
"""
import sys, sqlite3, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from scripts.train import run

VALIDATION = ("2014-08-01", "2023-07-01")   # tarama burada
conn = sqlite3.connect("edge.db")

print(f"{'xi':>8s} {'yarı ömür':>10s} {'model LL':>10s} {'harman LL':>10s} {'piyasa LL':>10s} {'beceri':>9s}")
print("-" * 62)
best = None
for xi in [0.0020, 0.0030, 0.0045, 0.0070, 0.0100, 0.0150]:
    r = run(conn, xi=xi, train_years=4.0, step_days=45,
            start=VALIDATION[0], blend_weight=0.30)
    a = r.pop("_arrays")
    # holdout'u dışla
    mask = a["df"].date < VALIDATION[1]
    from scripts.train import _score
    m = _score(a["model"][mask.to_numpy()], a["y"][mask.to_numpy()])
    mk = _score(a["market"][mask.to_numpy()], a["y"][mask.to_numpy()])
    bl = _score(a["blend"][mask.to_numpy()], a["y"][mask.to_numpy()])
    skill = (mk["log_loss"] - bl["log_loss"]) / mk["log_loss"]
    print(f"{xi:8.4f} {np.log(2)/xi:9.0f}g {m['log_loss']:10.5f} "
          f"{bl['log_loss']:10.5f} {mk['log_loss']:10.5f} {skill*100:+8.2f}%")
    if best is None or bl["log_loss"] < best[1]:
        best = (xi, bl["log_loss"])

print(f"\nen iyi xi (doğrulamada): {best[0]:.4f}")
Path("best_xi.json").write_text(json.dumps({"xi": best[0]}))
