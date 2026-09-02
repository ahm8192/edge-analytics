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
# match_id -> son zenginleştirilmiş maç sözlüğü — /analysis metni için
_MATCH_SNAP: dict[int, dict] = {}


def _tempo(lh: float, la: float) -> str:
    t = (lh or 0) + (la or 0)
    if t < 2.3:
        return "düşük"
    if t < 3.0:
        return "orta"
    return "yüksek"


def _conf_word(c: float) -> str:
    if c >= 0.66:
        return "yüksek"
    if c >= 0.45:
        return "orta"
    return "düşük"


def build_narrative(m: dict, home: str, away: str) -> str:
    """Modelin kendi sayılarından Türkçe maç analizi paragrafı üretir.
    LLM yok — modelin gerekçesini düz yazıya döker."""
    ph = m.get("p_home") or 0.34
    pd = m.get("p_draw") or 0.33
    pa = m.get("p_away") or 0.33
    lh = m.get("lambda_home") or 1.35
    la = m.get("lambda_away") or 1.10
    conf = m.get("model_confidence") or 0.4
    lines: list[str] = []

    top = max(ph, pd, pa)
    if top == pd:
        lines.append(
            f"Model beraberliğe %{pd*100:.0f} veriyor; açık favori yok, "
            f"{home} %{ph*100:.0f} · {away} %{pa*100:.0f}.")
    else:
        fav, fp = (home, ph) if ph >= pa else (away, pa)
        oth = f"{home} %{ph*100:.0f} · beraberlik %{pd*100:.0f} · {away} %{pa*100:.0f}"
        lines.append(f"Model {fav} tarafını %{fp*100:.0f} ile öne alıyor. Dağılım: {oth}.")

    lines.append(
        f"Beklenen gol toplamı ~{(lh + la):.1f}; {_tempo(lh, la)} tempolu bir maç. "
        f"2.5 üst %{(m.get('p_over25') or 0.5)*100:.0f}, KG var %{(m.get('p_btts') or 0.5)*100:.0f}.")

    mh, md, ma = m.get("market_home"), m.get("market_draw"), m.get("market_away")
    if mh and md and ma:
        model_pick = "1" if top == ph else ("X" if top == pd else "2")
        mk = {"1": mh, "X": md, "2": ma}[model_pick]
        diff = top - mk
        if abs(diff) < 0.03:
            lines.append(
                f"Piyasa da aynı yönde (adil %{mk*100:.0f}) — model burada piyasadan "
                f"anlamlı ayrışmıyor.")
        else:
            yön = "daha olası" if diff > 0 else "daha az olası"
            lines.append(
                f"Piyasa bu sonucu %{mk*100:.0f} fiyatlıyor; model {yön} görüyor "
                f"(%{top*100:.0f}).")

    if m.get("has_value") and m.get("best_edge_pct") and m.get("best_odds"):
        sel = {"HOME": "ev sahibi", "DRAW": "beraberlik", "AWAY": "deplasman"}.get(
            m.get("best_edge_sel", ""), m.get("best_edge_sel", ""))
        lines.append(
            f"Değer {sel} tarafında: en iyi {m['best_odds']:.2f} oranı Pinnacle'ın "
            f"adil fiyatını +%{m['best_edge_pct']*100:.1f} geçiyor. Oran avı — "
            f"model piyasayı yenmiyor, sadece daha iyi fiyat buluyor.")
    else:
        lines.append("Oynanabilir bir fiyat farkı yok; beklemede kal.")

    ih, ia = m.get("injuries_home") or 0, m.get("injuries_away") or 0
    n = max(ih, ia)
    if 2 <= n <= 6:  # 6 üstü genelde veri gürültüsü, metne koyma
        who = home if ih >= ia else away
        lines.append(f"{who} kadrosunda {n} önemli eksik var; hücum beklentisi buna göre kısıldı.")

    lines.append(
        f"Model güveni {_conf_word(conf)}. Tek maç sonucu şansa açık — anlamlı sinyal "
        f"yüzlerce bahis sonrasında ortaya çıkar, tek maça göre kasa ayarlama.")
    return " ".join(lines)


