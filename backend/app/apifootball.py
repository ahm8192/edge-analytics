"""API-Football (api-sports.io) — ücretsiz plan.

Ücretsiz planın sınırı: oran/sakatlık yalnızca ~3 günlük kayan pencere,
lige göre filtre yok (fixture id ile tek tek), günde 100 istek.
Bu yüzden: yakın maçlar (3 gün) için Pinnacle referansı + sakatlık;
uzak maçlar model-only kalır. Her şey sıkı önbelleklenir.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://v3.football.api-sports.io"

# API-Football lig id -> football-data.org competition kodu (params.json ile hizalı)
LEAGUE_ID_TO_CODE = {
    39: "PL", 40: "ELC", 78: "BL1", 135: "SA", 140: "PD", 61: "FL1",
    88: "DED", 94: "PPL", 71: "BSA", 2: "CL", 3: "EL", 203: "TR1",
}
TRACKED = set(LEAGUE_ID_TO_CODE)

_TTL = float(os.environ.get("APIFOOTBALL_TTL", "21600"))     # 6 saat
_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()
_req_today = [dt.date.today(), 0]
_MAX_DAY = int(os.environ.get("APIFOOTBALL_MAX_DAY", "80"))


def _key() -> str:
    # Render env yoksa gömülü ücretsiz anahtara düş (yayında panelden ver).
    return os.environ.get("API_FOOTBALL_KEY", "").strip() or "63e1cd1dc0acf458d373fbc9ce0f297c"


def enabled() -> bool:
    return bool(_key())


def _budget_ok() -> bool:
    today = dt.date.today()
    if _req_today[0] != today:
        _req_today[0], _req_today[1] = today, 0
    return _req_today[1] < _MAX_DAY


def _get(path: str, params: dict) -> dict | None:
    if not enabled() or not _budget_ok():
        return None
    ck = f"{path}?{urlencode(sorted(params.items()))}"
    now = time.monotonic()
    with _lock:
        hit = _cache.get(ck)
        if hit and now - hit[0] < _TTL:
            return hit[1]  # type: ignore
    url = f"{BASE}{path}?{urlencode(params)}"
    req = Request(url, headers={"x-apisports-key": _key(), "Accept": "application/json"})
    try:
        with urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    _req_today[1] += 1
    with _lock:
        _cache[ck] = (now, data)
    return data


def _pages(path: str, params: dict, cap: int = 8) -> list:
    out: list = []
    first = _get(path, {**params, "page": 1})
    if not first:
        return out
    out += first.get("response", [])
    total = first.get("paging", {}).get("total", 1)
    for p in range(2, min(total, cap) + 1):
        d = _get(path, {**params, "page": p})
        if not d:
            break
        out += d.get("response", [])
    return out


# ---------------------------------------------------------------- fikstür
def fixtures_window(days: int = 3) -> list[dict]:
    """Bugünden itibaren `days` gün, takip edilen liglerdeki maçlar."""
    today = dt.datetime.now(dt.timezone.utc).date()
    out: list[dict] = []
    for i in range(days):
        d = (today + dt.timedelta(days=i)).isoformat()
        data = _get("/fixtures", {"date": d})
        if not data:
            continue
        for f in data.get("response", []):
            lg = f.get("league", {})
            if lg.get("id") not in TRACKED:
                continue
            fx, tm, go = f["fixture"], f["teams"], f.get("goals", {})
            out.append({
                "af_id": fx["id"],
                "code": LEAGUE_ID_TO_CODE[lg["id"]],
                "date": fx["date"][:10],
                "kickoff": fx["date"],
                "home": tm["home"]["name"], "away": tm["away"]["name"],
                "home_id": tm["home"].get("id"), "away_id": tm["away"].get("id"),
                "home_logo": tm["home"].get("logo"), "away_logo": tm["away"].get("logo"),
                "status": fx.get("status", {}).get("short", "NS"),
                "hg": go.get("home"), "ag": go.get("away"),
            })
    return out


# ---------------------------------------------------------------- oranlar
def _devig(o: list[float]) -> list[float]:
    inv = [1.0 / x for x in o if x and x > 1.0]
    s = sum(inv)
    return [v / s for v in inv] if s else []


def odds_for_fixture(af_id: int) -> dict | None:
    """Pinnacle (varsa) + en iyi oran; 1X2 / Ü2.5 / KG."""
    data = _get("/odds", {"fixture": af_id})
    if not data or not data.get("response"):
        return None
    resp = data["response"][0]
    books = resp.get("bookmakers", [])
    if not books:
        return None

    def collect(bet_name: str) -> dict[str, list[float]]:
        acc: dict[str, list[float]] = {}
        for bm in books:
            for bet in bm.get("bets", []):
                if bet.get("name") != bet_name:
                    continue
                for v in bet.get("values", []):
                    try:
                        acc.setdefault(str(v["value"]), []).append(float(v["odd"]))
                    except (TypeError, ValueError):
                        continue
        return acc

    def pinnacle(bet_name: str) -> dict[str, float]:
        for bm in books:
            if bm.get("name", "").lower().startswith("pinnacle"):
                for bet in bm.get("bets", []):
                    if bet.get("name") == bet_name:
                        return {str(v["value"]): float(v["odd"])
                                for v in bet.get("values", []) if v.get("odd")}
        return {}

    mw = collect("Match Winner")
    ou = collect("Goals Over/Under")
    bt = collect("Both Teams Score")
    pin_mw = pinnacle("Match Winner")

    def best(acc, keys):
        return [max(acc.get(k, [0.0])) for k in keys]

    out: dict = {"books": len(books)}
    if all(k in mw for k in ("Home", "Draw", "Away")):
        out["best_1x2"] = {"HOME": max(mw["Home"]), "DRAW": max(mw["Draw"]),
                           "AWAY": max(mw["Away"])}
    if all(k in pin_mw for k in ("Home", "Draw", "Away")):
        p = _devig([pin_mw["Home"], pin_mw["Draw"], pin_mw["Away"]])
        if len(p) == 3:
            out["pin_1x2"] = {"HOME": pin_mw["Home"], "DRAW": pin_mw["Draw"],
                              "AWAY": pin_mw["Away"]}
            out["pin_p_1x2"] = {"HOME": round(p[0], 4), "DRAW": round(p[1], 4),
                                "AWAY": round(p[2], 4)}
    if "Over 2.5" in ou and "Under 2.5" in ou:
        out["best_ou25"] = {"OVER": max(ou["Over 2.5"]), "UNDER": max(ou["Under 2.5"])}
    if "Yes" in bt and "No" in bt:
        out["best_btts"] = {"YES": max(bt["Yes"]), "NO": max(bt["No"])}
    return out


# ---------------------------------------------------------------- canlı maçlar
_live_cache: list = []
_live_at = [0.0]


_live_all_cache: list[dict] = []
_live_all_at = [0.0]
# canlı yol kendi bütçesi (live=all tek istek; 100s önbellek -> gün ~90 istek)
_live_req = [dt.date.today(), 0]
_LIVE_MAX_DAY = int(os.environ.get("APIFOOTBALL_LIVE_MAX_DAY", "120"))


def _live_budget_ok() -> bool:
    today = dt.date.today()
    if _live_req[0] != today:
        _live_req[0], _live_req[1] = today, 0
    return _live_req[1] < _LIVE_MAX_DAY


def _fetch_live_raw() -> list[dict] | None:
    """/fixtures?live=all — dünyadaki tüm canlı maçlar. 100s önbellek."""
    now = time.monotonic()
    if _live_all_cache and now - _live_all_at[0] < 100:
        return _live_all_cache
    if not enabled() or not _live_budget_ok():
        return _live_all_cache or None
    data = _get("/fixtures", {"live": "all"})
    if data is None:
        return _live_all_cache or None
    _live_req[1] += 1
    rows = []
    for f in data.get("response", []):
        lg = f.get("league", {}) or {}
        fx, tm, go = f["fixture"], f["teams"], f.get("goals", {}) or {}
        st = fx.get("status", {}) or {}
        rows.append({
            "af_id": fx["id"], "af_league_id": lg.get("id"),
            "league_name": lg.get("name") or "", "country": lg.get("country") or "",
            "code": LEAGUE_ID_TO_CODE.get(lg.get("id")),
            "home": tm["home"]["name"], "away": tm["away"]["name"],
            "home_id": tm["home"].get("id"), "away_id": tm["away"].get("id"),
            "hg": go.get("home") or 0, "ag": go.get("away") or 0,
            "minute": st.get("elapsed") or 0, "phase": st.get("short", "1H"),
        })
    _live_all_cache[:] = rows
    _live_all_at[0] = now
    return rows


def live_matches() -> list[dict]:
    """Takip edilen liglerdeki canlı maçlar (model overlay için)."""
    rows = _fetch_live_raw() or []
    return [r for r in rows if r.get("code")]


def live_matches_all() -> list[dict]:
    """Dünyadaki tüm canlı maçlar (lig adı + ülke ile)."""
    return _fetch_live_raw() or []


# ---------------------------------------------------------------- sakatlıklar
def injuries_window(days: int = 3) -> dict[int, dict[int, int]]:
    """af_fixture_id -> {team_id: sakat oyuncu sayısı}."""
    today = dt.datetime.now(dt.timezone.utc).date()
    out: dict[int, dict[int, int]] = {}
    for i in range(days):
        d = (today + dt.timedelta(days=i)).isoformat()
        data = _get("/injuries", {"date": d})
        if not data:
            continue
        for it in data.get("response", []):
            fid = it.get("fixture", {}).get("id")
            tid = it.get("team", {}).get("id")
            if not fid or not tid:
                continue
            out.setdefault(fid, {}).setdefault(tid, 0)
            out[fid][tid] += 1
    return out
