"""Load BOE announcements into the bronze layer."""

from .common import read_sql


def stored_source_urls(conn, urls: list[str]) -> set[str]:
    """Return which of `urls` are already stored as source_url in bronze.auctions.

    Parameters:
    - conn: Open psycopg2 connection. The caller closes it.
    - urls: The url_xml of the candidates.
    """
    if not urls:
        return set()
    with conn.cursor() as cursor:
        cursor.execute(read_sql("select_bronze_stored_urls.sql"), {"urls": urls})
        return {row[0] for row in cursor.fetchall()}


def insert_auctions(conn, auctions: list[dict]) -> int:
    """Insert the announcements into bronze and return how many were new.

    Parameters:
    - conn: Open psycopg2 connection. The caller closes it.
    - auctions: The dictionaries that parse_auction returns.
    """
    insert_sql = read_sql("insert_bronze_auction.sql")
    inserted = 0
    with conn.cursor() as cursor:
        for auction in auctions:
            cursor.execute(insert_sql, auction)
            inserted += cursor.rowcount   # 1 if inserted, 0 if already stored
    conn.commit()
    return inserted
