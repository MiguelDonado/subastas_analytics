-- Rebuilds gold from silver. One transaction, so the app never sees half-loaded tables
-- and a failure leaves the previous gold in place.

BEGIN;

TRUNCATE
    gold.lots_catastral_references_bridge,
    gold.fact_lots,
    gold.dim_catastral_references,
    gold.dim_auctions,
    gold.dim_date;

INSERT INTO gold.dim_date (date_id, full_date, day, month, year)
-- Outer select: Build the columns
SELECT
    to_char(full_date, 'YYYYMMDD')::INTEGER,
    full_date,
    EXTRACT(DAY FROM full_date),
    EXTRACT(MONTH FROM full_date),
    EXTRACT(YEAR FROM full_date)
FROM (
    -- Inner subquery: Collect the dates
    SELECT publication_date AS full_date FROM silver.auctions
    UNION
    SELECT held_date FROM silver.auctions WHERE held_date IS NOT NULL
) dates;

INSERT INTO gold.dim_auctions (auction_id, boe_ref, announcement_text, source_url)
SELECT auction_id, boe_ref, announcement_text, source_url
FROM silver.auctions;

INSERT INTO gold.dim_catastral_references
    (catastral_reference_id, catastral_reference, latitude, longitude, use, class, surface, qualification, municipio, province)
SELECT
    r.catastral_reference_id, r.catastral_reference, r.latitude, r.longitude,
    r.use, r.class, r.surface, r.qualification, m.municipio, m.province
FROM silver.catastral_references r
JOIN silver.municipios m USING (municipio_id);

-- Because PostgreSQL needs the primary key of the second table too.
-- Think of primary keys as identifiers: once PostgreSQL knows the identifier, 
-- it knows the other attributes belonging to that row.
INSERT INTO gold.fact_lots
    (lot_id, starting_price, total_surface, reference_count, auction_id, lot_number, publication_date_id, held_date_id)
SELECT
    l.lot_id,
    l.starting_price,
    SUM(r.surface),
    COUNT(*),
    l.auction_id,
    l.lot_number,
    to_char(a.publication_date, 'YYYYMMDD')::INTEGER,
    to_char(a.held_date, 'YYYYMMDD')::INTEGER
FROM silver.lots l
JOIN silver.auctions a USING (auction_id)
JOIN silver.lots_catastral_references lr USING (lot_id)
JOIN silver.catastral_references r USING (catastral_reference_id)
GROUP BY l.lot_id, a.auction_id;

INSERT INTO gold.lots_catastral_references_bridge (lot_id, catastral_reference_id)
SELECT lot_id, catastral_reference_id
FROM silver.lots_catastral_references;

COMMIT;
