"""How many times load_silver pays Claude (and calls Goolzoom), against a real database.

Each call to the fake Claude is a call that would be paid. claude_calls() lists them by boe_ref.
"""

from datetime import date

import anthropic
import psycopg2
import pytest
import requests
from helpers import (
    OFFER_DEADLINE,
    REF_A,
    REF_B,
    REF_C,
    announcement,
    catastro_info,
    claude_calls,
    claude_error,
    lot,
    rows,
)

from subastas_analytics.clients.llm import Announcement
from subastas_analytics.loaders.common import read_sql
from subastas_analytics.loaders.silver import load_silver

pytestmark = pytest.mark.integration


def test_one_claude_call_per_pending_announcement_oldest_first(conn, add_bronze, claude):
    add_bronze("BOE-B-3", publication_date=date(2026, 11, 7))
    add_bronze("BOE-B-1", publication_date=date(2026, 11, 3))
    add_bronze("BOE-B-2", publication_date=date(2026, 11, 5))

    result = load_silver(conn)

    assert claude_calls(claude) == ["BOE-B-1", "BOE-B-2", "BOE-B-3"]
    assert result == {"loaded": ["BOE-B-1", "BOE-B-2", "BOE-B-3"], "failed": []}


def test_s2_nothing_pending_makes_no_calls(conn, claude):
    assert load_silver(conn) == {"loaded": [], "failed": []}
    assert claude.call_count == 0


######################################
# Second run: nothing is paid twice
######################################

# Every way an announcement can end: what Claude answers, what Goolzoom answers, and the list it ends in
ENDINGS = [
    pytest.param(announcement(), {}, "loaded", id="loaded"),
    pytest.param(claude_error(anthropic.BadRequestError), {}, "failed", id="s4_claude_rejects_the_request"),
    pytest.param(RuntimeError("Claude declined the request"), {}, "failed", id="s5_s6_refused_or_cut_off"),
    pytest.param(announcement(offer_deadline=None), {}, "failed", id="s7_no_offer_deadline"),
    pytest.param(announcement(offer_deadline=date(2026, 1, 1)), {}, "failed", id="s10_deadline_before_publication"),
    pytest.param(Announcement(offer_deadline=OFFER_DEADLINE, lots=[]), {}, "failed", id="s8_no_lots"),
    pytest.param(announcement(lot(price=None)), {}, "failed", id="s9_no_valid_lots"),
    pytest.param(announcement(lot(1), lot(1)), {}, "failed", id="s19_same_lot_number_twice"),
    pytest.param(announcement(lot(price=0)), {}, "failed", id="s20_price_zero"),
    pytest.param(announcement(lot(price=1e13)), {}, "failed", id="s21_price_too_big"),
    pytest.param(announcement(), {REF_A: KeyError("plot")}, "failed", id="s28_unexpected_goolzoom_structure"),
    pytest.param(announcement(), {REF_A: catastro_info(REF_A, use="x" * 101)}, "failed", id="s32_value_too_long"),
    pytest.param(announcement(), {REF_A: catastro_info(REF_A, surface=0)}, "failed", id="s34_surface_zero"),
    pytest.param(announcement(), {REF_A: catastro_info(REF_A, latitude=-4.72, longitude=41.64)}, "failed",
                 id="s35_coordinates_swapped"),
]


@pytest.mark.parametrize("claude_answer, goolzoom_answers, ending", ENDINGS)
def test_s1_second_run_makes_no_claude_calls(conn, add_bronze, claude, goolzoom, claude_answer, goolzoom_answers, ending):
    """S1: once an announcement is loaded or FAILED, it's never pending again, so it's only paid once."""
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = claude_answer
    goolzoom.answers.update(goolzoom_answers)

    first = load_silver(conn)
    second = load_silver(conn)

    assert first[ending] == ["BOE-B-1"]
    assert second == {"loaded": [], "failed": []}
    assert claude.call_count == 1


def test_failed_announcement_is_paid_again_only_after_deleting_its_row(conn, add_bronze, claude):
    """The way to retry a FAILED announcement by hand (docs/6.failure_modes.md): delete its row."""
    add_bronze("BOE-B-1")
    claude.answers["BOE-B-1"] = announcement(offer_deadline=None)
    load_silver(conn)
    load_silver(conn)
    assert claude.call_count == 1

    conn.cursor().execute("DELETE FROM silver.failed_announcements WHERE boe_ref = 'BOE-B-1'")
    conn.commit()
    claude.answers["BOE-B-1"] = announcement()

    assert load_silver(conn)["loaded"] == ["BOE-B-1"]
    assert claude.call_count == 2


######################################
# Outages: the run stops at the first error
######################################

OUTAGES = [
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.OverloadedError,
    anthropic.InternalServerError,
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.NotFoundError,
]


@pytest.mark.parametrize("error_class", OUTAGES, ids=lambda error_class: error_class.__name__)
def test_s3_claude_outage_stops_the_run(conn, add_bronze, claude, ping, error_class):
    add_bronze("BOE-B-1", "BOE-B-2", "BOE-B-3")
    claude.answers["BOE-B-2"] = claude_error(error_class)

    with pytest.raises(error_class):
        load_silver(conn)

    # Stops at the 2nd: the 3rd isn't sent to Claude
    assert claude_calls(claude) == ["BOE-B-1", "BOE-B-2"]
    # The 1st stays committed, and nothing is recorded as FAILED
    assert rows(conn, "SELECT boe_ref FROM silver.auctions") == [("BOE-B-1",)]
    assert rows(conn, "SELECT boe_ref FROM silver.failed_announcements") == []
    ping.assert_not_called()


