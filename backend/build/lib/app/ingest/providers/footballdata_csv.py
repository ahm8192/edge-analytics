"""
Toplu CSV sağlayıcı — football-data.co.uk türevi açık veri setleri.

Diğer sağlayıcılardan farkı: canlı API değil, tek seferlik toplu yükleme.
Projeyi sıfırdan başlatmak için ideal — 25 yıllık geçmişi API kotası
harcamadan getirir. Canlı akış için HTTP sağlayıcılarla birlikte kullanılır.

Kaynak: xgabora/Club-Football-Match-Data-2000-2025 (CC-BY, football-data.co.uk
ve ClubElo türevi). 42 lig, 230.000+ maç, maç öncesi oranlar dahil.
"""
from __future__ import annotations
import datetime as dt
import logging
from typing import Iterable

import pandas as pd

from .base import Provider, ProviderCapabilities, RawRecord

log = logging.getLogger(__name__)

# football-data.co.uk lig kodu -> (ülke, isim, kademe)
DIVISION_MAP = {
    "T1":  ("TR", "Süper Lig", 1),
    "E0":  ("ENG", "Premier League", 1),
    "E1":  ("ENG", "Championship", 2),
    "D1":  ("DE", "Bundesliga", 1),
    "SP1": ("ES", "La Liga", 1),
    "I1":  ("IT", "Serie A", 1),
    "F1":  ("FR", "Ligue 1", 1),
    "N1":  ("NL", "Eredivisie", 1),
    "P1":  ("PT", "Primeira Liga", 1),
    "B1":  ("BE", "Pro League", 1),
    "G1":  ("GR", "Super League", 1),
}


class FootballDataCsvProvider(Provider):
    code = "footballdata_csv"
    trust_weight = 0.9      # toplu arşiv: güvenilir ama gecikmeli

    def __init__(self, csv_path: str):
        super().__init__(api_key=None, rate_limit=(10_000, 1.0))
        self.csv_path = csv_path
        self._df: pd.DataFrame | None = None
        self.capabilities = ProviderCapabilities(
            matches=True, shot_events=False, xg=False,
            odds=True, odds_history=False,     # tek anlık görüntü, seri yok
            typical_delay_minutes=0,
            leagues_covered=list(DIVISION_MAP),
        )

    def load(self) -> pd.DataFrame:
        if self._df is None:
            self._df = pd.read_csv(self.csv_path, low_memory=False)
            self._df["MatchDate"] = pd.to_datetime(self._df.MatchDate, errors="coerce")
            self._call_count += 1
            log.info("%s: %d satır yüklendi", self.code, len(self._df))
        return self._df

    def fetch_matches(self, date_from: dt.date, date_to: dt.date,
                      divisions: list[str] | None = None) -> Iterable[RawRecord]:
        df = self.load()
        mask = (df.MatchDate >= pd.Timestamp(date_from)) & \
               (df.MatchDate <= pd.Timestamp(date_to))
        if divisions:
            mask &= df.Division.isin(divisions)
        for _, row in df[mask].iterrows():
            ext = f"{row.Division}:{row.MatchDate:%Y%m%d}:{row.HomeTeam}:{row.AwayTeam}"
            yield self._record("match", ext, row.to_dict())

    def normalize_match(self, raw: RawRecord) -> dict:
        p = raw.payload
        country, name, tier = DIVISION_MAP.get(p["Division"], ("XX", p["Division"], 1))
        date = pd.Timestamp(p["MatchDate"])
        kickoff = f"{date:%Y-%m-%d}T{_time_of(p.get('MatchTime'))}+00:00"
        return {
            "external_id": raw.external_id,
            "kickoff_utc": kickoff,
            "league_code": p["Division"],
            "league_name": name, "league_country": country, "league_tier": tier,
            "season": _season_of(date),
            "home_raw_name": p["HomeTeam"], "away_raw_name": p["AwayTeam"],
            "home_external_id": p["HomeTeam"], "away_external_id": p["AwayTeam"],
            "status": "finished" if pd.notna(p.get("FTHome")) else "scheduled",
            "home_goals": _int(p.get("FTHome")), "away_goals": _int(p.get("FTAway")),
            # madde 9: eksik olan 0 değil None kalır
            "home_shots": _int(p.get("HomeShots")),
            "away_shots": _int(p.get("AwayShots")),
            "home_target": _int(p.get("HomeTarget")),
            "away_target": _int(p.get("AwayTarget")),
            "home_red": _int(p.get("HomeRed")), "away_red": _int(p.get("AwayRed")),
            "home_elo": _float(p.get("HomeElo")), "away_elo": _float(p.get("AwayElo")),
        }

    def normalize_odds(self, raw: RawRecord) -> dict:
        """
        İki ayrı kitap gibi ele alınır:
          'market_avg' — piyasa ortalaması, ADİL olasılık buradan çıkar
          'market_best' — en iyi oran, oynanacak fiyat budur (madde 84)
        """
        p = raw.payload
        out = []
        if pd.notna(p.get("OddHome")):
            out.append({"bookmaker_code": "market_avg", "market": "1X2", "line": None,
                        "prices": {"HOME": float(p["OddHome"]),
                                   "DRAW": float(p["OddDraw"]),
                                   "AWAY": float(p["OddAway"])}})
        if pd.notna(p.get("MaxHome")):
            out.append({"bookmaker_code": "market_best", "market": "1X2", "line": None,
                        "prices": {"HOME": float(p["MaxHome"]),
                                   "DRAW": float(p["MaxDraw"]),
                                   "AWAY": float(p["MaxAway"])}})
        if pd.notna(p.get("Over25")):
            out.append({"bookmaker_code": "market_avg", "market": "OU", "line": 2.5,
                        "prices": {"OVER": float(p["Over25"]),
                                   "UNDER": float(p["Under25"])}})
        return {"captured_at": raw.observed_at.isoformat(), "quotes": out}


def _season_of(date: pd.Timestamp) -> str:
    y = date.year
    return f"{y}-{str(y+1)[2:]}" if date.month >= 7 else f"{y-1}-{str(y)[2:]}"


def _int(v):
    return None if v is None or pd.isna(v) else int(v)


def _float(v):
    return None if v is None or pd.isna(v) else float(v)


def _time_of(value) -> str:
    """
    MatchTime alanı sağlayıcıya göre 'HH:MM' ya da 'HH:MM:SS' gelir, bazen boştur.
    Hepsini HH:MM:SS'e normalize et — aksi hâlde ISO damgası bozulur ve
    SQLite DATE() sessizce NULL döner (bu hatayı sağlık kontrolü yakalamıştı).
    """
    s = str(value or "").strip()
    if not s or s.lower() in ("nan", "none"):
        return "00:00:00"
    parts = s.split(":")
    if len(parts) == 2:
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:00"
    if len(parts) >= 3:
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{parts[2][:2].zfill(2)}"
    return "00:00:00"
