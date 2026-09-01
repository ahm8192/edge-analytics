from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ...live_data import default_analysis, fetch_matches

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


@router.get("/matches/{match_id}/analysis")
def analysis(match_id: int):
    # Ücretsiz sağlayıcı model parametresi sunmadığı için nötr öncül kullanılır.
    return default_analysis(match_id)


@router.get("/matches/{match_id}/odds")
def odds(match_id: int, market: str = "1X2"):
    # football-data.org ücretsiz planında bahis oranları bulunmaz.
    return {"quotes": []}


@router.get("/matches/{match_id}/odds/movement")
def movement(match_id: int, market: str, selection: str):
    return {"points": []}
