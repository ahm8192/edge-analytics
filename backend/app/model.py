"""Canlı tahmin — app/model_data/params.json'dan takıma özel gol beklentisi.

football-data.org fikstürü + bu parametreler -> her maç için gerçek 1X2.
DB/ağ yok. Takım adı eşleme: alias tablosu + normalize + bulanık eşleşme.
"""
from __future__ import annotations

import difflib
import json
import math
import os
import unicodedata

_PATH = os.path.join(os.path.dirname(__file__), "model_data", "params.json")

try:
    with open(_PATH, encoding="utf-8") as f:
        _P = json.load(f)
except (OSError, ValueError):
    _P = {"leagues": {}, "by_code": {}}

_LEAGUES: dict = _P.get("leagues", {})
# by_code: {"PL": "Premier League", ...}
_CODE_TO_LEAGUE: dict = _P.get("by_code", {})

# football-data.org competition kodu -> veri setindeki lig adı (by_code'u tamamlar)
_CODE_MAP = {
    "PL": "Premier League", "ELC": "Championship",
    "BL1": "Bundesliga", "SA": "Serie A", "PD": "La Liga",
    "FL1": "Ligue 1", "DED": "Eredivisie", "PPL": "Primeira Liga",
    "BSA": "Serie A (BRA)", "PPL2": "Primeira Liga",
}
for _c, _l in _CODE_MAP.items():
    _CODE_TO_LEAGUE.setdefault(_c, _l)

