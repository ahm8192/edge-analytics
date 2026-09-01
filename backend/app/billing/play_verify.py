"""
Google Play Developer API ile abonelik doğrulama (purchases.subscriptionsv2.get).

İstemciden gelen purchaseToken'a asla güvenilmez; her zaman Google'a sorulur.
Servis hesabı JSON'u ile kimlik doğrulanır.
"""
from __future__ import annotations
import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .tiers import Tier

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/androidpublisher"]

# subscriptionState -> iç durum
_STATE_MAP = {
    "SUBSCRIPTION_STATE_ACTIVE": "ACTIVE",
    "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": "IN_GRACE",   # ödeme başarısız, erişim sürüyor
    "SUBSCRIPTION_STATE_ON_HOLD": "ON_HOLD",            # erişim KESİLİR
    "SUBSCRIPTION_STATE_PAUSED": "PAUSED",
    "SUBSCRIPTION_STATE_CANCELED": "CANCELED",          # süre dolana kadar erişim sürer
    "SUBSCRIPTION_STATE_EXPIRED": "EXPIRED",
    "SUBSCRIPTION_STATE_PENDING": "PENDING",
}

# Erişim veren durumlar. CANCELED dahildir: iptal etmiş ama süresi dolmamış
# kullanıcı parasının karşılığını almalıdır.
ACCESS_STATES = {"ACTIVE", "IN_GRACE", "CANCELED"}


@dataclass
class VerifiedSubscription:
    purchase_token: str
    product_id: str
    base_plan_id: str | None
    offer_id: str | None
    state: str
    tier: Tier
    expiry_at: dt.datetime | None
    start_at: dt.datetime | None
    auto_renewing: bool
    is_acknowledged: bool
    is_test: bool
    linked_purchase_token: str | None
    raw: dict[str, Any]

    @property
    def grants_access(self) -> bool:
        if self.state not in ACCESS_STATES:
            return False
        if self.expiry_at is None:
            return False
        return self.expiry_at > dt.datetime.now(dt.timezone.utc)


class PlayVerifier:
    def __init__(self, service_account_file: str, package_name: str,
                 product_tier_map: dict[str, Tier]):
        creds = service_account.Credentials.from_service_account_file(
            service_account_file, scopes=SCOPES)
        self._api = build("androidpublisher", "v3", credentials=creds,
                          cache_discovery=False)
        self.package_name = package_name
        self.product_tier_map = product_tier_map

    def verify(self, purchase_token: str) -> VerifiedSubscription | None:
        try:
            resp = self._api.purchases().subscriptionsv2().get(
                packageName=self.package_name, token=purchase_token
            ).execute()
        except HttpError as e:
            # 410 = token artık geçersiz; 400 = biçim hatası
            log.warning("Play doğrulama hatası %s: %s", e.resp.status, e)
            return None

        line_items = resp.get("lineItems") or []
        if not line_items:
            return None
        item = line_items[0]

        product_id = item.get("productId", "")
        state = _STATE_MAP.get(resp.get("subscriptionState", ""), "EXPIRED")
        tier = self.product_tier_map.get(product_id, Tier.FREE)

        auto_renew = bool(item.get("autoRenewingPlan", {}).get("autoRenewEnabled", False))

        return VerifiedSubscription(
            purchase_token=purchase_token,
            product_id=product_id,
            base_plan_id=item.get("offerDetails", {}).get("basePlanId"),
            offer_id=item.get("offerDetails", {}).get("offerId"),
            state=state,
            tier=tier,
            expiry_at=_parse(item.get("expiryTime")),
            start_at=_parse(resp.get("startTime")),
            auto_renewing=auto_renew,
            is_acknowledged=resp.get("acknowledgementState") ==
                            "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
            is_test=bool(resp.get("testPurchase")),
            linked_purchase_token=resp.get("linkedPurchaseToken"),
            raw=resp,
        )

    def acknowledge(self, product_id: str, purchase_token: str) -> None:
        """3 gün içinde onaylanmayan satın alma Google tarafından iade edilir."""
        try:
            self._api.purchases().subscriptions().acknowledge(
                packageName=self.package_name, subscriptionId=product_id,
                token=purchase_token, body={},
            ).execute()
        except HttpError as e:
            if e.resp.status != 400:   # 400 genelde "zaten onaylı"
                raise


def _parse(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
