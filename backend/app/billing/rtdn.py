"""
Real-time Developer Notifications (Pub/Sub push) işleyicisi.

Google, abonelik durumu her değiştiğinde buraya haber verir.
Polling'e güvenme: yenileme, iptal, ödeme sorunu anında buradan gelir.
İşleme idempotent olmalı; Pub/Sub aynı mesajı birden fazla teslim edebilir.
"""
from __future__ import annotations
import base64
import json
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

# https://developer.android.com/google/play/billing/rtdn-reference
SUBSCRIPTION_NOTIFICATION = {
    1: "RECOVERED",          # ON_HOLD'dan kurtuldu -> erişim aç
    2: "RENEWED",            # yenilendi -> süreyi uzat
    3: "CANCELED",           # otomatik yenileme kapandı, süre sonuna kadar erişim VAR
    4: "PURCHASED",          # yeni satın alma -> onayla (acknowledge)
    5: "ON_HOLD",            # ödeme başarısız -> erişimi KES
    6: "IN_GRACE_PERIOD",    # ödeme sorunu, erişim devam
    7: "RESTARTED",
    8: "PRICE_CHANGE_CONFIRMED",
    9: "DEFERRED",
    10: "PAUSED",            # erişimi kes
    11: "PAUSE_SCHEDULE_CHANGED",
    12: "REVOKED",           # iade/geri alma -> erişimi ANINDA kes
    13: "EXPIRED",
    20: "PENDING_PURCHASE_CANCELED",
}

# Doğrulamayı tetiklemesi gereken bildirimler
REVERIFY = {1, 2, 3, 4, 5, 6, 7, 10, 12, 13}


@dataclass
class RtdnMessage:
    message_id: str
    package_name: str
    notification_type: int | None
    purchase_token: str | None
    product_id: str | None
    is_test: bool
    raw: dict


def parse_pubsub_envelope(envelope: dict) -> RtdnMessage | None:
    msg = envelope.get("message") or {}
    data_b64 = msg.get("data")
    if not data_b64:
        return None
    payload = json.loads(base64.b64decode(data_b64).decode("utf-8"))

    sub = payload.get("subscriptionNotification") or {}
    return RtdnMessage(
        message_id=msg.get("messageId", ""),
        package_name=payload.get("packageName", ""),
        notification_type=sub.get("notificationType"),
        purchase_token=sub.get("purchaseToken"),
        product_id=sub.get("subscriptionId"),
        is_test="testNotification" in payload,
        raw=payload,
    )


def should_reverify(m: RtdnMessage) -> bool:
    return m.notification_type in REVERIFY
