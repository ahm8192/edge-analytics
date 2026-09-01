-- =====================================================================
-- Şema tasarımı doğrudan checklist maddelerine karşılık gelir.
-- Anahtar ilke: HER satır "ne zaman gözlendi" (observed_at) taşır.
-- Böylece geçmişe dönük tahmin üretirken sızıntı (leakage) imkânsız olur.
-- =====================================================================

-- ---------- Sağlayıcı / köken (madde 1, 2, 4) ------------------------
CREATE TABLE source (
    id              INTEGER PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,      -- 'provider_a', 'provider_b'
    kind            TEXT NOT NULL,             -- stats | odds | news | weather
    trust_weight    REAL NOT NULL DEFAULT 1.0, -- çelişkide ağırlık
    is_active       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE ingest_run (
    id              INTEGER PRIMARY KEY,
    source_id       INTEGER NOT NULL REFERENCES source(id),
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL,             -- ok | partial | failed
    row_count       INTEGER DEFAULT 0,
    error_text      TEXT
);

-- ---------- Kimlik eşleme (madde 6) ----------------------------------
CREATE TABLE team (
    id              INTEGER PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    country         TEXT,
    founded_year    INTEGER
);

CREATE TABLE team_alias (
    source_id       INTEGER NOT NULL REFERENCES source(id),
    external_id     TEXT NOT NULL,
    raw_name        TEXT NOT NULL,
    team_id         INTEGER NOT NULL REFERENCES team(id),
    confidence      REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (source_id, external_id)
);

-- ---------- Lig ve rejim (madde 10, 12, 13, 57) ----------------------
CREATE TABLE league (
    id                  INTEGER PRIMARY KEY,
    name                TEXT NOT NULL,
    country             TEXT,
    tier                INTEGER NOT NULL,      -- 1 = en üst
    gender              TEXT NOT NULL DEFAULT 'M',   -- M | F  (madde 13)
    age_group           TEXT NOT NULL DEFAULT 'senior',
    data_quality        REAL NOT NULL DEFAULT 1.0,   -- madde 12
    strength_coef       REAL NOT NULL DEFAULT 1.0    -- madde 57
);

CREATE TABLE league_regime (              -- madde 10: kural değişimi = rejim kırılması
    id              INTEGER PRIMARY KEY,
    league_id       INTEGER NOT NULL REFERENCES league(id),
    effective_from  TEXT NOT NULL,
    label           TEXT NOT NULL,        -- 'VAR', '5_subs', 'no_crowd'
    notes           TEXT
);

-- ---------- Maç ------------------------------------------------------
CREATE TABLE match (
    id              INTEGER PRIMARY KEY,
    league_id       INTEGER NOT NULL REFERENCES league(id),
    season          TEXT NOT NULL,
    kickoff_utc     TEXT NOT NULL,
    home_team_id    INTEGER NOT NULL REFERENCES team(id),
    away_team_id    INTEGER NOT NULL REFERENCES team(id),
    stage           TEXT NOT NULL DEFAULT 'league',  -- league|cup|playoff (madde 35)
    leg             INTEGER,                          -- madde 36
    tie_id          TEXT,                             -- iki ayaklı eşleşme anahtarı
    venue_id        INTEGER,
    crowd_status    TEXT DEFAULT 'normal',            -- normal|restricted|closed (madde 32,45)
    home_goals      INTEGER,
    away_goals      INTEGER,
    status          TEXT NOT NULL DEFAULT 'scheduled',
    UNIQUE (league_id, season, kickoff_utc, home_team_id, away_team_id)
);

-- Her sağlayıcının ham kaydı ayrı durur -> çapraz doğrulama (madde 1, 2)
CREATE TABLE match_source_record (
    id              INTEGER PRIMARY KEY,
    match_id        INTEGER NOT NULL REFERENCES match(id),
    source_id       INTEGER NOT NULL REFERENCES source(id),
    ingest_run_id   INTEGER REFERENCES ingest_run(id),
    observed_at     TEXT NOT NULL,          -- madde 4
    payload_json    TEXT NOT NULL,
    payload_hash    TEXT NOT NULL,
    UNIQUE (match_id, source_id, payload_hash)
);

CREATE TABLE source_conflict (             -- madde 1: çelişki logu
    id              INTEGER PRIMARY KEY,
    match_id        INTEGER NOT NULL REFERENCES match(id),
    field           TEXT NOT NULL,
    values_json     TEXT NOT NULL,
    resolved_value  TEXT,
    resolution      TEXT,                  -- trust_weight | majority | manual | unresolved
    detected_at     TEXT NOT NULL
);

-- ---------- Olay bazlı veri (madde 2, 48, 49, 51, 56, 58) ------------
CREATE TABLE shot_event (
    id                  INTEGER PRIMARY KEY,
    match_id            INTEGER NOT NULL REFERENCES match(id),
    source_id           INTEGER NOT NULL REFERENCES source(id),
    team_id             INTEGER NOT NULL REFERENCES team(id),
    player_id           INTEGER,
    minute              INTEGER NOT NULL,
    period              INTEGER NOT NULL,
    x                   REAL,               -- 0..100 normalize saha koordinatı
    y                   REAL,
    xg                  REAL NOT NULL,
    xg_model_version    TEXT NOT NULL,      -- madde 47: hangi xG modeli
    is_penalty          INTEGER NOT NULL DEFAULT 0,   -- madde 49
    is_set_piece        INTEGER NOT NULL DEFAULT 0,   -- madde 51
    is_goal             INTEGER NOT NULL DEFAULT 0,
    score_state         INTEGER NOT NULL DEFAULT 0,   -- madde 56: şut anındaki averaj
    men_on_pitch_diff   INTEGER NOT NULL DEFAULT 0,   -- madde 58: kırmızı kart etkisi
    observed_at         TEXT NOT NULL
);
CREATE INDEX ix_shot_match ON shot_event(match_id);

CREATE TABLE possession_summary (          -- madde 50: PPDA, field tilt
    match_id        INTEGER NOT NULL REFERENCES match(id),
    team_id         INTEGER NOT NULL REFERENCES team(id),
    ppda            REAL,
    field_tilt      REAL,
    passes_final_third INTEGER,
    observed_at     TEXT NOT NULL,
    PRIMARY KEY (match_id, team_id)
);

-- ---------- Kadro ve oyuncu (madde 15-30) ----------------------------
CREATE TABLE player (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    birth_date      TEXT,
    primary_position TEXT
);

CREATE TABLE lineup_entry (
    match_id        INTEGER NOT NULL REFERENCES match(id),
    team_id         INTEGER NOT NULL REFERENCES team(id),
    player_id       INTEGER NOT NULL REFERENCES player(id),
    is_starter      INTEGER NOT NULL,
    minutes_played  INTEGER,
    position        TEXT,
    observed_at     TEXT NOT NULL,
    PRIMARY KEY (match_id, player_id)
);

CREATE TABLE player_rating (               -- madde 18: marjinal xG katkısı
    player_id       INTEGER NOT NULL REFERENCES player(id),
    as_of           TEXT NOT NULL,
    off_contrib     REAL NOT NULL,         -- 90 dk başına xG katkısı
    def_contrib     REAL NOT NULL,
    minutes_sample  INTEGER NOT NULL,      -- madde 53: örneklem kontrolü
    uncertainty     REAL NOT NULL,
    PRIMARY KEY (player_id, as_of)
);

CREATE TABLE availability_news (           -- madde 8: haberin ÇIKMA saati kritik
    id              INTEGER PRIMARY KEY,
    player_id       INTEGER REFERENCES player(id),
    team_id         INTEGER NOT NULL REFERENCES team(id),
    kind            TEXT NOT NULL,         -- injury | suspension | doubt | return
    expected_return TEXT,
    published_at    TEXT NOT NULL,         -- filtre anahtarı
    source_id       INTEGER NOT NULL REFERENCES source(id),
    confidence      REAL NOT NULL DEFAULT 0.5,
    raw_text        TEXT
);

CREATE TABLE coach_spell (                 -- madde 20: teknik direktör değişimi
    id              INTEGER PRIMARY KEY,
    team_id         INTEGER NOT NULL REFERENCES team(id),
    coach_name      TEXT NOT NULL,
    start_date      TEXT NOT NULL,
    end_date        TEXT
);

CREATE TABLE club_event (                  -- madde 28: kriz, maaş, yönetim
    id              INTEGER PRIMARY KEY,
    team_id         INTEGER NOT NULL REFERENCES team(id),
    kind            TEXT NOT NULL,
    published_at    TEXT NOT NULL,
    severity        REAL NOT NULL DEFAULT 0.5,
    notes           TEXT
);

-- ---------- Bağlam (madde 31-45) -------------------------------------
CREATE TABLE venue (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    latitude        REAL, longitude REAL,
    altitude_m      REAL DEFAULT 0,        -- madde 41
    surface         TEXT DEFAULT 'grass',  -- madde 42
    capacity        INTEGER
);

CREATE TABLE weather_observation (         -- madde 40
    match_id        INTEGER PRIMARY KEY REFERENCES match(id),
    temp_c          REAL, wind_kph REAL, precip_mm REAL, humidity REAL,
    forecast_made_at TEXT NOT NULL,        -- tahmin ne zaman alındı (leakage!)
    is_actual       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE referee (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL
);

CREATE TABLE referee_form (                -- madde 43
    referee_id      INTEGER NOT NULL REFERENCES referee(id),
    as_of           TEXT NOT NULL,
    yellow_per_game REAL, red_per_game REAL, pen_per_game REAL,
    fouls_per_card  REAL, matches_sample INTEGER NOT NULL,
    PRIMARY KEY (referee_id, as_of)
);

CREATE TABLE match_officials (
    match_id        INTEGER PRIMARY KEY REFERENCES match(id),
    referee_id      INTEGER REFERENCES referee(id)
);

CREATE TABLE table_standing (              -- madde 33, 34: motivasyon
    league_id       INTEGER NOT NULL REFERENCES league(id),
    season          TEXT NOT NULL,
    team_id         INTEGER NOT NULL REFERENCES team(id),
    as_of           TEXT NOT NULL,
    position        INTEGER NOT NULL,
    points          INTEGER NOT NULL,
    games_played    INTEGER NOT NULL,
    games_remaining INTEGER NOT NULL,
    pts_to_title    INTEGER, pts_to_relegation INTEGER, pts_to_europe INTEGER,
    PRIMARY KEY (league_id, season, team_id, as_of)
);

-- ---------- Oran geçmişi (madde 7, 76-88) ----------------------------
CREATE TABLE bookmaker (
    id              INTEGER PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,
    is_sharp        INTEGER NOT NULL DEFAULT 0,   -- keskin kitap mı (madde 83)
    typical_margin  REAL
);

CREATE TABLE odds_snapshot (               -- madde 7: dakika dakika arşiv
    id              INTEGER PRIMARY KEY,
    match_id        INTEGER NOT NULL REFERENCES match(id),
    bookmaker_id    INTEGER NOT NULL REFERENCES bookmaker(id),
    market          TEXT NOT NULL,         -- 1X2 | OU | AH | BTTS
    line            REAL,                  -- 2.5, -0.5 vb.
    selection       TEXT NOT NULL,         -- HOME|DRAW|AWAY|OVER|UNDER|YES|NO
    price           REAL NOT NULL,         -- ondalık oran
    captured_at     TEXT NOT NULL,
    is_closing      INTEGER NOT NULL DEFAULT 0,   -- madde 76
    max_stake       REAL                   -- likidite göstergesi (madde 82)
);
CREATE INDEX ix_odds_match_time ON odds_snapshot(match_id, captured_at);
CREATE INDEX ix_odds_closing ON odds_snapshot(match_id, is_closing);

-- ---------- Tahmin ve bahis kaydı (madde 94, 95, 100) ----------------
CREATE TABLE prediction (
    id                  INTEGER PRIMARY KEY,
    match_id            INTEGER NOT NULL REFERENCES match(id),
    model_version       TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    as_of               TEXT NOT NULL,     -- hangi bilgi kesim anıyla üretildi
    market              TEXT NOT NULL,
    line                REAL,
    selection           TEXT NOT NULL,
    prob                REAL NOT NULL,
    prob_low            REAL,              -- madde 100: güven aralığı
    prob_high           REAL,
    fair_price          REAL NOT NULL,
    feature_hash        TEXT NOT NULL,     -- yeniden üretilebilirlik
    explanation_json    TEXT               -- madde 100: neden
);
CREATE INDEX ix_pred_match ON prediction(match_id);

CREATE TABLE bet_log (                     -- madde 94, 98
    id                  INTEGER PRIMARY KEY,
    prediction_id       INTEGER NOT NULL REFERENCES prediction(id),
    placed_at           TEXT NOT NULL,
    bookmaker_id        INTEGER REFERENCES bookmaker(id),
    taken_price         REAL NOT NULL,
    stake               REAL NOT NULL,
    stake_method        TEXT NOT NULL,     -- quarter_kelly | flat
    bankroll_before     REAL NOT NULL,
    closing_price       REAL,              -- sonradan doldurulur
    clv_pct             REAL,              -- madde 77
    settled_at          TEXT,
    outcome             TEXT,              -- win | lose | push | void
    pnl                 REAL,
    was_placed          INTEGER NOT NULL DEFAULT 1  -- 0 = sadece kayıt (paper)
);

CREATE TABLE model_health (                -- madde 96, 97
    id              INTEGER PRIMARY KEY,
    model_version   TEXT NOT NULL,
    window_start    TEXT NOT NULL,
    window_end      TEXT NOT NULL,
    n               INTEGER NOT NULL,
    log_loss        REAL NOT NULL,
    brier           REAL NOT NULL,
    calib_error     REAL NOT NULL,
    mean_clv        REAL,
    alarm_level     TEXT NOT NULL DEFAULT 'ok'  -- ok | warn | halt
);

CREATE TABLE stat_revision (               -- madde 5: geriye dönük düzeltme
    id              INTEGER PRIMARY KEY,
    table_name      TEXT NOT NULL,
    row_key         TEXT NOT NULL,
    field           TEXT NOT NULL,
    old_value       TEXT, new_value TEXT,
    revised_at      TEXT NOT NULL,
    source_id       INTEGER REFERENCES source(id)
);