def test_s3_retry_after_claude_outage_only_pays_for_the_rest(conn, add_bronze, claude):
    add_bronze("BOE-B-1", "BOE-B-2", "BOE-B-3")
    claude.answers["BOE-B-2"] = claude_error(anthropic.OverloadedError)
    with pytest.raises(anthropic.OverloadedError):
        load_silver(conn)

    # Claude is back: Airflow retries the task
    del claude.answers["BOE-B-2"]
    claude.reset_mock()
    load_silver(conn)

    # The failed call wasn't billed, so nothing is paid twice
    assert claude_calls(claude) == ["BOE-B-2", "BOE-B-3"]


@pytest.mark.parametrize("error", [
    pytest.param(requests.ConnectionError("Goolzoom down"), id="s26_goolzoom_down"),
    pytest.param(requests.HTTPError("500 Server Error"), id="s27_goolzoom_error"),
])
def test_s26_s27_goolzoom_outage_stops_the_run(conn, add_bronze, claude, goolzoom, error):
    add_bronze("BOE-B-1", "BOE-B-2", "BOE-B-3")
    claude.answers["BOE-B-2"] = announcement(lot(references=[REF_B]))
    goolzoom.answers[REF_B] = error

    with pytest.raises(type(error)):
        load_silver(conn)

    assert claude_calls(claude) == ["BOE-B-1", "BOE-B-2"]
    assert rows(conn, "SELECT boe_ref FROM silver.auctions") == [("BOE-B-1",)]
    assert rows(conn, "SELECT boe_ref FROM silver.failed_announcements") == []

    # Goolzoom is back: the retry pays Claude again for the 2nd, whose answer was rolled back
    del goolzoom.answers[REF_B]
    claude.reset_mock()
    load_silver(conn)
    assert claude_calls(claude) == ["BOE-B-2", "BOE-B-3"]


def test_s33_failed_announcement_then_outage_alerts_once(conn, add_bronze, claude, ping):
    add_bronze("BOE-B-1", "BOE-B-2", "BOE-B-3")
    claude.answers["BOE-B-1"] = announcement(offer_deadline=None)
    claude.answers["BOE-B-2"] = claude_error(anthropic.OverloadedError)

    with pytest.raises(anthropic.OverloadedError):
        load_silver(conn)

    ping.assert_called_once()
    # The FAILED one is recorded, so the retry won't see it pending and won't pay for it again
    assert rows(conn, "SELECT boe_ref FROM silver.failed_announcements") == [("BOE-B-1",)]

    del claude.answers["BOE-B-2"]
    claude.reset_mock()
    assert load_silver(conn) == {"loaded": ["BOE-B-2", "BOE-B-3"], "failed": []}
    assert claude_calls(claude) == ["BOE-B-2", "BOE-B-3"]


def test_s14_run_killed_midway_leaves_nothing_half_stored(conn, postgres, add_bronze, claude, goolzoom):
    """S14: the process dies while it's working on the 2nd announcement, with no chance to catch an error.

    KeyboardInterrupt isn't an Exception, so no `except` in load_silver catches it, as with a real kill.
    """
    add_bronze("BOE-B-1", "BOE-B-2", "BOE-B-3")
    # The 2nd has a new reference, REF_C, inserted before the kill on REF_B
    claude.answers["BOE-B-2"] = announcement(lot(1, references=[REF_C]), lot(2, references=[REF_B]))
    goolzoom.answers[REF_B] = KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        load_silver(conn)
    # The connection is lost without a commit, so Postgres undoes what wasn't committed
    conn.close()

    other = psycopg2.connect(**postgres)
    assert rows(other, "SELECT boe_ref FROM silver.auctions") == [("BOE-B-1",)]
    assert rows(other, "SELECT catastral_reference FROM silver.catastral_references") == [(REF_A,)]
    # The 2nd and 3rd are still pending for the next run
    pending = rows(other, read_sql("select_pending_silver_announcements.sql"))
    assert [boe_ref for boe_ref, *_ in pending] == ["BOE-B-2", "BOE-B-3"]
    other.close()


######################################
# Goolzoom calls
######################################

def test_s29_stored_reference_makes_no_goolzoom_call(conn, add_bronze, goolzoom):
    """S29: a re-auction of the same plot uses the stored reference."""
    add_bronze("BOE-B-1", "BOE-B-2")   # Both have REF_A, the default

    load_silver(conn)

    assert goolzoom.call_count == 1


def test_s31_rejected_reference_is_looked_up_every_time(conn, add_bronze, claude, goolzoom):
    """S31: rejected references aren't recorded, so Goolzoom is called again. Costs Goolzoom calls, not Claude."""
    add_bronze("BOE-B-1", "BOE-B-2")
    claude.answers["BOE-B-1"] = announcement(lot(1, references=[REF_B]), lot(2))
    claude.answers["BOE-B-2"] = announcement(lot(1, references=[REF_B]), lot(2))
    goolzoom.answers[REF_B] = None

    load_silver(conn)

    assert [call.args[0] for call in goolzoom.call_args_list].count(REF_B) == 2