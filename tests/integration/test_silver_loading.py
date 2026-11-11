"""What load_silver stores in each case, against a real database (S4–S10, S12, S16–S21, S25, S28–S30, S32, S34, S35)."""

import logging
from datetime import date
from decimal import Decimal

import anthropic
import pytest
from helpers import (
    HELD_DATE,
    PUBLICATION_DATE,
    REF_A,
    REF_B,
    REF_C,
    REF_D,
    TEXT_PREFIX,
    announcement,
    catastro_info,
    claude_error,
    lot,
    rows,
)

from subastas_analytics.clients.llm import MODEL, PROMPT_HASH, Announcement
from subastas_analytics.loaders.silver import load_silver

pytestmark = pytest.mark.integration


def stored_references(conn) -> list[str]:
    return [reference for (reference,) in rows(conn, "SELECT catastral_reference FROM silver.catastral_references ORDER BY 1")]


def stored_links(conn) -> list[tuple[int, str]]:
    """(lot_number, catastral_reference) of every link between a lot and a reference."""
    return rows(conn, """
        SELECT l.lot_number, c.catastral_reference
        FROM silver.lots_catastral_references lc
        JOIN silver.lots l USING (lot_id)
        JOIN silver.catastral_references c USING (catastral_reference_id)
        ORDER BY 1, 2
    """)


######################################
# Normal load
######################################

def test_announcement_is_stored_in_every_table(conn, add_bronze, claude, goolzoom, caplog):
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = announcement(
        lot(1, price=53754.21, references=[REF_A]),
        lot(2, price=1000.5, references=[REF_B, REF_C]),
    )
    goolzoom.answers[REF_C] = catastro_info(REF_C, municipality="SEGOVIA", province="SEGOVIA", qualification="MM Pinar maderable")

    with caplog.at_level(logging.INFO):
        assert load_silver(conn) == {"loaded": ["BOE-B-1"], "failed": []}

    assert rows(conn, """
        SELECT boe_ref, announcement_text, publication_date, held_date, source_url, extraction_model, extraction_prompt_hash
        FROM silver.auctions
    """) == [(
        "BOE-B-1", TEXT_PREFIX + "BOE-B-1", PUBLICATION_DATE, HELD_DATE,
        "https://www.boe.es/diario_boe/xml.php?id=BOE-B-1", MODEL, PROMPT_HASH,
    )]
    assert rows(conn, "SELECT lot_number, starting_price FROM silver.lots ORDER BY 1") == [
        (1, Decimal("53754.21")),
        (2, Decimal("1000.50")),
    ]
    assert stored_links(conn) == [(1, REF_A), (2, REF_B), (2, REF_C)]
    # REF_A and REF_B share Valladolid, so it's stored once
    assert rows(conn, "SELECT municipio, province FROM silver.municipios ORDER BY 1") == [
        ("SEGOVIA", "SEGOVIA"),
        ("VALLADOLID", "VALLADOLID"),
    ]
    assert rows(conn, f"""
        SELECT latitude, longitude, use, class, surface, qualification
        FROM silver.catastral_references WHERE catastral_reference = '{REF_C}'
    """) == [(41.64, -4.72, "Residencial", "Urbano", Decimal("75.00"), "MM Pinar maderable")]
    assert "LOADED BOE-B-1" in caplog.text


def test_s12_fallback_model_is_stored(conn, add_bronze, claude):
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = (announcement(), "claude-sonnet-5-5")

    load_silver(conn)

    assert rows(conn, "SELECT extraction_model FROM silver.auctions") == [("claude-sonnet-5-5",)]


def test_s25_reference_without_crops_is_stored_with_null_qualification(conn, add_bronze):
    add_bronze("BOE-B-1")   # REF_A, with qualification None by default

    load_silver(conn)

    assert rows(conn, "SELECT qualification FROM silver.catastral_references") == [(None,)]


######################################
# FAILED: decided by Claude's answer
######################################

