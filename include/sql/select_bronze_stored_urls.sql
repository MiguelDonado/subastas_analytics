-- Which of these announcement URLs are already in bronze.
-- fetch_auctions skips them before calling Claude, so a rerun of a week doesn't pay Claude again
-- for announcements it already stored.
-- ANY(%(urls)s): psycopg2 turns the Python list into a Postgres array.

SELECT source_url
FROM bronze.auctions
WHERE source_url = ANY(%(urls)s);