"""football-data.org ücretsiz plan adaptörü.

Token yalnızca FOOTBALL_DATA_TOKEN ortam değişkeninden okunur; APK'ya gömülmez.
Ücretsiz plan dakikada ~10 istek verir; sonuçlar kısa süre önbelleğe alınır ve
her competition isteği arasında minik bir bekleme konur ki limit aşılmasın.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import model

log = logging.getLogger(__name__)

BASE_URL = "https://api.football-data.org/v4"
DEFAULT_COMPETITIONS = ("PL", "BL1", "SA", "PD", "FL1", "PPL", "ELC", "BSA")

_CACHE_TTL = float(os.environ.get("FOOTBALL_DATA_CACHE_TTL", "120"))
_REQUEST_SPACING = float(os.environ.get("FOOTBALL_DATA_REQUEST_SPACING", "1.5"))
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
_rate_lock = threading.Lock()
_last_request_at = 0.0


# match_id -> (competition_code, home_name, away_name) — /analysis için
_MATCH_CTX: dict[int, tuple[str, str, str]] = {}
# match_id -> API-Football oran bloğu — /odds için
_MATCH_ODDS: dict[int, dict] = {}


def match_odds(match_id: int) -> dict:
    """Yakın maçlarda API-Football'dan gelen oranlar (yoksa boş)."""
    od = _MATCH_ODDS.get(int(match_id))
    if not od:
        return {"quotes": []}
    quotes = []
    if "pin_1x2" in od:
        p = od["pin_1x2"]
        quotes.append({"bookmaker": "Pinnacle", "market": "1X2",
                       "prices": {"HOME": p["HOME"], "DRAW": p["DRAW"], "AWAY": p["AWAY"]},
                       "captured_at": "", "is_closing": False, "is_sharp": True})
    if "best_1x2" in od:
        b = od["best_1x2"]
        quotes.append({"bookmaker": "En iyi", "market": "1X2",
                       "prices": {"HOME": b["HOME"], "DRAW": b["DRAW"], "AWAY": b["AWAY"]},
                       "captured_at": "", "is_closing": False, "is_sharp": False})
    if "best_ou25" in od:
        b = od["best_ou25"]
        quotes.append({"bookmaker": "En iyi", "market": "OU", "line": 2.5,
                       "prices": {"OVER": b["OVER"], "UNDER": b["UNDER"]},
                       "captured_at": "", "is_closing": False, "is_sharp": False})
    return {"quotes": quotes}


def _throttle() -> None:
    """İki football-data isteği arasında en az _REQUEST_SPACING saniye bırakır."""
    global _last_request_at
    with _rate_lock:
        wait = _REQUEST_SPACING - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def _get(path: str, params: dict[str, str], *, retries: int = 2) -> dict:
    token = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
    if not token:
        raise RuntimeError("FOOTBALL_DATA_TOKEN tanımlı değil")
    url = f"{BASE_URL}{path}?{urlencode(params)}"
    req = Request(url, headers={"X-Auth-Token": token, "Accept": "application/json"})
    for attempt in range(retries + 1):
        _throttle()
        try:
            with urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429 and attempt < retries:
                reset = exc.headers.get("X-RequestCounter-Reset") or exc.headers.get("Retry-After")
                delay = 8.0
                try:
                    if reset:
                        delay = min(float(reset) + 1.0, 30.0)
                except (TypeError, ValueError):
                    pass
                log.warning("football-data 429; %.0f sn bekleniyor (deneme %d)", delay, attempt + 1)
                time.sleep(delay)
                continue
            raise
    raise RuntimeError("football-data isteği tekrar tekrar 429 döndürdü")


def _iso_date(value: str, fallback: dt.date) -> str:
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except (TypeError, ValueError):
        return fallback.isoformat()


