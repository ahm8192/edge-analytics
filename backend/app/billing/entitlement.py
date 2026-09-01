"""
Yetki servisi: doğrulanmış abonelikten katman (tier) ve bayrak üretir,
istemcinin OFFLINE çalışabilmesi için kısa ömürlü imzalı token verir.

Offline mantığı:
  - token 24 saat geçerli (exp)
  - ağ yoksa 7 gün tolerans (grace) -> uçakta/metroda uygulama çalışmaya devam eder
  - grace bitince katman FREE'ye düşer, uygulama kilitlenmez
"""
from __future__ import annotations
import datetime as dt
import uuid

import jwt   # PyJWT

from .tiers import Tier, feature_flags, QUOTAS

TOKEN_TTL = dt.timedelta(hours=24)
OFFLINE_GRACE = dt.timedelta(days=7)


class EntitlementService:
    def __init__(self, signing_key: str, issuer: str = "edge-api"):
        self._key = signing_key
        self._iss = issuer

    def resolve_tier(self, subscriptions: list) -> Tier:
        """Birden fazla aktif abonelik varsa en yükseği kazanır."""
        best = Tier.FREE
        for s in subscriptions:
            if s.grants_access and s.tier.rank > best.rank:
                best = s.tier
        return best

    def issue(self, user_id: int, tier: Tier,
              expiry_at: dt.datetime | None = None) -> dict:
        now = dt.datetime.now(dt.timezone.utc)
        exp = now + TOKEN_TTL
        # Abonelik token'dan önce bitiyorsa token da erken bitsin
        if expiry_at and expiry_at < exp:
            exp = expiry_at
        grace = exp + OFFLINE_GRACE
        jti = str(uuid.uuid4())

        payload = {
            "iss": self._iss,
            "sub": str(user_id),
            "tier": tier.value,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "grace": int(grace.timestamp()),
            "jti": jti,
            "flags": feature_flags(tier),
            "quotas": {q.key: q.limit for q in QUOTAS[tier]},
        }
        return {
            "token": jwt.encode(payload, self._key, algorithm="HS256"),
            "tier": tier.value,
            "expires_at": exp.isoformat(),
            "grace_until": grace.isoformat(),
            "flags": payload["flags"],
            "quotas": payload["quotas"],
            "jti": jti,
        }

    def verify(self, token: str) -> dict | None:
        try:
            return jwt.decode(token, self._key, algorithms=["HS256"],
                              issuer=self._iss)
        except jwt.PyJWTError:
            return None
