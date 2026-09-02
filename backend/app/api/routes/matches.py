from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ...live_data import default_analysis, fetch_matches, match_odds

router = APIRouter(tags=["matches"])


@router.get("/matches")
def list_matches(
    from_: str = Query(alias="from"),
    to: str = Query(...),
    league_id: int | None = None,
):
    """Ücretsiz football-data.org planından fikstür ve gecikmeli skorları döndürür."""
    try:
        payload = fetch_matches(from_, to)
    except Exception as exc:
        raise HTTPException(502, detail={"error": "football_provider_unavailable", "message": str(exc)}) from exc
    if league_id is not None:
        payload["matches"] = [m for m in payload["matches"] if m["league_id"] == league_id]
    return payload


@router.get("/value")
def value_board(from_: str = Query(alias="from"), to: str = Query(...)):
    """Değer tablosu: Pinnacle-adil fiyatını geçen her kitap/seçim, kenara göre sıralı.
    Belgelenmiş +EV yönü (zayıf kitap > Pinnacle-adil)."""
    try:
        payload = fetch_matches(from_, to)
    except Exception as exc:
        raise HTTPException(502, detail={"error": "football_provider_unavailable", "message": str(exc)}) from exc
    tn = {t["id"]: (t.get("short_name") or t.get("name") or "") for t in payload["teams"]}
    ln = {lg["id"]: lg.get("name", "") for lg in payload["leagues"]}
    rows: list[dict] = []
    for m in payload["matches"]:
        for v in m.get("value_bets", []):
            rows.append({
                "match_id": m["id"], "kickoff": m["kickoff"],
                "league": ln.get(m["league_id"], ""),
                "home": tn.get(m["home_team_id"], ""), "away": tn.get(m["away_team_id"], ""),
                **v,
            })
    rows.sort(key=lambda x: -x["edge_pct"])
    return {"value_bets": rows}


@router.get("/matches/{match_id}/analysis")
def analysis(match_id: int):
    # Ücretsiz sağlayıcı model parametresi sunmadığı için nötr öncül kullanılır.
    return default_analysis(match_id)


@router.get("/matches/{match_id}/odds")
def odds(match_id: int, market: str = "1X2"):
    # Yakın maçlar için API-Football'dan Pinnacle + en iyi oran; uzak maçlarda boş.
    return match_odds(match_id)


@router.get("/matches/{match_id}/odds/movement")
def movement(match_id: int, market: str, selection: str):
    return {"points": []}