def build_live_narrative(m: dict, home: str, away: str) -> str:
    mn = m.get("minute") or 0
    hg = m.get("home_goals") or 0
    ag = m.get("away_goals") or 0
    ph = m.get("p_home") or 0.34
    pd = m.get("p_draw") or 0.33
    pa = m.get("p_away") or 0.33
    top = max(ph, pd, pa)
    sel = home if top == ph else ("beraberlik" if top == pd else away)
    rem = max(0, 95 - mn)
    return (
        f"Dakika {mn}, skor {hg}–{ag}. Kalan ~{rem} dakikada model {sel} sonucuna "
        f"%{top*100:.0f} veriyor ({home} %{ph*100:.0f} · X %{pd*100:.0f} · "
        f"{away} %{pa*100:.0f}). 2.5 üst %{(m.get('p_over25') or 0.4)*100:.0f}. "
        f"Skor değiştikçe bu oranlar hızla kayar; canlı bahiste sadece net bir "
        f"fiyat farkı görürsen gir.")


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

    _enrich(matches, teams, list(competitions))
    _enrich_live(matches, teams)
    _append_live_extras(matches, leagues, teams)

    # /analysis metni için son durumu sakla (prose'da kısa ad daha okunur)
    _tn = {t["id"]: (t.get("short_name") or t.get("name") or "") for t in teams.values()}
    for _m in matches:
        _MATCH_SNAP[int(_m["id"])] = {
            "home": _tn.get(_m["home_team_id"], ""), "away": _tn.get(_m["away_team_id"], ""),
            **{k: _m.get(k) for k in (
                "p_home", "p_draw", "p_away", "p_over25", "p_btts",
                "lambda_home", "lambda_away", "model_confidence",
                "market_home", "market_draw", "market_away",
                "best_edge_pct", "best_edge_sel", "best_odds", "has_value",
                "injuries_home", "injuries_away", "status", "minute",
                "home_goals", "away_goals")},
        }

    # Canlı maçlar en üstte, sonra başlama saatine göre
    matches.sort(key=lambda x: (0 if x["status"] == "LIVE" else 1, x["kickoff"]))
    result = {"matches": matches, "leagues": list(leagues.values()), "teams": list(teams.values())}
    with _cache_lock:
        _cache[cache_key] = (time.monotonic(), result)
    return result


_BR = {  # football-data.org tam adı (normalize) -> yaygın kısa ad
    "queens park rangers": "qpr", "west bromwich albion": "west brom",
    "sheffield wednesday": "sheffield weds", "wolverhampton wanderers": "wolves",
    "brighton hove albion": "brighton", "tottenham hotspur": "tottenham",
    "manchester united": "manchester utd", "newcastle united": "newcastle",
    "west ham united": "west ham", "leeds united": "leeds",
    "afc bournemouth": "bournemouth", "1 fc koln": "koln",
    "bayer 04 leverkusen": "bayer leverkusen", "1 fsv mainz 05": "mainz",
    "rc celta de vigo": "celta vigo", "club atletico de madrid": "atletico madrid",
    "real betis balompie": "real betis", "rcd espanyol de barcelona": "espanyol",
    "borussia monchengladbach": "monchengladbach", "eintracht frankfurt": "eintracht frankfurt",
}


def _keyify(s: str) -> str:
    from .model import _norm
    n = _norm(s)
    return _BR.get(n, n)


