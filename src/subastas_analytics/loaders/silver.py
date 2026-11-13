"""Load BOE announcements from bronze into silver.

Silver only stores complete data, and everything left out is logged. Search the task log for
"REJECTED", "FAILED" or "STOPPED" to review the problems:

Problem                                 What happens
 Reference invalid, not found or         REJECTED: the reference isn't stored, the rest of
 with incomplete Catastro data           the announcement is
 Lot with no references, with any        REJECTED: the lot isn't stored, the rest of the
 invalid one, or with no starting price  announcement is
 No offer deadline, no valid lots, or    FAILED: only its boe_ref and the reason are stored in
 the announcement can't be loaded        failed_announcements, so it isn't sent to Claude
 (refused by Claude...)                  again. The DAG alerts
 Claude or Goolzoom are down             STOPPED: the run stops, it is tried again on the next run
"""

import logging
from dataclasses import asdict

import anthropic
import requests

from ..clients.goolzoom import CatastroInfo, lookup_reference, normalize_reference
from ..clients.healthchecks import ping_failure
from ..clients.llm import PROMPT_HASH, Announcement, extract_info_announcement
from .common import read_sql

logger = logging.getLogger(__name__)


def _insert_reference(cursor, info: CatastroInfo) -> int:
    '''
    Inserts catastral reference into its table and return its id
    '''
    ########################
    # 1. Upsert municipio table
    ########################
    cursor.execute(
        read_sql("upsert_silver_municipio.sql"),
        {"municipality": info.municipality, "province": info.province},
    )
    municipio_id = cursor.fetchone()[0]
    ########################
    # 2. Insert into ref catastral table
    ########################
    cursor.execute(
        read_sql("insert_silver_catastral_reference.sql"),
        {**asdict(info), "municipio_id": municipio_id},
    )
    return cursor.fetchone()[0]


def _get_reference_id(cursor, raw_reference: str, boe_ref: str, lot_number: int) -> int | None:
    """
    Return the id of a reference
    0. If already stored, simply return id.
    1. If new, insert it first, then return id
    2. If insertion was rejected, then return None (incorrect reference, some missing field)
    """
    reference = normalize_reference(raw_reference)
    cursor.execute(read_sql("select_silver_catastral_reference_id.sql"), {"reference": reference})
    row = cursor.fetchone()
    #########################################
    # 0. Catastral reference already stored
    #########################################
    if row:
        return row[0]

    #########################################
    # 1. Catastral reference not stored
    #########################################
    info = lookup_reference(raw_reference)          # CatastroInfo object or None

    #########################################
    # 1.a Do not store cuz something's wrong with the catastral reference
    #########################################
    if info is None:
        logger.warning("REJECTED %s lot %s: reference %r", boe_ref, lot_number, raw_reference)
        return None

    #########################################
    # 1.b Store reference and return id
    #########################################
    return _insert_reference(cursor, info)


def _record_failure(cursor, bronze_row: dict, reason: str, extraction_model: str | None) -> None:
    """Record a failed announcement, so it isn't sent to Claude again on the next run

    bronze_row: The announcement as it's stored in bronze. Its publication date and URL are copied,
                so a failed announcement can be found and opened without joining bronze
    """
    cursor.execute(
        read_sql("insert_silver_failed_announcement.sql"),
        {
            "boe_ref": bronze_row["boe_ref"],
            "publication_date": bronze_row["publication_date"],
            "source_url": bronze_row["source_url"],
            "reason": reason,
            "extraction_model": extraction_model,
            "extraction_prompt_hash": PROMPT_HASH,
        },
    )


