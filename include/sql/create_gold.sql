-- =============================================================================
-- Schema "gold": star schema of data_modeling/OLTP/3.gold/E-R.pdf
-- (PostgreSQL)
--
-- Built only from silver, and rebuilt on every run by load_gold.sql.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS gold;

-- -----------------------------------------------------------------------------
-- dim_date: one row per date used by fact_lots
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.dim_date (
    date_id    INTEGER   PRIMARY KEY,                                -- YYYYMMDD, e.g. 20261126
    full_date  DATE      NOT NULL UNIQUE,
    day        SMALLINT  NOT NULL,
    month      SMALLINT  NOT NULL,
    year       SMALLINT  NOT NULL
);

-- -----------------------------------------------------------------------------
-- dim_auctions: one row per BOE announcement
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.dim_auctions (
    auction_id         BIGINT       PRIMARY KEY,                     -- same id as silver.auctions
    boe_ref            VARCHAR(30)  NOT NULL UNIQUE,
    announcement_text  TEXT         NOT NULL,
    source_url         TEXT         NOT NULL UNIQUE
);

-- -----------------------------------------------------------------------------
-- dim_catastral_references: one row per real plot or property
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.dim_catastral_references (
    catastral_reference_id  BIGINT            PRIMARY KEY,           -- same id as silver.catastral_references
    catastral_reference     VARCHAR(20)       NOT NULL UNIQUE CHECK (char_length(catastral_reference) = 20),  -- no spaces, uppercase; references of any other length are not stored
    latitude                DOUBLE PRECISION  NOT NULL,
    longitude               DOUBLE PRECISION  NOT NULL,
    use                     VARCHAR(100)      NOT NULL,
    class                   VARCHAR(100)      NOT NULL,
    surface                 NUMERIC(12, 2)    NOT NULL,
    municipio               VARCHAR(100)      NOT NULL,
    province                VARCHAR(100)      NOT NULL,
);

-- -----------------------------------------------------------------------------
-- fact_lots: one row per lot
-- price per m2 isn't stored: a ratio can't be summed or averaged correctly
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.fact_lots (
    lot_id               BIGINT          PRIMARY KEY,                -- same id as silver.lots
    starting_price       NUMERIC(14, 2)  NOT NULL CHECK (starting_price >= 0),  -- earliest round offered in the announcement                  
    total_surface        NUMERIC(14, 2)  NOT NULL,                   -- sum of the surfaces of its references
    reference_count      INTEGER         NOT NULL,
    auction_id           BIGINT          NOT NULL REFERENCES gold.dim_auctions (auction_id),
    lot_number           INTEGER         NOT NULL,
    publication_date_id  INTEGER         NOT NULL REFERENCES gold.dim_date (date_id),
    held_date_id         INTEGER         NOT NULL REFERENCES gold.dim_date (date_id),  
    UNIQUE (auction_id, lot_number)
);

-- -----------------------------------------------------------------------------
-- lots_catastral_references_bridge: which references each lot contains
-- Joining through it repeats a lot once per reference, so don't sum lot measures after it
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.lots_catastral_references_bridge (
    lot_id                  BIGINT  NOT NULL REFERENCES gold.fact_lots (lot_id),
    catastral_reference_id  BIGINT  NOT NULL REFERENCES gold.dim_catastral_references (catastral_reference_id),
    PRIMARY KEY (lot_id, catastral_reference_id)
);

-- The primary key's index starts with lot_id, so it can't look up rows by reference alone
CREATE INDEX IF NOT EXISTS ix_lots_catastral_references_bridge_catastral_reference_id
    ON gold.lots_catastral_references_bridge (catastral_reference_id);

-- -----------------------------------------------------------------------------
-- app_lots: what the Shiny app reads, one row per lot
-- A lot shows the most common value of its references (the first alphabetically if
-- there is a tie). Its references almost always share them, so one value is enough.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold.app_lots AS
WITH lot_attributes AS (
    SELECT
        b.lot_id,
        mode() WITHIN GROUP (ORDER BY r.province)  AS province,
        mode() WITHIN GROUP (ORDER BY r.municipio) AS municipio,
        mode() WITHIN GROUP (ORDER BY r.use)       AS use,
        mode() WITHIN GROUP (ORDER BY r.class)     AS class
    FROM gold.lots_catastral_references_bridge b
    JOIN gold.dim_catastral_references r USING (catastral_reference_id)
    GROUP BY b.lot_id
)
SELECT
    f.lot_id,
    a.boe_ref,
    replace(a.source_url, '/xml.php', '/txt.php') AS announcement_url,  -- readable page instead of the raw XML
    f.starting_price,
    f.total_surface,
    f.reference_count,
    f.lot_number,
    publication.full_date AS publication_date,
    held.full_date        AS held_date,
    attributes.province,
    attributes.municipio,
    attributes.use,
    attributes.class
FROM gold.fact_lots f
JOIN gold.dim_auctions a USING (auction_id)
JOIN lot_attributes attributes USING (lot_id)
JOIN gold.dim_date publication ON publication.date_id = f.publication_date_id
LEFT JOIN gold.dim_date held ON held.date_id = f.held_date_id;
