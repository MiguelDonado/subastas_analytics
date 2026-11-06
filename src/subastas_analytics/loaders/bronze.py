"""Load BOE announcements into the bronze layer."""

from .common import read_sql


def stored_boe_refs(conn, boe_refs: list[str]) -> set[str]:
    """Return which of `boe_refs` are already stored in bronze.auctions.

    Parameters:
    - conn: Open psycopg2 connection. The caller closes it.
    - boe_refs: The boe_ref (summary `identificador`) of the candidates.
    """
    if not boe_refs:
        return set()
    with conn.cursor() as cursor:
        cursor.execute(read_sql("select_bronze_stored_boe_refs.sql"), {"boe_refs": boe_refs})
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
