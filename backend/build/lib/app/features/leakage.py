"""
Sızıntı koruması (madde 3, 4, 9).

Bu dosya projedeki EN KRİTİK dosyadır. Buradaki bir hata, backtest'i
harika gösterip canlıda para kaybettirir — ve fark etmesi aylar sürer.

Temel kural: her sorgu bir `as_of` anıyla yapılır ve o andan SONRA
gözlenmiş hiçbir satır dönmez.
"""
from __future__ import annotations
import datetime as dt
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


class LeakageError(RuntimeError):
    """Zaman kesimini ihlal eden bir sorgu yakalandı."""


@dataclass
class AsOfContext:
    """
    Bir tahmin üretilirken bilinen dünyanın sınırı.

    kickoff'tan `lead_minutes` önce donmuş bilgi kullanılır. Bunun sebebi:
    maçtan 5 dakika önce çıkan kadro haberiyle üretilen tahmin, gerçek
    hayatta bahis oynanan anı temsil etmez.
    """
    as_of: dt.datetime
    match_id: int | None = None
    lead_minutes: int = 90
    violations: list[str] = field(default_factory=list)

    @classmethod
    def before_kickoff(cls, kickoff: dt.datetime, match_id: int,
                       lead_minutes: int = 90) -> "AsOfContext":
        return cls(as_of=kickoff - dt.timedelta(minutes=lead_minutes),
                   match_id=match_id, lead_minutes=lead_minutes)

    @property
    def iso(self) -> str:
        return self.as_of.isoformat()


# Bu tabloların hangi kolonu zaman kesimi için kullanılacak
TIME_COLUMN = {
    "shot_event": "observed_at",
    "lineup_entry": "observed_at",
    "availability_news": "published_at",
    "club_event": "published_at",
    "odds_snapshot": "captured_at",
    "possession_summary": "observed_at",
    "player_rating": "as_of",
    "referee_form": "as_of",
    "table_standing": "as_of",
    "weather_observation": "forecast_made_at",
    "match_source_record": "observed_at",
}

# Maç bittikten sonra dolan kolonlar — özellik olarak ASLA kullanılamaz
FORBIDDEN_COLUMNS = {
    "home_goals", "away_goals", "is_goal", "outcome", "pnl",
    "minutes_played", "is_closing", "settled_at",
}


class SafeQuery:
    """
    Zaman kesimini zorlayan sorgu sarmalayıcı.
    Ham SQL yazmak yerine bunu kullan; unutulan bir WHERE burada yakalanır.
    """

    def __init__(self, conn: sqlite3.Connection, ctx: AsOfContext,
                 strict: bool = True):
        self.conn = conn
        self.ctx = ctx
        self.strict = strict

    def table(self, name: str, where: str = "1=1",
              params: tuple = (), columns: str = "*") -> pd.DataFrame:
        tcol = TIME_COLUMN.get(name)
        if tcol is None:
            raise LeakageError(
                f"'{name}' için zaman kolonu tanımlı değil. "
                f"TIME_COLUMN sözlüğüne ekle, yoksa sızıntı riski var.")

        sql = f"SELECT {columns} FROM {name} WHERE ({where}) AND {tcol} <= ?"
        df = pd.read_sql_query(sql, self.conn, params=(*params, self.ctx.iso))
        self._audit(df, name)
        return df

    def _audit(self, df: pd.DataFrame, name: str) -> None:
        bad = FORBIDDEN_COLUMNS.intersection(df.columns)
        if bad:
            msg = f"{name}: sonuç-sonrası kolonlar seçildi: {sorted(bad)}"
            self.ctx.violations.append(msg)
            if self.strict:
                raise LeakageError(msg)
            log.warning(msg)

    def latest_per_key(self, name: str, key_cols: list[str],
                       where: str = "1=1", params: tuple = ()) -> pd.DataFrame:
        """
        Her anahtar için as_of'tan önceki EN SON kaydı getirir.
        Örnek: her oyuncunun en güncel derecesi, her takımın son sıralaması.
        """
        tcol = TIME_COLUMN[name]
        keys = ", ".join(key_cols)
        sql = f"""
            SELECT * FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY {keys} ORDER BY {tcol} DESC) AS _rn
                FROM {name} WHERE ({where}) AND {tcol} <= ?
            ) WHERE _rn = 1
        """
        df = pd.read_sql_query(sql, self.conn, params=(*params, self.ctx.iso))
        return df.drop(columns=["_rn"], errors="ignore")


# ---------------------------------------------------------------------
# Eksik veri (madde 9)
# ---------------------------------------------------------------------
MISSING = np.nan


def encode_missing(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """
    Eksik değeri 0 ile doldurmak, "bilgi yok"u "sıfır değer" ile karıştırır.
    Bunun yerine NaN bırakılır ve yanına bir 'var mı' bayrağı eklenir.
    LightGBM/XGBoost NaN'ı doğal olarak işler; bilgiyi kendisi öğrenir.
    """
    out = df.copy()
    for c in columns:
        if c not in out.columns:
            out[c] = MISSING
        out[f"{c}__known"] = out[c].notna().astype("int8")
    return out


def assert_no_future_rows(df: pd.DataFrame, time_col: str,
                          ctx: AsOfContext) -> None:
    """Testlerde ve pipeline sonunda çağrılacak son savunma hattı."""
    if time_col not in df.columns or df.empty:
        return
    ts = pd.to_datetime(df[time_col], utc=True, errors="coerce")
    cutoff = pd.Timestamp(ctx.as_of, tz="UTC") if ctx.as_of.tzinfo is None \
        else pd.Timestamp(ctx.as_of)
    future = ts > cutoff
    if future.any():
        raise LeakageError(
            f"{int(future.sum())} satır kesim anından sonra gözlenmiş "
            f"({cutoff.isoformat()}). Bu bir sızıntıdır.")


@contextmanager
def leakage_guard(ctx: AsOfContext):
    """
    Blok bittiğinde biriken ihlalleri raporlar.
    Eğitim döngüsünün etrafına sar; sessiz sızıntı bırakmaz.
    """
    try:
        yield ctx
    finally:
        if ctx.violations:
            log.error("Sızıntı ihlalleri (%s): %s",
                      ctx.match_id, "; ".join(ctx.violations))
