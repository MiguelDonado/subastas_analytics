"""load_gold.sql against a real database (G1–G4).

Each test builds silver with load_silver and the fakes, then runs load_gold.sql and reads gold.app_lots,
the view the app reads.
"""

from datetime import date
from decimal import Decimal

import psycopg2
import pytest
from helpers import HELD_DATE, PUBLICATION_DATE, REF_A, REF_B, REF_C, announcement, catastro_info, lot, rows

from subastas_analytics.loaders.common import read_sql
from subastas_analytics.loaders.silver import load_silver

pytestmark = pytest.mark.integration


def load_gold(conn) -> None:
    """Run load_gold.sql as Airflow's SQLExecuteQueryOperator does: the whole file in one execute, then a commit."""
    cursor = conn.cursor()
    cursor.execute(read_sql("load_gold.sql"))
    conn.commit()


def app_lots(conn, columns: str) -> list[tuple]:
    return rows(conn, f"SELECT {columns} FROM gold.app_lots ORDER BY lot_id")


def test_app_lots_has_one_row_per_lot(conn, add_bronze, claude):
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = announcement(lot(1, price=50000, references=[REF_A, REF_B]), lot(2, references=[REF_C]))
    load_silver(conn)

    load_gold(conn)

    assert app_lots(conn, """
        boe_ref, announcement_url, lot_number, starting_price, total_surface, reference_count,
        publication_date, held_date, province, municipio, is_latest
    """) == [
        # Lot 1: the surfaces of its 2 references (75 m² each) are summed
        ("BOE-B-1", "https://www.boe.es/diario_boe/txt.php?id=BOE-B-1", 1, Decimal("50000.00"), Decimal("150.00"), 2,
         PUBLICATION_DATE, HELD_DATE, "VALLADOLID", "VALLADOLID", True),
        ("BOE-B-1", "https://www.boe.es/diario_boe/txt.php?id=BOE-B-1", 2, Decimal("50000.00"), Decimal("75.00"), 1,
         PUBLICATION_DATE, HELD_DATE, "VALLADOLID", "VALLADOLID", True),
    ]


def test_running_it_twice_gives_the_same_gold(conn, add_bronze):
    add_bronze("BOE-B-1", "BOE-B-2")
    load_silver(conn)

    load_gold(conn)
    first = app_lots(conn, "*")
    load_gold(conn)

    assert app_lots(conn, "*") == first


@pytest.mark.parametrize("uses, expected", [
    pytest.param(["Agrario", "Agrario", "Residencial"], "Agrario", id="most_common"),
    pytest.param(["Residencial", "Agrario"], "Agrario", id="tie_first_alphabetically"),
])
def test_g2_lot_shows_the_most_common_value_of_its_references(conn, add_bronze, claude, goolzoom, uses, expected):
    references = [REF_A, REF_B, REF_C][:len(uses)]
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = announcement(lot(references=references))
    for reference, use in zip(references, uses):
        goolzoom.answers[reference] = catastro_info(reference, use=use)
    load_silver(conn)

    load_gold(conn)

    assert app_lots(conn, "use") == [(expected,)]


@pytest.mark.parametrize("qualifications, expected", [
    pytest.param([None, None], None, id="g3_none_has_one"),
    pytest.param([None, "MM Pinar maderable"], "MM Pinar maderable", id="nulls_are_ignored"),
])
def test_g3_qualification(conn, add_bronze, claude, goolzoom, qualifications, expected):
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = announcement(lot(references=[REF_A, REF_B]))
    for reference, qualification in zip([REF_A, REF_B], qualifications):
        goolzoom.answers[reference] = catastro_info(reference, qualification=qualification)
    load_silver(conn)

    load_gold(conn)

    assert app_lots(conn, "qualification") == [(expected,)]


def test_reauction_only_the_newest_lot_is_latest(conn, add_bronze, claude):
    """The same property (REF_A) auctioned twice: only the newer announcement is the latest.
    REF_B is another property, so its only lot is the latest too."""
    add_bronze("BOE-B-1", publication_date=date(2026, 11, 3))
    add_bronze("BOE-B-2", publication_date=date(2026, 11, 10))
    add_bronze("BOE-B-3", publication_date=date(2026, 11, 3))
    claude.answers["BOE-B-3"] = announcement(lot(references=[REF_B]))
    load_silver(conn)

    load_gold(conn)

    assert rows(conn, "SELECT boe_ref, is_latest FROM gold.app_lots ORDER BY boe_ref") == [
        ("BOE-B-1", False),
        ("BOE-B-2", True),
        ("BOE-B-3", True),
    ]


def test_g1_g4_failed_load_keeps_the_previous_gold(conn, add_bronze):
    """G4: a source_url without /xml.php breaks the CHECK of gold.dim_auctions.
    G1: the load is one transaction, so the app keeps showing the previous gold."""
    add_bronze("BOE-B-1")
    load_silver(conn)
    load_gold(conn)
    before = app_lots(conn, "*")

    # The BOE changes its link format
    conn.cursor().execute("UPDATE silver.auctions SET source_url = 'https://www.boe.es/new/BOE-B-1'")
    conn.commit()

    with pytest.raises(psycopg2.errors.CheckViolation):
        load_gold(conn)
    conn.rollback()

    assert app_lots(conn, "*") == before