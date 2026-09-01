"""
Çoklu kaynak uzlaştırma (madde 1, 6).

İki sağlayıcı aynı maç için farklı şey söylediğinde ne olacağı ÖNCEDEN
kararlaştırılmalı. Sessizce birini seçmek, hangi verinin modele girdiğini
bilinmez yapar.
"""
from __future__ import annotations
import datetime as dt
import json
import logging
from collections import Counter
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class Resolution:
    field: str
    value: object
    method: str          # unanimous | majority | trust_weight | unresolved
    disagreement: bool
    candidates: dict


def reconcile_field(field: str, values: dict[str, object],
                    trust: dict[str, float],
                    numeric_tolerance: float = 0.0) -> Resolution:
    """
    values: {source_code: value}
    trust:  {source_code: ağırlık}
    """
    clean = {s: v for s, v in values.items() if v is not None}
    if not clean:
        return Resolution(field, None, "unresolved", False, values)

    distinct = list({_key(v, numeric_tolerance) for v in clean.values()})
    if len(distinct) == 1:
        return Resolution(field, next(iter(clean.values())), "unanimous", False, clean)

    # Çoğunluk
    counts = Counter(_key(v, numeric_tolerance) for v in clean.values())
    top, n = counts.most_common(1)[0]
    if n > len(clean) / 2:
        value = next(v for v in clean.values() if _key(v, numeric_tolerance) == top)
        return Resolution(field, value, "majority", True, clean)

    # Beraberlik: güven ağırlığı karar verir
    best_source = max(clean, key=lambda s: trust.get(s, 1.0))
    return Resolution(field, clean[best_source], "trust_weight", True, clean)


def _key(v, tol: float):
    if tol > 0 and isinstance(v, (int, float)):
        return round(float(v) / tol) * tol
    return v


def reconcile_match(conn, match_id: int, fields: list[str],
                    trust: dict[str, float]) -> dict:
    """Bir maçın tüm kaynak kayıtlarını okuyup uzlaştırır ve çelişkileri loglar."""
    rows = conn.execute(
        """SELECT s.code, r.payload_json FROM match_source_record r
           JOIN source s ON s.id = r.source_id
           WHERE r.match_id = ?""", (match_id,)).fetchall()

    payloads = {code: json.loads(p) for code, p in rows}
    resolved, conflicts = {}, []

    for f in fields:
        vals = {s: p.get(f) for s, p in payloads.items()}
        res = reconcile_field(f, vals, trust,
                              numeric_tolerance=0.01 if f.startswith("xg") else 0.0)
        resolved[f] = res.value
        if res.disagreement:
            conflicts.append(res)
            conn.execute(
                """INSERT INTO source_conflict(match_id, field, values_json,
                       resolved_value, resolution, detected_at)
                   VALUES (?,?,?,?,?,?)""",
                (match_id, f, json.dumps(res.candidates, default=str),
                 json.dumps(res.value, default=str), res.method,
                 dt.datetime.now(dt.timezone.utc).isoformat()))

    if conflicts:
        log.info("Maç %s: %d alanda çelişki uzlaştırıldı", match_id, len(conflicts))
    conn.commit()
    return {"resolved": resolved, "conflicts": len(conflicts)}