def _enrich(matches: list[dict], teams: dict[int, dict], competitions: list[str]) -> None:
    """Yaklaşan maçları oran + sakatlık ile zenginleştir: Pinnacle referansı + +EV."""
    import difflib

    # 1) Oranlar — The Odds API (tam fikstür) birincil
    odx: dict = {}
    try:
        from . import theoddsapi as toa
        if toa.enabled():
            for row in toa.odds_rows(competitions):
                odx[(_keyify(row["home"]), _keyify(row["away"]), row["date"])] = row
    except Exception:
        odx = {}

    # 2) Sakatlıklar — API-Football (dar pencere), best-effort
    injw: dict = {}
    af_idx: dict = {}
    try:
        from . import apifootball as af
        if af.enabled():
            for fx in af.fixtures_window(3):
                af_idx[(_keyify(fx["home"]), _keyify(fx["away"]), fx["date"])] = fx
            injw = af.injuries_window(3)
    except Exception:
        injw, af_idx = {}, {}

    if not odx and not injw:
        return

    odx_by_date: dict[str, list] = {}
    for (h, a, d), v in odx.items():
        odx_by_date.setdefault(d, []).append((h, a, v))

    def find_odds(hk: str, ak: str, d: str):
        exact = odx.get((hk, ak, d))
        if exact:
            return exact
        best, sc = None, 0.0
        for h, a, v in odx_by_date.get(d, []):
            s = (difflib.SequenceMatcher(None, hk, h).ratio()
                 + difflib.SequenceMatcher(None, ak, a).ratio()) / 2
            if s > sc:
                best, sc = v, s
        return best if sc >= 0.78 else None

    for m in matches:
        th = teams.get(m["home_team_id"], {})
        ta = teams.get(m["away_team_id"], {})
        d = m["kickoff"][:10]
        hk, ak = _keyify(th.get("name", "")), _keyify(ta.get("name", ""))
        code, hn, an = _MATCH_CTX.get(m["id"], (None, th.get("name"), ta.get("name")))

        # sakatlık
        ih = ia = 0
        af_fx = af_idx.get((hk, ak, d))
        if af_fx:
            inj = injw.get(af_fx["af_id"], {})
            # API-Football bazen pencere içi tüm kayıtları sayıyor -> 4 ile sınırla
            ih = min(int(inj.get(af_fx.get("home_id"), 0) or 0), 4)
            ia = min(int(inj.get(af_fx.get("away_id"), 0) or 0), 4)
            if code and (ih >= 2 or ia >= 2):
                p = model.probs(code, hn, an, inj_home=ih, inj_away=ia)
                m.update({"p_home": p["p_home"], "p_draw": p["p_draw"], "p_away": p["p_away"],
                          "p_over25": p["p_over25"], "p_btts": p["p_btts"],
                          "lambda_home": p["lambda_home"], "lambda_away": p["lambda_away"]})
        m["injuries_home"], m["injuries_away"] = int(ih), int(ia)

        # oran + edge
        od = find_odds(hk, ak, d)
        if not od:
            continue
        _MATCH_ODDS[m["id"]] = od
        if "pin_1x2" in od:
            m["pinnacle_home"] = od["pin_1x2"]["HOME"]
            m["pinnacle_draw"] = od["pin_1x2"]["DRAW"]
            m["pinnacle_away"] = od["pin_1x2"]["AWAY"]

        mp = od.get("pin_p_1x2")
        if mp:
            m["market_home"] = mp["HOME"]
            m["market_draw"] = mp["DRAW"]
            m["market_away"] = mp["AWAY"]
            # Modelimiz kapanış oranını geçmiyor -> servis edilen olasılık
            # %22 model + %78 piyasa. Modelin leanı görünür ama abartıya kaçmaz;
            # ayrışma büyükse (kötü takım reytingi) bile makul kenar üretir.
            w = 0.22
            ph = w * m["p_home"] + (1 - w) * mp["HOME"]
            pd_ = w * m["p_draw"] + (1 - w) * mp["DRAW"]
            pa = w * m["p_away"] + (1 - w) * mp["AWAY"]
            s = ph + pd_ + pa
            m["p_home"], m["p_draw"], m["p_away"] = round(ph / s, 4), round(pd_ / s, 4), round(pa / s, 4)

        b = od.get("best_1x2")
        if b and mp:
            # +EV = en iyi oran, Pinnacle'ın adil fiyatını geçiyor mu (oran avı)
            shop = {k: b[k] * mp[k] - 1.0 for k in ("HOME", "DRAW", "AWAY")
                    if b.get(k) and mp.get(k)}
            if shop:
                sel = max(shop, key=shop.get)
                e = shop[sel]
                if 0.005 < e < 0.15:  # gerçekçi bant; üstü veri/eşleşme hatası
                    m["best_edge_pct"] = round(e, 4)
                    m["best_edge_sel"] = sel
                    m["best_odds"] = round(b[sel], 2)
                    # >%3: gürültü/bayat çizgi payını düşer, gerçekten oynanabilir
                    m["has_value"] = e > 0.03