def fetch_matches(date_from: str, date_to: str, competitions: tuple[str, ...] | None = None) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    if competitions is None:
        configured = os.environ.get("FOOTBALL_DATA_COMPETITIONS", "").strip()
        competitions = tuple(x.strip().upper() for x in configured.split(",") if x.strip()) or DEFAULT_COMPETITIONS
    default_from = now.date()
    default_to = default_from + dt.timedelta(days=7)
    start = _iso_date(date_from, default_from)
    end = _iso_date(date_to, default_to)

    cache_key = f"{start}|{end}|{','.join(competitions)}"
    with _cache_lock:
        cached = _cache.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL:
        return cached[1]

    matches: list[dict] = []
    leagues: dict[int, dict] = {}
    teams: dict[int, dict] = {}
    failed: list[str] = []

    for code in competitions:
        try:
            payload = _get(f"/competitions/{code}/matches", {"dateFrom": start, "dateTo": end})
        except (HTTPError, URLError, RuntimeError, TimeoutError) as exc:
            # Tek lig hata verdiyse tüm yanıtı çöpe atma; onu atla, gerisini döndür.
            log.warning("competition %s alınamadı: %s", code, exc)
            failed.append(code)
            continue
        competition = payload.get("competition") or {}
        comp_id = int(competition.get("id", abs(hash(code)) % 2_000_000))
        area = competition.get("area") or {}
        leagues[comp_id] = {
            "id": comp_id,
            "name": competition.get("name", code),
            "country": area.get("name", ""),
            "tier": 1,
            "data_quality": 1.0,
            "strength_coef": 1.0,
        }
        for item in payload.get("matches", []):
            home = item.get("homeTeam") or {}
            away = item.get("awayTeam") or {}
            if not home.get("id") or not away.get("id") or not item.get("utcDate"):
                continue
            home_id, away_id = int(home["id"]), int(away["id"])
            teams[home_id] = {"id": home_id, "name": home.get("name", ""),
                              "short_name": home.get("shortName") or home.get("tla") or home.get("name", ""),
                              "crest_url": home.get("crest")}
            teams[away_id] = {"id": away_id, "name": away.get("name", ""),
                              "short_name": away.get("shortName") or away.get("tla") or away.get("name", ""),
                              "crest_url": away.get("crest")}
            score = item.get("score") or {}
            full = score.get("fullTime") or {}
            raw_status = str(item.get("status", "SCHEDULED")).upper()
            status = {
                "TIMED": "SCHEDULED", "IN_PLAY": "LIVE", "PAUSED": "LIVE",
                "SUSPENDED": "LIVE", "AWARDED": "FINISHED", "CANCELED": "POSTPONED",
            }.get(raw_status, raw_status if raw_status in {"SCHEDULED", "LIVE", "FINISHED", "POSTPONED"} else "SCHEDULED")
            pred = model.probs(code, home.get("name", ""), away.get("name", ""))
            _MATCH_CTX[int(item["id"])] = (code, home.get("name", ""), away.get("name", ""))
            matches.append({
                "id": int(item["id"]), "league_id": comp_id,
                "home_team_id": home_id, "away_team_id": away_id,
                "kickoff": item["utcDate"], "status": status,
                "home_goals": full.get("home"), "away_goals": full.get("away"),
                # Takıma özel, kalibre Dixon-Coles (app/model_data/params.json)
                "lambda_home": pred["lambda_home"], "lambda_away": pred["lambda_away"],
                "rho": pred["rho"], "model_confidence": pred["model_confidence"],
                "p_home": pred["p_home"], "p_draw": pred["p_draw"], "p_away": pred["p_away"],
                "p_over25": pred["p_over25"], "p_btts": pred["p_btts"],
                "best_edge_pct": None, "has_value": False,
            })

    if not leagues and failed:
        # Hiçbir lig alınamadı: varsa bayat önbelleği ver, yoksa hatayı yükselt.
        if cached:
            return cached[1]
        raise RuntimeError(f"football-data yanıt vermedi: {', '.join(failed)}")

    _enrich(matches, teams)

    matches.sort(key=lambda x: x["kickoff"])
    result = {"matches": matches, "leagues": list(leagues.values()), "teams": list(teams.values())}
    with _cache_lock:
        _cache[cache_key] = (time.monotonic(), result)
    return result


