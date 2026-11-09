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
    source_url        TEXT         NOT NULL UNIQUE,
    extraction_model          VARCHAR(100)  NOT NULL,
    extraction_prompt_hash    VARCHAR(12)   NOT NULL
);

COMMENT ON COLUMN silver.auctions.extraction_model IS 'Claude model that produced this extraction. It can be a fallback instead of the model requested.';
COMMENT ON COLUMN silver.auctions.extraction_prompt_hash IS 'Hash of the extraction instructions (PROMPT_HASH in clients/llm.py). Changes when the prompt, the output schema or the effort changes.';

-- -----------------------------------------------------------------------------
-- lots: one row per lot of an announcement
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.lots (
    lot_id            BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    starting_price    NUMERIC(14, 2)  NOT NULL CHECK (starting_price > 0),  -- earliest round offered in the announcement
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
    latitude                DOUBLE PRECISION  NOT NULL CHECK (latitude BETWEEN 27 AND 44),     -- Spain, including the Canary and Balearic Islands
    longitude               DOUBLE PRECISION  NOT NULL CHECK (longitude BETWEEN -19 AND 5),    -- both checks also catch latitude and longitude being swapped, or Goolzoom changing the format of its coordinates
    use                     VARCHAR(100)      NOT NULL,
    class                   VARCHAR(100)      NOT NULL,
    surface                 NUMERIC(12, 2)    NOT NULL CHECK (surface > 0),
    qualification           VARCHAR(100),                            -- qualification of the biggest crop; NULL if it has no crops
    municipio_id            BIGINT            NOT NULL REFERENCES silver.municipios (municipio_id)
);

COMMENT ON COLUMN silver.catastral_references.qualification IS 'Catastro qualification of the crop with the largest area, as returned by Goolzoom, e.g. MM Pinar maderable. A reference can have several crops, but only this one is kept. NULL if Goolzoom returns no crops, e.g. an apartment.';

-- -----------------------------------------------------------------------------
-- lots_catastral_references: which references each lot contains
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.lots_catastral_references (
    lot_id                  BIGINT  NOT NULL REFERENCES silver.lots (lot_id) ON DELETE CASCADE,
    catastral_reference_id  BIGINT  NOT NULL REFERENCES silver.catastral_references (catastral_reference_id) ON DELETE CASCADE,
    PRIMARY KEY (lot_id, catastral_reference_id)
);

-- -----------------------------------------------------------------------------
-- failed_announcements: every FAILED announcement (no held date, no valid lots, Claude refused, an error...)
-- Kept here so that they aren't sent to Claude again on every run. Delete a row to retry it once the cause is fixed
-- ------------------------------------------------------------- ----------------
CREATE TABLE IF NOT EXISTS silver.failed_announcements (
    boe_ref      VARCHAR(30)  PRIMARY KEY,
    reason       TEXT         NOT NULL,
    failed_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    extraction_model          VARCHAR(100),
    extraction_prompt_hash    VARCHAR(12)   NOT NULL
);

COMMENT ON COLUMN silver.failed_announcements.reason IS 'Why it failed: "No held date", "No valid lots", or "<ErrorType>: <message>" for an error';
COMMENT ON COLUMN silver.failed_announcements.extraction_model IS 'Claude model that produced the extraction this failure is based on. It can be a fallback instead of the model requested. NULL if it failed before Claude answered.';
COMMENT ON COLUMN silver.failed_announcements.extraction_prompt_hash IS 'Hash of the extraction instructions (PROMPT_HASH in clients/llm.py). Changes when the prompt, the output schema or the effort changes.';