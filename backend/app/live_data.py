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

log = logging.getLogger(__name__)

BASE_URL = "https://api.football-data.org/v4"
DEFAULT_COMPETITIONS = ("PL", "BL1", "SA", "PD", "FL1", "PPL", "ELC", "BSA")

_CACHE_TTL = float(os.environ.get("FOOTBALL_DATA_CACHE_TTL", "120"))
_REQUEST_SPACING = float(os.environ.get("FOOTBALL_DATA_REQUEST_SPACING", "1.5"))
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
_rate_lock = threading.Lock()
_last_request_at = 0.0


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
            matches.append({
                "id": int(item["id"]), "league_id": comp_id,
                "home_team_id": home_id, "away_team_id": away_id,
                "kickoff": item["utcDate"], "status": status,
                "home_goals": full.get("home"), "away_goals": full.get("away"),
                # Ücretsiz kaynakta model parametreleri yok; nötr öncül kullanılır.
                "lambda_home": 1.35, "lambda_away": 1.10, "rho": -0.03,
                "model_confidence": 0.35, "best_edge_pct": None, "has_value": False,
            })

    if not leagues and failed:
        # Hiçbir lig alınamadı: varsa bayat önbelleği ver, yoksa hatayı yükselt.
        if cached:
            return cached[1]
        raise RuntimeError(f"football-data yanıt vermedi: {', '.join(failed)}")

    matches.sort(key=lambda x: x["kickoff"])
    result = {"matches": matches, "leagues": list(leagues.values()), "teams": list(teams.values())}
    with _cache_lock:
        _cache[cache_key] = (time.monotonic(), result)
    return result


def default_analysis(match_id: int) -> dict:
    return {"match_id": match_id, "lambda_home": 1.35, "lambda_away": 1.10,
            "rho": -0.03, "model_confidence": 0.35,
            "context_factors": [], "explanation": {"source": 0.0},
            "quota_remaining": -1}
