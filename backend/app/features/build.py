"""
Özellik çerçevesi kurucusu (madde 3, 4, 46-58 birleştirme noktası).

Tek giriş: `build_features(conn, match_id, kickoff)`.
Her şey `AsOfContext` altında toplanır; sızıntı yapısal olarak imkânsız.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import numpy as np
import pandas as pd

from . import context as ctx_mod
from . import squad as squad_mod
from .decay import days_between, exponential, effective_sample_size, confidence_from_ess
from .leakage import AsOfContext, SafeQuery, encode_missing
from .sos import opponent_adjusted


def build_features(conn, match_id: int, kickoff: dt.datetime,
                   lead_minutes: int = 90, xi: float = 0.0045) -> dict:
    ctx = AsOfContext.before_kickoff(kickoff, match_id, lead_minutes)
    q = SafeQuery(conn, ctx)

    meta = pd.read_sql_query(
        """SELECT m.home_team_id, m.away_team_id, m.league_id, m.season,
                  m.stage, m.leg, m.crowd_status, m.venue_id,
                  v.altitude_m, v.surface
           FROM match m LEFT JOIN venue v ON v.id = m.venue_id
           WHERE m.id = ?""", conn, params=(match_id,)).iloc[0]

    home_id, away_id = int(meta.home_team_id), int(meta.away_team_id)

    team_feats = {}
    for side, tid in (("home", home_id), ("away", away_id)):
        team_feats.update(
            {f"{side}_{k}": v for k, v in _team_block(q, conn, tid, ctx, xi).items()})

    effects = _context_effects(q, conn, match_id, meta, home_id, away_id, kickoff)

    rows = {
        **team_feats,
        "league_id": int(meta.league_id),
        "is_cup": int(meta.stage != "league"),
        "leg": int(meta.leg or 0),
        "crowd_closed": int(meta.crowd_status == "closed"),
        "altitude_m": float(meta.altitude_m or 0),
    }
    for e in effects:
        rows[f"ctx_{_slug(e.label)}_home"] = e.lambda_multiplier_home
        rows[f"ctx_{_slug(e.label)}_away"] = e.lambda_multiplier_away

    frame = encode_missing(pd.DataFrame([rows]),
                           [c for c in rows if c.endswith(("_xg", "_xga", "_ppda"))])

    return {
        "features": frame,
        "context_effects": effects,
        "as_of": ctx.iso,
        "violations": ctx.violations,
        "feature_hash": _hash(rows),
    }


def _team_block(q: SafeQuery, conn, team_id: int, ctx: AsOfContext,
                xi: float) -> dict:
    """Bir takımın zaman ağırlıklı geçmiş performansı."""
    shots = q.table(
        "shot_event",
        where="team_id = ? AND is_penalty = 0",     # madde 49: penaltısız xG
        params=(team_id,),
        columns="match_id, xg, is_set_piece, is_goal, score_state, men_on_pitch_diff, observed_at")

    if shots.empty:
        return {"xg": np.nan, "xg_setpiece": np.nan, "shots": 0,
                "conversion": np.nan, "ess": 0.0, "confidence": 0.2}

    # madde 56, 58: dengesiz durumda üretilen xG farklı ağırlık taşır
    neutral = shots[(shots.score_state.abs() <= 1) & (shots.men_on_pitch_diff == 0)]
    base = neutral if len(neutral) >= 20 else shots

    days = days_between(base["observed_at"], ctx.as_of)
    w = exponential(days, xi)

    per_match = (pd.DataFrame({"m": base.match_id, "xg": base.xg * w, "w": w})
                 .groupby("m").agg(xg=("xg", "sum"), w=("w", "mean")))
    ess = effective_sample_size(per_match["w"].to_numpy())

    xg_mean = float((base.xg * w).sum() / max(w.sum(), 1e-9) * len(base) / max(len(per_match), 1))
    setpiece = float((base.loc[base.is_set_piece == 1, "xg"] *
                      w[base.is_set_piece.to_numpy() == 1]).sum() / max(w.sum(), 1e-9))
    goals = float((base.is_goal * w).sum())
    xg_total = float((base.xg * w).sum())

    return {
        "xg": xg_mean,
        "xg_setpiece": setpiece,                     # madde 51
        "shots": int(len(base)),                      # madde 48: hacim
        "shot_quality": float(base.xg.mean()),        # madde 48: kalite
        # madde 52: aşırı dönüşüm ortalamaya döner — ham değil, oran olarak tut
        "conversion": goals / max(xg_total, 1e-9),
        "ess": ess,                                   # madde 53
        "confidence": confidence_from_ess(ess),
    }


def _context_effects(q: SafeQuery, conn, match_id: int, meta,
                     home_id: int, away_id: int, kickoff: dt.datetime) -> list:
    effects = []

    rest = pd.read_sql_query(
        """SELECT home_team_id AS t, kickoff_utc FROM match
           WHERE kickoff_utc < ? AND (home_team_id IN (?,?) OR away_team_id IN (?,?))
           ORDER BY kickoff_utc DESC LIMIT 20""",
        conn, params=(kickoff.isoformat(), home_id, away_id, home_id, away_id))

    def rest_days(tid: int) -> float:
        prev = rest[rest.t == tid]
        if prev.empty:
            return 7.0
        last = pd.Timestamp(prev.iloc[0].kickoff_utc)
        return float((pd.Timestamp(kickoff) - last).days)

    effects.append(ctx_mod.rest_effect(rest_days(home_id), rest_days(away_id),
                                       len(rest[rest.t == home_id]),
                                       len(rest[rest.t == away_id])))

    w = q.table("weather_observation", where="match_id = ?", params=(match_id,),
                columns="wind_kph, precip_mm, temp_c, forecast_made_at")
    if not w.empty:
        r = w.iloc[-1]
        effects.append(ctx_mod.weather_effect(r.wind_kph, r.precip_mm, r.temp_c))

    if meta.altitude_m:
        effects.append(ctx_mod.altitude_effect(float(meta.altitude_m), 0.0))

    effects.append(ctx_mod.crowd_effect(meta.crowd_status or "normal", 1.25))

    standings = q.latest_per_key("table_standing", ["team_id"],
                                 where="team_id IN (?,?)", params=(home_id, away_id))
    if len(standings) == 2:
        rem = int(standings.games_remaining.min())
        stakes = {int(r.team_id): _stakes(r) for _, r in standings.iterrows()}
        effects.append(ctx_mod.motivation_effect(
            stakes.get(home_id, 0.5), stakes.get(away_id, 0.5), rem))

    return effects


def _stakes(row) -> float:
    """Sıralamadan 'kaybedecek bir şeyi var mı' skoru (0-1)."""
    for col, weight in (("pts_to_relegation", 1.0), ("pts_to_title", 0.9),
                        ("pts_to_europe", 0.7)):
        v = row.get(col)
        if v is not None and not pd.isna(v) and abs(v) <= 6:
            return float(weight * (1 - abs(v) / 12))
    return 0.35


def _slug(s: str) -> str:
    return (s.lower().replace(" ", "_")
            .translate(str.maketrans("çğıöşü", "cgiosu")))


def _hash(d: dict) -> str:
    payload = json.dumps({k: (None if isinstance(v, float) and np.isnan(v) else v)
                          for k, v in sorted(d.items())}, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