def _store_auction(cursor, bronze_row: dict, announcement: Announcement, extraction_model: str) -> bool:
    """
    Store the auction, its valid lots and their catastral references. It doesn't commit.

    1. Checks each lot: it needs a starting price and at least one reference, all of them valid
       (new references are inserted here)
    2. If at least one lot is valid, it inserts the auction and those lots, and returns True.
       If none is valid, it inserts nothing and returns False

    bronze_row: Info about the auction already stored in Bronze layer (using BOE API)
    Announcement: Contains the info extracted from the auction usign Claude API
    extraction_model: Model that produced the announcement
    """
    valid_lots = []
    for lot in announcement.lots:
        ###################
        # Lote has no starting price: It isn't stored
        ###################
        if lot.starting_price is None:
            logger.warning("REJECTED %s lot %s: the lot has no starting price",
                           bronze_row["boe_ref"], lot.lot_number)
            continue

        ###################
        # Lot has no catastral references: It isn't stored, because its surface would be unknown.
        # The announcement may identify the property another way (coordinates, address...), see S36
        ###################
        if not lot.catastral_references:
            logger.warning("REJECTED %s lot %s: the lot has no catastral references "
                           "(the announcement may identify the property another way, see S36)",
                           bronze_row["boe_ref"], lot.lot_number)
            continue

        ##########################
        # 1. Retrive id of catastral references of each lot, before inserting the lots
        #    1. Already stored
        #    2. Not stored -> Insert it -> Retrieve its id

        # reference_ids: Holds a list with the ids of all the ref catastral in the lot.
        #                For problematic ref catastral we get None values
        ##########################
        # Checkpoint: if this lot is rejected, its references can be undone without losing the earlier lots
        cursor.execute("SAVEPOINT lot")
        reference_ids = [
            _get_reference_id(cursor, raw_reference, bronze_row["boe_ref"], lot.lot_number)
            for raw_reference in lot.catastral_references
        ]

        ###################
        # Lot with any invalid reference: It isn't stored, because its surface would be wrong.
        # The REJECTED line of each invalid reference, logged above, says which one
        ###################
        if None in reference_ids:
            cursor.execute("ROLLBACK TO SAVEPOINT lot")
            logger.warning("REJECTED %s lot %s: some of its catastral references are invalid",
                           bronze_row["boe_ref"], lot.lot_number)
            continue

        valid_lots.append((lot, reference_ids))

    ###################
    # Auction has no valid lots: It isn't stored
    ###################
    if not valid_lots:
        return False

    ##########################
    # 2. Insert auction in silver.auctions
    ##########################
    cursor.execute(read_sql("insert_silver_auction.sql"), {
        **bronze_row,
        "offer_deadline": announcement.offer_deadline,
        "extraction_model": extraction_model,
        "extraction_prompt_hash": PROMPT_HASH,
    })
    auction_id = cursor.fetchone()[0]

    for lot, reference_ids in valid_lots:
        ##########################
        # 3. Insert lot in silver.lots
        ##########################
        cursor.execute(read_sql("insert_silver_lot.sql"), {
            "auction_id": auction_id,
            "lot_number": lot.lot_number,
            "starting_price": lot.starting_price,
        })
        lot_id = cursor.fetchone()[0]

        ###################
        # 4. Insert rows into junction table
        ###################
        for reference_id in reference_ids:
            cursor.execute(
                read_sql("insert_silver_lot_catastral_reference.sql"),
                {"lot_id": lot_id, "reference_id": reference_id},
            )

    return True


