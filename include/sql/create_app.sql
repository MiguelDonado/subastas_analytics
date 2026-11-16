-- =============================================================================
-- Schema "app": data entered by the users of the Shiny app
-- (PostgreSQL)
--
-- Created once by hand, for the app. The DAG doesn't touch this schema.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS app;

-- -----------------------------------------------------------------------------
-- users: people who can log in to the app, created by hand (no sign-up)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app.users (
    user_id        BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username       VARCHAR(50)  NOT NULL UNIQUE,
    password_hash  TEXT         NOT NULL,                        -- never the password itself
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON COLUMN app.users.password_hash IS 'Hash made with sodium::password_store() in R. The login checks the typed password against it with sodium::password_verify().';

-- -----------------------------------------------------------------------------
-- lot_reviews: one note per user and lot
-- The lot is boe_ref + lot_number, not lot_id: lot_id may change if silver is rebuilt
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app.lot_reviews (
    user_id     BIGINT       NOT NULL REFERENCES app.users (user_id) ON DELETE CASCADE,
    boe_ref     VARCHAR(30)  NOT NULL,
    lot_number  INTEGER      NOT NULL,
    notes       TEXT,                                                         -- NULL: no note 
    status      VARCHAR(20)  CHECK (status IN ('interested', 'discarded')),   -- NULL: not reviewed
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, boe_ref, lot_number),  -- composite key, no surrogate id: no other table points to this one (more in docs/11.reviews.md, "One row per user and lot")
    -- a row only exists if it has a note or a status
    CONSTRAINT lot_reviews_not_empty CHECK (notes IS NOT NULL OR status IS NOT NULL)
);