@pytest.mark.parametrize("claude_answer, reason, model", [
    pytest.param(claude_error(anthropic.BadRequestError), "BadRequestError: ", None, id="s4_claude_rejects_the_request"),
    pytest.param(RuntimeError("Claude declined the request"), "RuntimeError: Claude declined the request", None,
                 id="s5_s6_refused_or_cut_off"),
    pytest.param(announcement(held_date=None), "No held date", MODEL, id="s7_no_held_date"),
    pytest.param(Announcement(held_date=HELD_DATE, lots=[]), "No valid lots", MODEL, id="s8_no_lots"),
    pytest.param(announcement(lot(price=None)), "No valid lots", MODEL, id="s9_no_valid_lots"),
    pytest.param(announcement(held_date=date(2026, 11, 4)), "Held date before publication date", MODEL,
                 id="s10_held_before_publication"),
])
def test_failed_announcement_is_recorded_and_the_next_one_still_loads(conn, add_bronze, claude, caplog,
                                                                     claude_answer, reason, model):
    add_bronze("BOE-B-1", "BOE-B-2")
    claude.answers["BOE-B-1"] = claude_answer

    assert load_silver(conn) == {"loaded": ["BOE-B-2"], "failed": ["BOE-B-1"]}

    [(boe_ref, stored_reason, stored_model, prompt_hash)] = rows(conn, """
        SELECT boe_ref, reason, extraction_model, extraction_prompt_hash FROM silver.failed_announcements
    """)
    assert boe_ref == "BOE-B-1"
    assert stored_reason.startswith(reason)
    # The model is only known when Claude answered
    assert stored_model == model
    assert prompt_hash == PROMPT_HASH
    assert rows(conn, "SELECT boe_ref FROM silver.auctions") == [("BOE-B-2",)]
    assert "FAILED BOE-B-1" in caplog.text


######################################
# FAILED: rejected by the database or by Goolzoom's data
######################################

@pytest.mark.parametrize("claude_answer, goolzoom_answers, reason", [
    pytest.param(announcement(lot(1, references=[REF_B]), lot(1, references=[REF_C])), {},
                 "UniqueViolation", id="s19_same_lot_number_twice"),
    pytest.param(announcement(lot(price=0, references=[REF_B])), {}, "CheckViolation", id="s20_price_zero"),
    pytest.param(announcement(lot(price=1e13, references=[REF_B])), {}, "NumericValueOutOfRange", id="s21_price_too_big"),
    pytest.param(announcement(lot(references=[REF_B])), {REF_B: KeyError("plot")}, "KeyError", id="s28_unexpected_structure"),
    pytest.param(announcement(lot(references=[REF_B])), {REF_B: catastro_info(REF_B, municipality="x" * 101)},
                 "StringDataRightTruncation", id="s32_value_too_long"),
    pytest.param(announcement(lot(references=[REF_B])), {REF_B: ValueError(f"Reference {REF_B} has no surface")},
                 "ValueError", id="s34_empty_surface"),
    pytest.param(announcement(lot(references=[REF_B])), {REF_B: catastro_info(REF_B, surface=0)},
                 "CheckViolation", id="s34_surface_zero"),
    pytest.param(announcement(lot(references=[REF_B])), {REF_B: catastro_info(REF_B, latitude=-4.72, longitude=41.64)},
                 "CheckViolation", id="s35_coordinates_swapped"),
])
def test_rejected_insert_undoes_the_whole_announcement(conn, add_bronze, claude, goolzoom,
                                                       claude_answer, goolzoom_answers, reason):
    """The path of an insert error (docs/6.failure_modes.md): the whole announcement is rolled back,
    the new references included, it's FAILED, and the next one still loads."""
    add_bronze("BOE-B-1", "BOE-B-2")
    claude.answers["BOE-B-1"] = claude_answer
    goolzoom.answers.update(goolzoom_answers)

    assert load_silver(conn) == {"loaded": ["BOE-B-2"], "failed": ["BOE-B-1"]}

    [(stored_reason,)] = rows(conn, "SELECT reason FROM silver.failed_announcements")
    assert stored_reason.startswith(reason)
    # Only the 2nd announcement is stored, with its REF_A. Nothing of the 1st is left
    assert rows(conn, "SELECT boe_ref FROM silver.auctions") == [("BOE-B-2",)]
    assert stored_references(conn) == [REF_A]
    assert stored_links(conn) == [(1, REF_A)]


def test_s19_same_lot_number_is_fine_if_one_of_them_is_rejected(conn, add_bronze, claude):
    """S19 only happens if both lots pass. A rejected lot is never inserted, so there's no conflict."""
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = announcement(lot(1, price=None), lot(1))

    assert load_silver(conn)["loaded"] == ["BOE-B-1"]
    assert rows(conn, "SELECT lot_number FROM silver.lots") == [(1,)]


