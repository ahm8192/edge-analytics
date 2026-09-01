"""
HTTP tabanlı sağlayıcılar için ortak taban.

Somut sağlayıcı yazarken bundan türet; sadece endpoint yollarını ve
alan eşlemesini yazman yeterli olur.
"""
from __future__ import annotations
import datetime as dt
import logging
from typing import Any, Iterable

import requests

from .base import Provider, RawRecord, with_retry

log = logging.getLogger(__name__)


class HttpProvider(Provider):
    base_url: str = ""
    auth_style: str = "header"        # header | query
    auth_key_name: str = "X-Api-Key"

    def __init__(self, api_key: str | None = None,
                 rate_limit: tuple[int, float] = (60, 60.0),
                 timeout: float = 12.0):
        super().__init__(api_key, rate_limit)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "edge-analytics/0.1"

    def get(self, path: str, params: dict | None = None) -> Any:
        self.limiter.acquire()
        params = dict(params or {})
        headers = {}
        if self.api_key:
            if self.auth_style == "header":
                headers[self.auth_key_name] = self.api_key
            else:
                params[self.auth_key_name] = self.api_key

        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

        def call():
            r = self.session.get(url, params=params, headers=headers,
                                 timeout=self.timeout)
            self._call_count += 1
            if r.status_code == 429:
                # Sağlayıcı sınırı: Retry-After'a saygı göster
                wait = int(r.headers.get("Retry-After", "5"))
                log.warning("%s 429 — %s sn bekleniyor", self.code, wait)
                raise TimeoutError(f"rate limited, retry after {wait}")
            if r.status_code >= 500:
                raise ConnectionError(f"{self.code} {r.status_code}")
            r.raise_for_status()
            return r.json()

        try:
            return with_retry(call)
        except Exception:
            self._error_count += 1
            raise


class GenericStatsProvider(HttpProvider):
    """
    Örnek istatistik sağlayıcı adaptörü.

    ÖNEMLİ: alan adları temsilidir. Kendi sağlayıcının dökümanına bakıp
    FIELD_MAP'i düzelt — kodun geri kalanına dokunman gerekmez.
    """
    code = "stats_primary"
    base_url = "https://api.example-stats.com/v3"
    trust_weight = 1.0

    FIELD_MAP = {
        "match_id": "id",
        "kickoff": "utcDate",
        "home_name": "homeTeam.name",
        "away_name": "awayTeam.name",
        "home_id": "homeTeam.id",
        "away_id": "awayTeam.id",
        "status": "status",
        "home_goals": "score.fullTime.home",
        "away_goals": "score.fullTime.away",
    }

    SHOT_MAP = {
        "minute": "minute", "x": "location.x", "y": "location.y",
        "xg": "shot.statsbomb_xg", "is_goal": "shot.outcome.is_goal",
        "is_penalty": "shot.type.is_penalty",
        "is_set_piece": "shot.type.is_set_piece",
        "team_id": "team.id", "player_id": "player.id",
    }

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        from .base import ProviderCapabilities
        self.capabilities = ProviderCapabilities(
            matches=True, shot_events=True, xg=True, lineups=True,
            injuries=True, typical_delay_minutes=5,
            xg_model_name="provider_v3")

    def fetch_matches(self, date_from: dt.date,
                      date_to: dt.date) -> Iterable[RawRecord]:
        data = self.get("/matches", {"dateFrom": date_from.isoformat(),
                                     "dateTo": date_to.isoformat()})
        for m in data.get("matches", []):
            yield self._record("match", _dig(m, self.FIELD_MAP["match_id"]), m)

    def fetch_shot_events(self, external_match_id: str) -> Iterable[RawRecord]:
        data = self.get(f"/matches/{external_match_id}/events",
                        {"type": "shot"})
        for e in data.get("events", []):
            yield self._record("shot", f"{external_match_id}:{e.get('id')}", e)

    def fetch_lineups(self, external_match_id: str) -> Iterable[RawRecord]:
        data = self.get(f"/matches/{external_match_id}/lineups")
        for side in ("home", "away"):
            for p in data.get(side, {}).get("players", []):
                yield self._record("lineup", f"{external_match_id}:{p.get('id')}",
                                   {**p, "side": side})

    def fetch_injuries(self, external_team_id: str) -> Iterable[RawRecord]:
        data = self.get(f"/teams/{external_team_id}/injuries")
        for n in data.get("injuries", []):
            yield self._record("news", f"{external_team_id}:{n.get('id')}", n)

    def normalize_match(self, raw: RawRecord) -> dict:
        p = raw.payload
        f = self.FIELD_MAP
        return {
            "external_id": str(_dig(p, f["match_id"])),
            "kickoff_utc": _dig(p, f["kickoff"]),
            "home_external_id": str(_dig(p, f["home_id"])),
            "away_external_id": str(_dig(p, f["away_id"])),
            "home_raw_name": _dig(p, f["home_name"]),
            "away_raw_name": _dig(p, f["away_name"]),
            "status": _map_status(_dig(p, f["status"])),
            "home_goals": _dig(p, f["home_goals"]),
            "away_goals": _dig(p, f["away_goals"]),
        }

    def normalize_shot(self, raw: RawRecord) -> dict:
        p, m = raw.payload, self.SHOT_MAP
        return {
            "minute": _dig(p, m["minute"]),
            "x": _dig(p, m["x"]), "y": _dig(p, m["y"]),
            "xg": _dig(p, m["xg"]),
            "xg_model_version": self.capabilities.xg_model_name,
            "is_goal": int(bool(_dig(p, m["is_goal"]))),
            "is_penalty": int(bool(_dig(p, m["is_penalty"]))),
            "is_set_piece": int(bool(_dig(p, m["is_set_piece"]))),
            "team_external_id": str(_dig(p, m["team_id"])),
            "player_external_id": str(_dig(p, m["player_id"])),
        }


