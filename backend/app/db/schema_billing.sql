-- =====================================================================
-- Abonelik / yetkilendirme şeması.
-- ALTIN KURAL: Yetki (entitlement) ASLA istemcide belirlenmez.
-- Telefon "ben Pro'yum" der; sunucu Google'a sorar ve karar verir.
-- =====================================================================

CREATE TABLE app_user (
    id                  INTEGER PRIMARY KEY,
    anon_id             TEXT NOT NULL UNIQUE,   -- cihaz kurulumunda üretilen UUID
    play_obfuscated_id  TEXT,                   -- obfuscatedAccountId ile eşleşme
    created_at          TEXT NOT NULL,
    last_seen_at        TEXT,
    country             TEXT,
    app_version         TEXT
);

CREATE TABLE product (
    id                  INTEGER PRIMARY KEY,
    play_product_id     TEXT NOT NULL UNIQUE,   -- 'edge_pro', 'edge_elite'
    base_plan_id        TEXT NOT NULL,          -- 'monthly', 'annual'
    tier                TEXT NOT NULL,          -- FREE | PRO | ELITE
    period              TEXT NOT NULL,          -- P1M | P1Y
    is_active           INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE subscription (
    id                      INTEGER PRIMARY KEY,
    user_id                 INTEGER NOT NULL REFERENCES app_user(id),
    purchase_token          TEXT NOT NULL UNIQUE,   -- Google'ın tekil anahtarı
    play_product_id         TEXT NOT NULL,
    base_plan_id            TEXT,
    offer_id                TEXT,
    state                   TEXT NOT NULL,   -- ACTIVE|IN_GRACE|ON_HOLD|PAUSED|CANCELED|EXPIRED
    tier                    TEXT NOT NULL,
    start_at                TEXT,
    expiry_at               TEXT,
    auto_renewing           INTEGER NOT NULL DEFAULT 1,
    is_acknowledged         INTEGER NOT NULL DEFAULT 0,
    is_test_purchase        INTEGER NOT NULL DEFAULT 0,
    linked_purchase_token   TEXT,            -- upgrade/downgrade zinciri
    last_verified_at        TEXT NOT NULL,
    raw_json                TEXT
);
CREATE INDEX ix_sub_user ON subscription(user_id, state);
CREATE INDEX ix_sub_expiry ON subscription(expiry_at);

-- Google Real-time Developer Notifications ham kaydı (idempotency için)
CREATE TABLE rtdn_event (
    id                  INTEGER PRIMARY KEY,
    message_id          TEXT NOT NULL UNIQUE,   -- Pub/Sub messageId -> tekrar işleme yok
    notification_type   INTEGER,
    purchase_token      TEXT,
    received_at         TEXT NOT NULL,
    processed_at        TEXT,
    payload_json        TEXT NOT NULL
);

-- Ücretsiz kullanıcı kotası (madde: free tier limiti)
CREATE TABLE usage_quota (
    user_id         INTEGER NOT NULL REFERENCES app_user(id),
    quota_key       TEXT NOT NULL,      -- 'match_analysis', 'model_run'
    period_start    TEXT NOT NULL,      -- UTC gün başlangıcı
    used            INTEGER NOT NULL DEFAULT 0,
    limit_value     INTEGER NOT NULL,
    PRIMARY KEY (user_id, quota_key, period_start)
);

-- İstemciye verilen kısa ömürlü imzalı yetki (offline çalışma için)
CREATE TABLE entitlement_token (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES app_user(id),
    tier            TEXT NOT NULL,
    issued_at       TEXT NOT NULL,
    expires_at      TEXT NOT NULL,      -- kısa: 24 saat
    grace_until     TEXT NOT NULL,      -- ağ yoksa tolerans: +7 gün
    jti             TEXT NOT NULL UNIQUE
);
