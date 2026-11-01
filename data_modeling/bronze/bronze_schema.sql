-- =============================================================================
-- Schema "bronze": physical model of data_modeling/bronze/OLTP_bronze.pdf
-- (PostgreSQL)
--
-- Stores BOE auction announcements exactly as received from the BOE Open Data
-- API, so silver can be rebuilt without calling the API again.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS bronze;

-- -----------------------------------------------------------------------------
-- auctions: one row per BOE announcement (BOE-B-YYYY-NNNNN)
-- -----------------------------------------------------------------------------
CREATE TABLE bronze.auctions (
    auction_id        BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    boe_ref           VARCHAR(30)  NOT NULL UNIQUE,              -- e.g. BOE-B-2026-34259
    announcement_text TEXT         NOT NULL,                     -- full announcement text, as received
    publication_date  DATE         NOT NULL,                     -- BOE publication date
    ingested_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),       -- load timestamp
    source_url        TEXT         NOT NULL
);

COMMENT ON TABLE  bronze.auctions IS 'BOE auction announcements, stored as received from the BOE Open Data API.';
COMMENT ON COLUMN bronze.auctions.boe_ref IS 'BOE persistent identifier (BOE-B-YYYY-NNNNN).';
COMMENT ON COLUMN bronze.auctions.announcement_text IS 'Full announcement text, unmodified. Input to the LLM extraction that builds silver.';
COMMENT ON COLUMN bronze.auctions.ingested_at IS 'When the announcement was loaded into bronze.';