# football-data.org adı -> veri setindeki kısa ad (normalize sonrası eşleşmeyenler)
_ALIAS = {
    # Premier League
    "manchester city": "Man City", "manchester united": "Man United",
    "nottingham forest": "Nott'm Forest", "tottenham hotspur": "Tottenham",
    "wolverhampton wanderers": "Wolves", "brighton hove albion": "Brighton",
    "west ham united": "West Ham", "newcastle united": "Newcastle",
    "leeds united": "Leeds", "afc bournemouth": "Bournemouth",
    "sheffield united": "Sheffield United", "leicester city": "Leicester",
    "ipswich town": "Ipswich", "luton town": "Luton",
    # Bundesliga
    "eintracht frankfurt": "Ein Frankfurt", "borussia monchengladbach": "M'gladbach",
    "borussia dortmund": "Dortmund", "bayer 04 leverkusen": "Leverkusen",
    "bayern munchen": "Bayern Munich", "fc bayern munchen": "Bayern Munich",
    "1 fc koln": "FC Koln", "fc koln": "FC Koln", "1 fc union berlin": "Union Berlin",
    "vfb stuttgart": "Stuttgart", "vfl wolfsburg": "Wolfsburg",
    "tsg 1899 hoffenheim": "Hoffenheim", "sc freiburg": "Freiburg",
    "fc augsburg": "Augsburg", "sv werder bremen": "Werder Bremen",
    "1 fsv mainz 05": "Mainz", "rb leipzig": "RB Leipzig",
    "1 fc heidenheim 1846": "Heidenheim", "fc st pauli": "St Pauli",
    "holstein kiel": "Holstein Kiel", "vfl bochum": "Bochum",
    # Serie A
    "ac milan": "Milan", "internazionale": "Inter", "fc internazionale milano": "Inter",
    "as roma": "Roma", "ss lazio": "Lazio", "acf fiorentina": "Fiorentina",
    "juventus fc": "Juventus", "ssc napoli": "Napoli", "atalanta bc": "Atalanta",
    "bologna fc 1909": "Bologna", "torino fc": "Torino", "udinese calcio": "Udinese",
    "genoa cfc": "Genoa", "us lecce": "Lecce", "cagliari calcio": "Cagliari",
    "hellas verona": "Verona", "parma calcio 1913": "Parma", "como 1907": "Como",
    "us sassuolo calcio": "Sassuolo", "empoli fc": "Empoli", "us cremonese": "Cremonese",
    "ac monza": "Monza", "venezia fc": "Venezia",
    # La Liga
    "atletico madrid": "Ath Madrid", "club atletico de madrid": "Ath Madrid",
    "athletic club": "Ath Bilbao", "athletic bilbao": "Ath Bilbao",
    "real betis": "Betis", "real betis balompie": "Betis",
    "celta de vigo": "Celta", "rc celta de vigo": "Celta",
    "rcd espanyol": "Espanol", "rcd espanyol de barcelona": "Espanol",
    "real sociedad": "Sociedad", "rayo vallecano": "Vallecano",
    "deportivo alaves": "Alaves", "ud almeria": "Almeria", "cadiz cf": "Cadiz",
    "getafe cf": "Getafe", "girona fc": "Girona", "ud las palmas": "Las Palmas",
    "cd leganes": "Leganes", "rcd mallorca": "Mallorca", "ca osasuna": "Osasuna",
    "sevilla fc": "Sevilla", "valencia cf": "Valencia",
    "real valladolid cf": "Valladolid", "villarreal cf": "Villarreal",
    "fc barcelona": "Barcelona", "real madrid cf": "Real Madrid",
    # Ligue 1
    "paris saint germain": "Paris SG", "paris saint-germain": "Paris SG",
    "olympique de marseille": "Marseille", "olympique lyonnais": "Lyon",
    "as monaco": "Monaco", "losc lille": "Lille", "ogc nice": "Nice",
    "stade rennais": "Rennes", "rc lens": "Lens", "stade brestois 29": "Brest",
    "fc nantes": "Nantes", "montpellier hsc": "Montpellier", "toulouse fc": "Toulouse",
    "rc strasbourg alsace": "Strasbourg", "stade de reims": "Reims",
    "le havre ac": "Le Havre", "aj auxerre": "Auxerre", "angers sco": "Angers",
    "as saint-etienne": "St Etienne",
    # Eredivisie
    "afc ajax": "Ajax", "psv": "PSV Eindhoven", "psv eindhoven": "PSV Eindhoven",
    "feyenoord rotterdam": "Feyenoord", "az": "AZ Alkmaar", "az alkmaar": "AZ Alkmaar",
    "fc twente 65": "Twente", "fc utrecht": "Utrecht",
    # Primeira
    "sl benfica": "Benfica", "fc porto": "Porto", "sporting cp": "Sp Lisbon",
    "sc braga": "Sp Braga", "vitoria sc": "Guimaraes",
    # normalize sonrası kısalanlar için ek anahtarlar
    "internazionale": "Inter", "internazionale milano": "Inter",
    "athletic": "Ath Bilbao", "atletico": "Ath Madrid",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower()
    for ch in ".-'/&":
        s = s.replace(ch, " ")
    drop = {"fc", "afc", "cf", "sc", "ac", "as", "ss", "ssd", "ssc", "cfc", "bc",
            "club", "cd", "rc", "rcd", "ca", "ud", "us", "calcio", "sv", "vfb",
            "vfl", "tsg", "fsv", "acf", "hsc", "sco", "de", "the", "1", "04", "05",
            "09", "65", "1846", "1899", "1907", "1909", "1913", "29", "balompie"}
    toks = [t for t in s.split() if t and t not in drop]
    return " ".join(toks)


# Alias anahtarlarını normalize et (kıyas hep normalize metinle yapılır).
_ALIAS = {_norm(k): v for k, v in _ALIAS.items()}


class _League:
    __slots__ = ("name", "home_adv", "rho", "goal_mean", "teams", "_norm_index")

    def __init__(self, name: str, d: dict):
        self.name = name
        self.home_adv = float(d["home_adv"])
        self.rho = float(d["rho"])
        self.goal_mean = float(d.get("goal_mean", 1.35))
        self.teams = d["teams"]  # {name: [atk, def]}
        self._norm_index = {_norm(k): k for k in self.teams}

    def resolve(self, api_name: str) -> str | None:
        n = _norm(api_name)
        if n in _ALIAS:
            cand = _ALIAS[n]
            if cand in self.teams:
                return cand
        if n in self._norm_index:
            return self._norm_index[n]
        keys = list(self._norm_index)
        hit = difflib.get_close_matches(n, keys, n=1, cutoff=0.6)
        if hit:
            return self._norm_index[hit[0]]
        # token altküme: "man city" ⊂ "manchester city"
        nt = set(n.split())
        for k in keys:
            kt = set(k.split())
            if nt and kt and (nt <= kt or kt <= nt):
                return self._norm_index[k]
        return None


_L_CACHE: dict[str, _League] = {}
_GLOBAL_IDX: dict[str, tuple[float, float]] | None = None


def _global_index() -> dict[str, tuple[float, float]]:
    """Tüm liglerden takım -> (atk, def). Terfi etmiş / kupa rakipleri için yedek."""
    global _GLOBAL_IDX
    if _GLOBAL_IDX is None:
        idx: dict[str, tuple[float, float]] = {}
        for d in _LEAGUES.values():
            for name, (atk, dfc) in d["teams"].items():
                idx.setdefault(_norm(name), (float(atk), float(dfc)))
        _GLOBAL_IDX = idx
    return _GLOBAL_IDX


def _global_lookup(api_name: str) -> tuple[float, float] | None:
    idx = _global_index()
    n = _norm(api_name)
    if n in _ALIAS and _norm(_ALIAS[n]) in idx:
        return idx[_norm(_ALIAS[n])]
    if n in idx:
        return idx[n]
    hit = difflib.get_close_matches(n, list(idx), n=1, cutoff=0.68)
    if hit:
        return idx[hit[0]]
    nt = set(n.split())
    for k in idx:
        kt = set(k.split())
        if nt and kt and (nt <= kt or kt <= nt):
            return idx[k]
    return None


def _league_for_code(code: str) -> _League | None:
    lname = _CODE_TO_LEAGUE.get(code)
    if not lname or lname not in _LEAGUES:
        return None
    lg = _L_CACHE.get(lname)
    if lg is None:
        lg = _League(lname, _LEAGUES[lname])
        _L_CACHE[lname] = lg
    return lg


def _components(comp_code: str, home_name: str, away_name: str) -> dict | None:
    lg = _league_for_code(comp_code)
    if lg is None:
        return None
    h = lg.resolve(home_name)
    a = lg.resolve(away_name)
    atk_h, def_h = (lg.teams[h] if h else (None, None))
    atk_a, def_a = (lg.teams[a] if a else (None, None))
    g_h = g_a = False
    if atk_h is None:
        r = _global_lookup(home_name)
        if r:
            atk_h, def_h, g_h = r[0], r[1], True
    if atk_a is None:
        r = _global_lookup(away_name)
        if r:
            atk_a, def_a, g_a = r[0], r[1], True
    atk_h = 0.0 if atk_h is None else float(atk_h)
    def_h = 0.0 if def_h is None else float(def_h)
    atk_a = 0.0 if atk_a is None else float(atk_a)
    def_a = 0.0 if def_a is None else float(def_a)

    lam_home = min(max(math.exp(atk_h - def_a + lg.home_adv), 0.15), 5.0)
    lam_away = min(max(math.exp(atk_a - def_h), 0.15), 5.0)

    have_h, have_a = bool(h) or g_h, bool(a) or g_a
    conf = 0.62 if (h and a) else (0.52 if (have_h and have_a)
                                   else (0.42 if (have_h or have_a) else 0.32))
    return {
        "lg": lg, "lam_home": lam_home, "lam_away": lam_away,
        "atk_h": atk_h, "def_h": def_h, "atk_a": atk_a, "def_a": def_a,
        "home_adv": lg.home_adv, "rho": lg.rho, "conf": conf,
        "have_h": have_h, "have_a": have_a,
    }


def lambdas(comp_code: str, home_name: str, away_name: str) -> dict:
    """Maç için lambda_home / lambda_away / rho / model_confidence."""
    c = _components(comp_code, home_name, away_name)
    if c is None:
        return {"lambda_home": 1.35, "lambda_away": 1.10, "rho": -0.03,
                "model_confidence": 0.30, "modeled": False}
    return {"lambda_home": round(c["lam_home"], 3),
            "lambda_away": round(c["lam_away"], 3),
            "rho": round(c["rho"], 3), "model_confidence": c["conf"],
            "modeled": bool(c["have_h"] and c["have_a"])}


def explain(comp_code: str, home_name: str, away_name: str) -> dict:
    """Modelin bu maç için gol beklentisini nasıl kurduğunun dökümü."""
    c = _components(comp_code, home_name, away_name)
    if c is None:
        return {"lambda_home": 1.35, "lambda_away": 1.10, "rho": -0.03,
                "model_confidence": 0.30, "context_factors": [], "explanation": {}}

    def factor(label, value, impact, note):
        return {"label": label, "value": value, "impact": round(impact, 3), "note": note}

    # Etki = gol beklentisine yaklaşık katkı (exp lineerize)
    base = c["lg"].goal_mean
    fs = [
        factor("Ev sahibi hücum", f"{c['atk_h']:+.2f}", c["atk_h"] * base,
               "Lig ortalamasına göre gol üretimi"),
        factor("Deplasman savunma", f"{c['def_a']:+.2f}", -c["def_a"] * base,
               "Rakip savunmanın gol yeme eğilimi (ters)"),
        factor("Ev avantajı", f"{c['home_adv']:+.2f}", c["home_adv"] * base,
               "Bu ligde ev sahibi olmanın katkısı"),
        factor("Deplasman hücum", f"{c['atk_a']:+.2f}", c["atk_a"] * base,
               "Konuk takımın gol üretimi"),
        factor("Ev sahibi savunma", f"{c['def_h']:+.2f}", -c["def_h"] * base,
               "Ev sahibi savunmanın rakibi durdurma gücü (ters)"),
    ]
    fs.sort(key=lambda x: -abs(x["impact"]))
    return {
        "match_id": 0,
        "lambda_home": round(c["lam_home"], 3),
        "lambda_away": round(c["lam_away"], 3),
        "rho": round(c["rho"], 3),
        "model_confidence": c["conf"],
        "context_factors": fs,
        "explanation": {
            "home_attack": round(c["atk_h"], 3),
            "home_defence": round(c["def_h"], 3),
            "away_attack": round(c["atk_a"], 3),
            "away_defence": round(c["def_a"], 3),
            "home_advantage": round(c["home_adv"], 3),
            "matched": 1.0 if (c["have_h"] and c["have_a"]) else 0.0,
        },
    }