class GenericOddsProvider(HttpProvider):
    """Örnek oran sağlayıcı adaptörü."""
    code = "odds_primary"
    base_url = "https://api.example-odds.com/v4"
    auth_style = "query"
    auth_key_name = "apiKey"
    trust_weight = 1.0

    MARKET_MAP = {"h2h": "1X2", "totals": "OU", "spreads": "AH"}
    SELECTION_MAP = {"home": "HOME", "draw": "DRAW", "away": "AWAY",
                     "over": "OVER", "under": "UNDER"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        from .base import ProviderCapabilities
        self.capabilities = ProviderCapabilities(
            odds=True, odds_history=True, live=True, typical_delay_minutes=1)

    def fetch_matches(self, date_from, date_to):
        return []          # oran sağlayıcısı maç kaynağı değildir

    def fetch_odds(self, external_match_id: str,
                   markets: list[str]) -> Iterable[RawRecord]:
        data = self.get(f"/events/{external_match_id}/odds",
                        {"markets": ",".join(markets), "oddsFormat": "decimal"})
        for book in data.get("bookmakers", []):
            yield self._record("odds", f"{external_match_id}:{book.get('key')}", book)

    def normalize_match(self, raw: RawRecord) -> dict:
        raise NotImplementedError

    def normalize_odds(self, raw: RawRecord) -> dict:
        b = raw.payload
        out = []
        for mk in b.get("markets", []):
            market = self.MARKET_MAP.get(mk.get("key"), mk.get("key"))
            for o in mk.get("outcomes", []):
                sel = self.SELECTION_MAP.get(
                    str(o.get("name", "")).lower(), str(o.get("name")).upper())
                out.append({"market": market, "selection": sel,
                            "line": o.get("point"), "price": o.get("price")})
        return {"bookmaker_code": b.get("key"),
                "captured_at": raw.observed_at.isoformat(),
                "quotes": out}


def _dig(d: dict, path: str):
    """Noktalı yol ile iç içe sözlükten değer okur: 'score.fullTime.home'."""
    cur: Any = d
    for part in path.split("."):
        if cur is None:
            return None
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def _map_status(s: str | None) -> str:
    return {"SCHEDULED": "scheduled", "TIMED": "scheduled", "IN_PLAY": "live",
            "PAUSED": "live", "FINISHED": "finished",
            "POSTPONED": "postponed"}.get(str(s).upper(), "scheduled")
