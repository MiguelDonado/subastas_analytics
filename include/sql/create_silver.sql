-- =============================================================================
-- Schema "silver": physical model of data_modeling/silver/OLTP_E-R.pdf
-- (PostgreSQL)
--
-- Every BOE announcement is stored as its own auction and lots, and is never
-- overwritten. When a plot is auctioned again, its new lot links to the same row
-- in catastral_references, which keeps the price history of the plot.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS silver;

-- -----------------------------------------------------------------------------
-- auctions: one row per BOE announcement
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.auctions (
    auction_id        BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    boe_ref           VARCHAR(30)  NOT NULL UNIQUE,              -- e.g. BOE-B-2026-34259
    announcement_text TEXT         NOT NULL,                     -- copied from bronze.auctions
    publication_date  DATE         NOT NULL,
    held_date         DATE         NOT NULL,                     
    ingested_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    source_url        TEXT         NOT NULL UNIQUE
);

-- -----------------------------------------------------------------------------
-- lots: one row per lot of an announcement
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.lots (
    lot_id            BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    starting_price    NUMERIC(14, 2)  NOT NULL CHECK (starting_price >= 0),  -- earliest round offered in the announcement
    auction_id        BIGINT          NOT NULL REFERENCES silver.auctions (auction_id) ON DELETE CASCADE,
    lot_number        INTEGER         NOT NULL,
    UNIQUE (auction_id, lot_number)
);

COMMENT ON COLUMN silver.lots.starting_price IS 'Starting price for the CURRENT auction.';

-- -----------------------------------------------------------------------------
-- municipios
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.municipios (
    municipio_id      BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio         VARCHAR(100)  NOT NULL,
    province          VARCHAR(100)  NOT NULL,
    UNIQUE (municipio, province)
);

-- -----------------------------------------------------------------------------
-- catastral_references: one row per real plot or property, however many times it is auctioned
-- References that are not found in Catastro are not stored.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.catastral_references (
    catastral_reference_id  BIGINT            GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    catastral_reference     VARCHAR(20)       NOT NULL UNIQUE CHECK (char_length(catastral_reference) = 20),  -- no spaces, uppercase; references of any other length are not stored
    latitude                DOUBLE PRECISION  NOT NULL,
    longitude               DOUBLE PRECISION  NOT NULL,
    use                     VARCHAR(100)      NOT NULL,
    class                   VARCHAR(100)      NOT NULL,
    surface                 NUMERIC(12, 2)    NOT NULL,
    municipio_id            BIGINT            NOT NULL REFERENCES silver.municipios (municipio_id)
);

CREATE INDEX IF NOT EXISTS ix_catastral_references_municipio_id
    ON silver.catastral_references (municipio_id);

-- -----------------------------------------------------------------------------
-- lots_catastral_references: which references each lot contains
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.lots_catastral_references (
    lot_id                  BIGINT  NOT NULL REFERENCES silver.lots (lot_id) ON DELETE CASCADE,
    catastral_reference_id  BIGINT  NOT NULL REFERENCES silver.catastral_references (catastral_reference_id) ON DELETE CASCADE,
    PRIMARY KEY (lot_id, catastral_reference_id)
);

-- The primary key's index starts with lot_id, so it can't look up rows by reference alone
CREATE INDEX IF NOT EXISTS ix_lots_catastral_references_catastral_reference_id
    ON silver.lots_catastral_references (catastral_reference_id);