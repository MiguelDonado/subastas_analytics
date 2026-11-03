"""Load BOE announcements into the bronze layer."""

from .common import read_sql


def insert_auctions(conn, auctions: list[dict]) -> int:
    """Insert the announcements into bronze and return how many were new.

    Parameters:
    - conn: Open psycopg2 connection. The caller closes it.
    - auctions: The dictionaries that fetch_auction returns.
    """
    insert_sql = read_sql("insert_bronze_auction.sql")
    inserted = 0
    with conn.cursor() as cursor:
        for auction in auctions:
            cursor.execute(insert_sql, auction)
            inserted += cursor.rowcount   # 1 if inserted, 0 if already stored
    conn.commit()
    return inserted
