-- Which of these boe_refs are already in bronze.
-- fetch_auctions skips them before downloading the announcement or calling Claude, so a rerun
-- of a week doesn't pay Claude again for announcements it already stored.
-- It uses the same key as the ON CONFLICT (boe_ref) of insert_bronze_auction.sql, and its UNIQUE index.
-- ANY(%(boe_refs)s): psycopg2 turns the Python list into a Postgres array.

SELECT boe_ref
FROM bronze.auctions
WHERE boe_ref = ANY(%(boe_refs)s);