def _append_live_extras(matches: list[dict], leagues: dict[int, dict],
                        teams: dict[int, dict]) -> None:
    """football-data'da olmayan (tüm dünya) canlı maçları listeye ekler.
    Model kalibre olan liglerde maç-içi olasılık da hesaplanır; değilse sadece skor."""
    try:
        from . import apifootball as af
        rows = af.live_matches_all()
    except Exception:
        return
    if not rows:
        return
    have = {
        (_keyify(teams.get(m["home_team_id"], {}).get("name", "")),
         _keyify(teams.get(m["away_team_id"], {}).get("name", "")))
        for m in matches
    }
    # saygın ligler + model kalibre olanlar; 3./4. lig vb. elenir
    try:
        from .apifootball import LIVE_ALLOW
    except Exception:
        LIVE_ALLOW = set()
    rows = [r for r in rows if r.get("code") or r.get("af_league_id") in LIVE_ALLOW]
    rows = sorted(rows, key=lambda r: (0 if r.get("code") else 1, r.get("league_name") or ""))
    added = 0
    for r in rows:
        if added >= 30:
            break
        key = (_keyify(r["home"]), _keyify(r["away"]))
        if key in have:
            continue
        have.add(key)
        added += 1
        mid = 900_000_000 + int(r["af_id"])
        lg_id = 800_000 + int(r.get("af_league_id") or 0)
        if lg_id not in leagues:
            nm = r.get("league_name") or "Canlı"
            co = r.get("country") or ""
            leagues[lg_id] = {
                "id": lg_id, "name": (f"{nm} · {co}" if co and co not in nm else nm),
                "country": co, "tier": 3, "data_quality": 0.4, "strength_coef": 1.0,
            }
        ht = 700_000_000 + (int(r["home_id"]) if r.get("home_id")
                            else abs(hash(r["home"])) % 5_000_000)
        at = 700_000_000 + (int(r["away_id"]) if r.get("away_id")
                            else abs(hash(r["away"])) % 5_000_000)
        teams.setdefault(ht, {"id": ht, "name": r["home"], "short_name": r["home"],
                              "crest_url": None})
        teams.setdefault(at, {"id": at, "name": r["away"], "short_name": r["away"],
                              "crest_url": None})
        d = {
            "id": mid, "league_id": lg_id, "home_team_id": ht, "away_team_id": at,
            "kickoff": dt.datetime.now(dt.timezone.utc).isoformat(), "status": "LIVE",
            "home_goals": r["hg"], "away_goals": r["ag"], "minute": r["minute"],
            "rho": -0.03, "model_confidence": 0.30,
            "lambda_home": None, "lambda_away": None,
            "p_home": None, "p_draw": None, "p_away": None,
            "p_over25": None, "p_btts": None,
            "best_edge_pct": None, "best_edge_sel": None, "best_odds": None,
            "has_value": False, "injuries_home": 0, "injuries_away": 0,
        }
        code = r.get("code")
        if code:
            try:
                ip = model.inplay(code, r["home"], r["away"],
                                  r["hg"], r["ag"], r["minute"])
                d.update(
                    lambda_home=ip.get("lambda_home"), lambda_away=ip.get("lambda_away"),
                    p_home=ip["p_home"], p_draw=ip["p_draw"], p_away=ip["p_away"],
                    p_over25=ip.get("p_over25"), model_confidence=0.50,
                )
                _MATCH_CTX[mid] = (code, r["home"], r["away"])
            except Exception:
                pass
        matches.append(d)


def _enrich_live(matches: list[dict], teams: dict[int, dict]) -> None:
    """Oynanan maçlara canlı skor + dakika + maç-içi olasılık ekler."""
    try:
        from . import apifootball as af
        if not af.enabled():
            return
        lm = af.live_matches()
    except Exception:
        return
    if not lm:
        return
    idx = {(_keyify(x["home"]), _keyify(x["away"])): x for x in lm}
    for m in matches:
        th = teams.get(m["home_team_id"], {})
        ta = teams.get(m["away_team_id"], {})
        live = idx.get((_keyify(th.get("name", "")), _keyify(ta.get("name", ""))))
        if not live:
            continue
        code, hn, an = _MATCH_CTX.get(m["id"], (None, th.get("name"), ta.get("name")))
        m["status"] = "LIVE"
        m["home_goals"] = live["hg"]
        m["away_goals"] = live["ag"]
        m["minute"] = live["minute"]
        if code:
            ip = model.inplay(code, hn, an, live["hg"], live["ag"], live["minute"])
            m["p_home"], m["p_draw"], m["p_away"] = ip["p_home"], ip["p_draw"], ip["p_away"]
            m["p_over25"] = ip["p_over25"]
            m["model_confidence"] = min(0.85, (m.get("model_confidence") or 0.5) + 0.15)


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

    snap = _MATCH_SNAP.get(int(match_id))
    if snap:
        hn = snap.get("home") or home
        an = snap.get("away") or away
        try:
            out["summary"] = build_narrative(snap, hn, an)
            if snap.get("status") == "LIVE":
                out["live_summary"] = build_live_narrative(snap, hn, an)
        except Exception:  # metin üretimi asla /analysis'i düşürmesin
            pass
    return out
