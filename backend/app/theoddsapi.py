"""The Odds API (the-odds-api.com) — ücretsiz plan: 500 istek/ay.

Her lig = 1 kredi, tüm yaklaşan maçlar + 20+ bahisçi (Pinnacle dahil).
API-Football'un dar 3-günlük penceresinin aksine tam fikstür.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://api.the-odds-api.com/v4"

LEAGUE_TO_SPORT = {
    "PL": "soccer_epl", "ELC": "soccer_efl_champ",
    "BL1": "soccer_germany_bundesliga", "SA": "soccer_italy_serie_a",
    "PD": "soccer_spain_la_liga", "FL1": "soccer_france_ligue_one",
    "DED": "soccer_netherlands_eredivisie", "PPL": "soccer_portugal_primeira_liga",
    "BSA": "soccer_brazil_campeonato", "CL": "soccer_uefa_champs_league",
    "EL": "soccer_uefa_europa_league", "TR1": "soccer_turkey_super_league",
}

_TTL = float(os.environ.get("ODDSAPI_TTL", "50400"))   # 14 saat (9 lig x ~1.7/gun ~ 460/ay)
_MIN_REMAINING = int(os.environ.get("ODDSAPI_MIN_REMAINING", "25"))
_cache: dict[str, tuple[float, list]] = {}
_lock = threading.Lock()
_remaining = [10_000]   # son görülen x-requests-remaining


def _key() -> str:
    return os.environ.get("ODDS_API_KEY", "").strip()


def enabled() -> bool:
    return bool(_key())


def _fetch_sport(sport: str) -> list:
    ck = f"odds:{sport}"
    now = time.monotonic()
    with _lock:
        hit = _cache.get(ck)
        if hit and now - hit[0] < _TTL:
            return hit[1]
    if _remaining[0] < _MIN_REMAINING:
        return []
    q = urlencode({"apiKey": _key(), "regions": "eu", "markets": "h2h",
                   "oddsFormat": "decimal", "dateFormat": "iso"})
    req = Request(f"{BASE}/sports/{sport}/odds/?{q}", headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=15) as r:
            rem = r.headers.get("x-requests-remaining")
            if rem is not None:
                _remaining[0] = int(float(rem))
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    with _lock:
        _cache[ck] = (now, data)
    return data


def _devig(o: list[float]) -> list[float]:
    inv = [1.0 / x for x in o]
    s = sum(inv)
    return [v / s for v in inv]


def odds_rows(codes: list[str]) -> list[dict]:
    """[{home, away, date, pin_1x2, best_1x2, pin_p_1x2, books}] — ham takım adlarıyla."""
    out: list[dict] = []
    if not enabled():
        return out
    for code in codes:
        sport = LEAGUE_TO_SPORT.get(code)
        if not sport:
            continue
        for m in _fetch_sport(sport):
            try:
                home, away = m["home_team"], m["away_team"]
                date = m["commence_time"][:10]
            except (KeyError, TypeError):
                continue
            pin = None
            best: dict[str, float] = {}
            for bm in m.get("bookmakers", []):
                mk = next((x for x in bm.get("markets", []) if x.get("key") == "h2h"), None)
                if not mk:
                    continue
                row: dict[str, float] = {}
                for oc in mk.get("outcomes", []):
                    nm = oc.get("name")
                    pr = oc.get("price")
                    if not pr:
                        continue
                    sel = "DRAW" if nm == "Draw" else ("HOME" if nm == home else
                                                       ("AWAY" if nm == away else None))
                    if sel:
                        row[sel] = float(pr)
                        best[sel] = max(best.get(sel, 0.0), float(pr))
                if bm.get("key") == "pinnacle" and len(row) == 3:
                    pin = row
            entry: dict = {"home": home, "away": away, "date": date,
                           "books": len(m.get("bookmakers", []))}
            if len(best) == 3:
                entry["best_1x2"] = best
            if pin:
                entry["pin_1x2"] = pin
                p = _devig([pin["HOME"], pin["DRAW"], pin["AWAY"]])
                entry["pin_p_1x2"] = {"HOME": round(p[0], 4), "DRAW": round(p[1], 4),
                                      "AWAY": round(p[2], 4)}
            elif len(best) == 3:
                p = _devig([best["HOME"], best["DRAW"], best["AWAY"]])
                entry["pin_p_1x2"] = {"HOME": round(p[0], 4), "DRAW": round(p[1], 4),
                                      "AWAY": round(p[2], 4)}
            out.append(entry)
    return out


def status() -> dict:
    return {"enabled": enabled(), "remaining": _remaining[0]}