def load_silver(conn) -> dict:
    """Load every announcement in bronze that isn't in silver yet, oldest first.

    Parameters:
    - conn: Open psycopg2 connection. The caller closes it.

    Returns the boe_refs that were loaded and the ones that failed. The failed ones are recorded in
    silver.failed_announcements, so they aren't sent to Claude again.
    """
    # One cursor for the whole run.
    # - cursor.execute(): runs the SQL against the DB right away, inside an open transaction.
    #   Only this connection sees the changes yet (that's why RETURNING + fetchone() works)
    # - conn.commit(): saves every change since the last commit into the DB, visible to everyone
    # - conn.rollback(): reverts every change made by execute() since the last commit
    with conn.cursor() as cursor:
        ######################################
        # 1. Check pending auctions from bronze to insert on silver
        ######################################
        # Get pending auctions from bronze to introduce in silver
        cursor.execute(read_sql("select_pending_silver_announcements.sql"))
        # cursor.description holds metadata for each column in the result
        # Example: columns = ["boe_ref", "announcement_text", "publication_date", "source_url"]
        columns = [column.name for column in cursor.description]
        # .fetchall(): Returns each row as a tuple (with no column names)
        # zip(): Pair each column name with its value
        pending_auctions = [dict(zip(columns, row)) for row in cursor.fetchall()]
        # Ends the transaction (psycopg2 opens one automatically, even for a SELECT)
        conn.commit()
        logger.info("%d pending announcements in bronze", len(pending_auctions))

        loaded = []
        failed = []

        for pending_auction in pending_auctions:
            boe_ref = pending_auction["boe_ref"]
            # Reset on every announcement: if it fails before Claude answers, the failure is recorded with
            # no model, instead of the one left over from the previous announcement
            extraction_model = None
            try:
                ######################################
                # 2. Call Claude API to extract info in a structured way
                ######################################
                announcement, extraction_model = extract_info_announcement(
                    pending_auction["announcement_text"], pending_auction["publication_date"]
                )

                ######################################
                # Fail it if it has no offer deadline
                ######################################
                if announcement.offer_deadline is None:
                    logger.error("FAILED %s: the announcement has no offer deadline", boe_ref)
                    _record_failure(cursor, pending_auction, "No offer deadline", extraction_model)
                    conn.commit()
                    failed.append(boe_ref)
                    continue

                ######################################
                # Fail it if the offer deadline is before the publication date
                ######################################
                if announcement.offer_deadline < pending_auction["publication_date"]:
                    logger.error("FAILED %s: offer deadline %s is before publication date %s",
                                boe_ref, announcement.offer_deadline, pending_auction["publication_date"])
                    _record_failure(cursor, pending_auction, "Offer deadline before publication date", extraction_model)
                    conn.commit()
                    failed.append(boe_ref)
                    continue

                ######################################
                # 3. Store auction and its lots and ref catastrales
                ######################################
                stored = _store_auction(cursor, pending_auction, announcement, extraction_model)

                ######################################
                # Fail it if it has no valid lots
                ######################################
                if not stored:
                    logger.error("FAILED %s: no valid lots (Claude found %d)",
                                 boe_ref, len(announcement.lots))
                    _record_failure(cursor, pending_auction, "No valid lots", extraction_model)
                    conn.commit()
                    failed.append(boe_ref)
                    continue

                ######################################
                # Accept it: the auction and its valid lots are stored
                ######################################
                # One transaction per announcement: it's stored whole or not at all, and a
                # rerun doesn't pay Claude again for the ones already stored
                conn.commit()
                logger.info("LOADED %s", boe_ref)
                loaded.append(boe_ref)

            # Case 1 (STOPPED): an outside service failed, not the announcement. Every announcement would fail the
            # same way, so the rest aren't tried and nothing is recorded:
            # - Claude down, timing out (APIConnectionError), rate limited (429), overloaded (529) or a 5xx
            # - Claude configured wrong: bad key (401), no permission (403), retired model (404)
            # - Goolzoom down (requests.RequestException)
            # Claude's other errors (400 bad request, 413 too large, 422...) are the announcement's fault, so they go to Case 2.
            # Except that out of credits is also a 400, so then every pending announcement is FAILED (see S4 in docs/6.failure_modes.md)
            except (
                anthropic.APIConnectionError,
                anthropic.RateLimitError,
                anthropic.OverloadedError,
                anthropic.InternalServerError,
                anthropic.AuthenticationError,
                anthropic.PermissionDeniedError,
                anthropic.NotFoundError,
                requests.RequestException,
            ):
                # Discards everything since last commit (so announcement cant end up half stored). Announcements commited earlier arent affected
                conn.rollback()
                logger.error("STOPPED at %s: the API call failed, the run stops so Airflow retries it", boe_ref)
                # The failed list is lost when this attempt ends, and the retry won't see these announcements as pending,
                # so this is the only chance to alert about them (S33 in docs/6.failure_modes.md)
                if failed:
                    logger.error("Announcements that failed before the run stopped: %s", failed)
                    ping_failure()
                # Re-raises the same error -> stops load_silver -> Fails Airflow task -> Airflow then retries it later -> Announcements already commited are skipped on the retry
                raise
            # Case 2 (FAILED): the announcement itself caused it (Claude rejected the request, refused it, its answer
            # was cut off, a constraint failed...). Skip it and carry on with the next one, since the others aren't
            # affected. It's recorded, so it isn't sent to Claude again: a retry would pay again for the same result
            except Exception as error:
                # Discards the half-stored announcement, then records the failure in a new transaction
                conn.rollback()
                # Logs the message with the full error traceback
                logger.exception("FAILED %s: nothing stored for this announcement", boe_ref)
                _record_failure(cursor, pending_auction, f"{type(error).__name__}: {error}", extraction_model)
                conn.commit()
                failed.append(boe_ref)

    return {"loaded": loaded, "failed": failed}
