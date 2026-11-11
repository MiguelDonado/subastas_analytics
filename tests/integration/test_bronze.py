"""The bronze loader against a real database: an announcement is never stored twice (B14)."""

import pytest
from helpers import PUBLICATION_DATE, TEXT_PREFIX, rows

from subastas_analytics.loaders.bronze import insert_auctions, stored_boe_refs

pytestmark = pytest.mark.integration


def auction(boe_ref: str) -> dict:
    """An announcement as parse_auction returns it."""
    return {
        "boe_ref": boe_ref,
        "announcement_text": TEXT_PREFIX + boe_ref,
        "publication_date": PUBLICATION_DATE.isoformat(),
        "source_url": f"https://www.boe.es/diario_boe/xml.php?id={boe_ref}",
    }


def test_insert_returns_how_many_were_new(conn):
    assert insert_auctions(conn, [auction("BOE-B-1"), auction("BOE-B-2")]) == 2
    assert rows(conn, "SELECT boe_ref FROM bronze.auctions ORDER BY 1") == [("BOE-B-1",), ("BOE-B-2",)]


def test_b14_rerun_of_the_week_stores_nothing_new(conn):
    insert_auctions(conn, [auction("BOE-B-1"), auction("BOE-B-2")])

    # ON CONFLICT (boe_ref) DO NOTHING: the stored ones are skipped, the new one is inserted
    assert insert_auctions(conn, [auction("BOE-B-1"), auction("BOE-B-2"), auction("BOE-B-3")]) == 1
    assert rows(conn, "SELECT count(*) FROM bronze.auctions") == [(3,)]


def test_b14_same_item_twice_in_one_week_is_stored_once(conn):
    """The check before Claude can't see this case, because neither copy is stored yet. ON CONFLICT covers it."""
    assert insert_auctions(conn, [auction("BOE-B-1"), auction("BOE-B-1")]) == 1
    assert rows(conn, "SELECT count(*) FROM bronze.auctions") == [(1,)]


def test_empty_week_inserts_nothing(conn):
    assert insert_auctions(conn, []) == 0


def test_b14_stored_boe_refs_returns_only_the_stored_ones(conn):
    insert_auctions(conn, [auction("BOE-B-1"), auction("BOE-B-2")])

    assert stored_boe_refs(conn, ["BOE-B-1", "BOE-B-3"]) == {"BOE-B-1"}


def test_stored_boe_refs_with_no_candidates_doesnt_query(conn):
    conn.close()   # A query on a closed connection would raise

    assert stored_boe_refs(conn, []) == set()
