from __future__ import annotations

import datetime as dt
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/billing", tags=["billing"])


def _free_entitlement() -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    expires = now + dt.timedelta(days=1)
    grace = now + dt.timedelta(days=8)
    return {
        "token": "free-local-entitlement",
        "tier": "FREE",
        "expires_at": expires.isoformat(),
        "grace_until": grace.isoformat(),
        "flags": {},
        "quotas": {"match_analysis": 3, "odds_refresh": 3},
        "usage": {
            "match_analysis": {"remaining": 3, "limit": 3},
            "odds_refresh": {"remaining": 3, "limit": 3},
        },
    }


@router.get("/entitlement")
def entitlement() -> dict:
    """Anonim kullanıcı için ücretsiz katman; Play Billing entegrasyonu ayrıca açılabilir."""
    return _free_entitlement()


@router.post("/verify")
def verify_purchase(body: dict) -> dict:
    # Google Play doğrulaması canlı servis yapılandırılmadan PRO açılmaz.
    raise HTTPException(
        status.HTTP_402_PAYMENT_REQUIRED,
        detail={"error": "billing_not_configured", "message": "Play Billing sunucu doğrulaması yapılandırılmadı."},
    )


@router.post("/rtdn")
def rtdn() -> dict:
    return {"status": "ignored", "reason": "billing_not_configured"}
