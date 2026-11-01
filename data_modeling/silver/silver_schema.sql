-- =============================================================================
-- Schema "silver": physical model of data_modeling/silver/OLTP_E-R.drawio
-- (PostgreSQL)
--
-- Cleaned, structured auction data extracted from bronze.auctions.
--
--   auctions 1 ──< lots 1 ──< properties 1 ──< catastral_references >── 1 municipios
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS silver;

-- -----------------------------------------------------------------------------
-- auctions: one row per BOE announcement (BOE-B-YYYY-NNNNN)
-- -----------------------------------------------------------------------------
CREATE TABLE silver.auctions (
    auction_id        BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    boe_ref           VARCHAR(30)  NOT NULL UNIQUE,              -- e.g. BOE-B-2026-34259 (Natural key)
    description       TEXT,
    publication_date  DATE         NOT NULL,                     -- BOE publication date
    held_at           TIMESTAMPTZ  NOT NULL,                     -- date/time the auction is held
    ingested_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),       -- load timestamp
    source_url        TEXT         NOT NULL UNIQUE
);

COMMENT ON TABLE  silver.auctions IS 'Auctions announced in the BOE, one row per announcement.';
COMMENT ON COLUMN silver.auctions.boe_ref IS 'BOE persistent identifier (BOE-B-YYYY-NNNNN). Natural key, joins to bronze.auctions.boe_ref.';
COMMENT ON COLUMN silver.auctions.held_at IS 'Date and time the auction takes place.';
COMMENT ON COLUMN silver.auctions.ingested_at IS 'When the auction was loaded into silver.';

-- -----------------------------------------------------------------------------
-- lots: one row per lot of an auction
-- -----------------------------------------------------------------------------
CREATE TABLE silver.lots (
    lot_id          BIGINT         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    auction_id      BIGINT         NOT NULL
                                   REFERENCES silver.auctions (auction_id) ON DELETE CASCADE,
    lot_number      SMALLINT       NOT NULL CHECK (lot_number > 0),
    starting_price  NUMERIC(14, 2) NOT NULL CHECK (starting_price >= 0),  -- tipo de licitación, EUR
    description     TEXT,
    UNIQUE (auction_id, lot_number)
);

COMMENT ON TABLE  silver.lots IS 'Lots offered in an auction.';
COMMENT ON COLUMN silver.lots.lot_number IS 'Lot number within its auction, as published.';
COMMENT ON COLUMN silver.lots.starting_price IS 'Starting price (tipo de licitación) of the 1st auction round, in EUR. Prices of later rounds are not stored.';

-- -----------------------------------------------------------------------------
-- properties: one row per property included in a lot
-- -----------------------------------------------------------------------------
CREATE TABLE silver.properties (
    property_id  BIGINT  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lot_id       BIGINT  NOT NULL
                         REFERENCES silver.lots (lot_id) ON DELETE CASCADE
);

CREATE INDEX ix_properties_lot_id ON silver.properties (lot_id);

COMMENT ON TABLE silver.properties IS 'Properties (fincas) included in a lot. A property may span several catastral references.';

-- -----------------------------------------------------------------------------
-- municipios: lookup of Spanish municipalities
-- -----------------------------------------------------------------------------
CREATE TABLE silver.municipios (
    municipio_id  INTEGER       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio     VARCHAR(100)  NOT NULL,
    province      VARCHAR(50)   NOT NULL,
    ccaa          VARCHAR(50)   NOT NULL,                        -- comunidad autónoma
    UNIQUE (municipio, province)
);

COMMENT ON TABLE  silver.municipios IS 'Spanish municipalities with their province and autonomous community.';
COMMENT ON COLUMN silver.municipios.ccaa IS 'Comunidad autónoma.';

-- -----------------------------------------------------------------------------
-- catastral_references: one row per catastral reference of a property
-- -----------------------------------------------------------------------------
CREATE TABLE silver.catastral_references (
    catastral_reference_id  BIGINT         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    catastral_reference     VARCHAR(20)    NOT NULL UNIQUE,      -- 14 (parcel) or 20 (unit) chars, natural key
    property_id             BIGINT         NOT NULL
                                           REFERENCES silver.properties (property_id) ON DELETE CASCADE,
    latitude                NUMERIC(9, 6)  CHECK (latitude  BETWEEN  -90 AND  90),
    longitude               NUMERIC(9, 6)  CHECK (longitude BETWEEN -180 AND 180),
    use                     VARCHAR(50),                         -- uso principal (residencial, industrial, ...)
    class                   VARCHAR(20),                         -- clase (urbano, rústico)
    surface                 NUMERIC(12, 2) CHECK (surface >= 0), -- m²
    municipio_id            INTEGER        NOT NULL
                                           REFERENCES silver.municipios (municipio_id),
    reference_value         NUMERIC(14, 2) CHECK (reference_value >= 0), -- valor de referencia, EUR
    description             TEXT
);

CREATE INDEX ix_catastral_references_property_id  ON silver.catastral_references (property_id);
CREATE INDEX ix_catastral_references_municipio_id ON silver.catastral_references (municipio_id);

COMMENT ON TABLE  silver.catastral_references IS 'Catastral references (referencias catastrales) of each property, enriched with cadastre data.';
COMMENT ON COLUMN silver.catastral_references.catastral_reference IS 'Spanish catastral reference: 14 chars (parcel) or 20 chars (property unit). Unique: only the first auction of a plot is loaded; later re-auctions are ignored.';
COMMENT ON COLUMN silver.catastral_references.use IS 'Main use according to the cadastre.';
COMMENT ON COLUMN silver.catastral_references.class IS 'Cadastre class: urbano or rústico.';
COMMENT ON COLUMN silver.catastral_references.surface IS 'Surface in square metres.';
COMMENT ON COLUMN silver.catastral_references.reference_value IS 'Valor de referencia catastral, in EUR.';