######################################
# Rejected lots: the rest of the announcement is stored
######################################

def test_s16_lot_without_starting_price_is_rejected(conn, add_bronze, claude, goolzoom, caplog):
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = announcement(lot(1, price=None, references=[REF_B]), lot(2))

    assert load_silver(conn)["loaded"] == ["BOE-B-1"]

    assert stored_links(conn) == [(2, REF_A)]
    # Rejected before its references are looked up
    assert [call.args[0] for call in goolzoom.call_args_list] == [REF_A]
    assert "REJECTED BOE-B-1 lot 1: the lot has no starting price" in caplog.text


def test_s17_lot_without_references_is_rejected(conn, add_bronze, claude, caplog):
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = announcement(lot(1, references=[]), lot(2))

    load_silver(conn)

    assert stored_links(conn) == [(2, REF_A)]
    assert "REJECTED BOE-B-1 lot 1" in caplog.text


def test_s18_lot_with_an_invalid_reference_is_rejected_with_its_valid_ones(conn, add_bronze, claude, goolzoom, caplog):
    """S18: REF_B is valid and gets inserted, but REF_C is invalid, so the lot and REF_B are undone."""
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = announcement(lot(1, references=[REF_B, REF_C]), lot(2))
    goolzoom.answers[REF_C] = None

    load_silver(conn)

    assert stored_links(conn) == [(2, REF_A)]
    assert stored_references(conn) == [REF_A]
    assert f"REJECTED BOE-B-1 lot 1: reference '{REF_C}'" in caplog.text


def test_savepoint_example_from_the_docs(conn, add_bronze, claude, goolzoom):
    """The example in "How the valid references of a rejected lot are undone" (docs/6.failure_modes.md):
    3 lots, lot 2 rejected. Its reference C is undone, A and D are kept."""
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = announcement(
        lot(1, references=[REF_A]),
        lot(2, references=[REF_C, REF_B]),
        lot(3, references=[REF_D]),
    )
    goolzoom.answers[REF_B] = None

    load_silver(conn)

    assert stored_references(conn) == [REF_A, REF_D]
    assert stored_links(conn) == [(1, REF_A), (3, REF_D)]


def test_rejected_lot_doesnt_undo_a_reference_of_an_earlier_lot(conn, add_bronze, claude, goolzoom):
    """Lot 2 also has REF_A, inserted by lot 1 before lot 2's savepoint, so undoing lot 2 keeps it."""
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = announcement(lot(1, references=[REF_A]), lot(2, references=[REF_A, REF_B]))
    goolzoom.answers[REF_B] = None

    load_silver(conn)

    assert stored_links(conn) == [(1, REF_A)]


######################################
# Catastral references
######################################

def test_s29_reauction_links_to_the_stored_reference(conn, add_bronze):
    """S29: two announcements of the same plot share one reference row, which keeps its price history."""
    add_bronze("BOE-B-1", "BOE-B-2")   # Both have REF_A, the default

    load_silver(conn)

    assert stored_references(conn) == [REF_A]
    assert rows(conn, """
        SELECT a.boe_ref, c.catastral_reference
        FROM silver.lots_catastral_references lc
        JOIN silver.lots l USING (lot_id)
        JOIN silver.auctions a USING (auction_id)
        JOIN silver.catastral_references c USING (catastral_reference_id)
        ORDER BY 1
    """) == [("BOE-B-1", REF_A), ("BOE-B-2", REF_A)]


def test_s30_same_reference_written_two_ways_gives_one_link(conn, add_bronze, claude, goolzoom):
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = announcement(lot(references=["1111111 AA1111A 0001 AA", REF_A]))

    assert load_silver(conn)["loaded"] == ["BOE-B-1"]

    assert stored_links(conn) == [(1, REF_A)]
    # The second spelling is found already stored, so Goolzoom is called once
    assert goolzoom.call_count == 1


######################################
# STOPPED
######################################

def test_stopped_is_logged(conn, add_bronze, claude, caplog):
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = claude_error(anthropic.OverloadedError)

    with pytest.raises(anthropic.OverloadedError):
        load_silver(conn)

    assert "STOPPED at BOE-B-1" in caplog.text