def _enrich(matches: list[dict], teams: dict[int, dict]) -> None:
    """Yakın maçları API-Football ile zenginleştir: Pinnacle + sakatlık + +EV."""
    try:
        from . import apifootball as af
    except Exception:
        return
    if not af.enabled():
        return
    try:
        fixw = af.fixtures_window(3)
        injw = af.injuries_window(3)
    except Exception:
        return
    if not fixw:
        return

    import difflib

    from .model import _norm  # aynı isim normalizasyonu

    # football-data.org tam adı (normalize) -> API-Football yaygın adı (normalize)
    _BR = {
        "queens park rangers": "qpr", "west bromwich albion": "west brom",
        "sheffield wednesday": "sheffield weds", "wolverhampton wanderers": "wolves",
        "brighton hove albion": "brighton", "tottenham hotspur": "tottenham",
        "manchester united": "manchester utd", "newcastle united": "newcastle",
        "nottingham forest": "nottingham forest", "west ham united": "west ham",
        "leeds united": "leeds", "afc bournemouth": "bournemouth",
        "borussia monchengladbach": "borussia monchengladbach",
        "1 fc koln": "fc koln", "bayer 04 leverkusen": "bayer leverkusen",
        "1 fsv mainz 05": "mainz 05", "rc celta de vigo": "celta vigo",
        "club atletico de madrid": "atletico madrid", "athletic club": "athletic club",
        "real betis balompie": "real betis", "rcd espanyol de barcelona": "espanyol",
    }

    def keyify(s: str) -> str:
        n = _norm(s)
        return _BR.get(n, n)

    by_date: dict[str, list] = {}
    for fx in fixw:
        by_date.setdefault(fx["date"], []).append(fx)

    def find(hn: str, an: str, d: str):
        cands = by_date.get(d, [])
        h, a = keyify(hn), keyify(an)
        for fx in cands:
            if keyify(fx["home"]) == h and keyify(fx["away"]) == a:
                return fx
        best, bestsc = None, 0.0
        for fx in cands:
            sc = (difflib.SequenceMatcher(None, h, keyify(fx["home"])).ratio()
                  + difflib.SequenceMatcher(None, a, keyify(fx["away"])).ratio()) / 2
            if sc > bestsc:
                best, bestsc = fx, sc
        return best if bestsc >= 0.70 else None

    for m in matches:
        th = teams.get(m["home_team_id"], {})
        ta = teams.get(m["away_team_id"], {})
        d = m["kickoff"][:10]
        fx = find(th.get("name", ""), ta.get("name", ""), d)
        if fx is None:
            continue

        inj = injw.get(fx["af_id"], {})
        ih = inj.get(fx.get("home_id"), 0)
        ia = inj.get(fx.get("away_id"), 0)
        code, hn, an = _MATCH_CTX.get(m["id"], (None, th.get("name"), ta.get("name")))
        if code and (ih or ia):
            p = model.probs(code, hn, an, inj_home=ih, inj_away=ia)
            m.update({"p_home": p["p_home"], "p_draw": p["p_draw"], "p_away": p["p_away"],
                      "p_over25": p["p_over25"], "p_btts": p["p_btts"],
                      "lambda_home": p["lambda_home"], "lambda_away": p["lambda_away"]})
        m["injuries_home"], m["injuries_away"] = int(ih), int(ia)

        od = None
        try:
            od = af.odds_for_fixture(fx["af_id"])
        except Exception:
            od = None
        if not od:
            continue
        _MATCH_ODDS[m["id"]] = od
        if "pin_1x2" in od:
            m["pinnacle_home"] = od["pin_1x2"]["HOME"]
            m["pinnacle_draw"] = od["pin_1x2"]["DRAW"]
            m["pinnacle_away"] = od["pin_1x2"]["AWAY"]
        if "pin_p_1x2" in od:
            m["market_home"] = od["pin_p_1x2"]["HOME"]
            m["market_draw"] = od["pin_p_1x2"]["DRAW"]
            m["market_away"] = od["pin_p_1x2"]["AWAY"]
        if "best_1x2" in od:
            b = od["best_1x2"]
            pm = {"HOME": m["p_home"], "DRAW": m["p_draw"], "AWAY": m["p_away"]}
            edges = {k: pm[k] * b[k] - 1.0 for k in ("HOME", "DRAW", "AWAY") if b.get(k)}
            if edges:
                sel = max(edges, key=edges.get)
                m["best_edge_pct"] = round(edges[sel], 4)
                m["best_edge_sel"] = sel
                m["best_odds"] = round(b[sel], 2)
                m["has_value"] = edges[sel] > 0.03


def default_analysis(match_id: int) -> dict:
    ctx = _MATCH_CTX.get(int(match_id))
    if ctx is None:
        return {"match_id": match_id, "lambda_home": 1.35, "lambda_away": 1.10,
                "rho": -0.03, "model_confidence": 0.30,
                "context_factors": [], "explanation": {}, "quota_remaining": -1}
    code, home, away = ctx
    out = model.explain(code, home, away)
    out["match_id"] = int(match_id)
    out["quota_remaining"] = -1
    return out
