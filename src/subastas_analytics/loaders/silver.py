"""Load BOE announcements from bronze into silver.

Silver only stores complete data, and everything left out is logged. Search the task log for
"REJECTED" or "FAILED" to review the problems:

Problem                                 What happens
 Reference invalid, not found or         REJECTED: the reference isn't stored, the rest of
 with incomplete Catastro data           the announcement is
 Lot with no valid reference or with     REJECTED: the lot isn't stored, the rest of the
 no starting price                       announcement is
 No held date, no lots found or none     REJECTED: only its boe_ref and the reason are
 of them valid                           stored, so it isn't sent to Claude again
 Announcement can't be loaded            FAILED: nothing of it is stored, it is tried again
 (refused by Claude...)                  on the next run
 Claude or Goolzoom are down             The run stops, it is tried again on the next run
"""

import logging
from dataclasses import asdict

import anthropic
import requests

from ..clients.goolzoom import CatastroInfo, lookup_reference, normalize_reference
from ..clients.llm import Announcement, extract_info_announcement
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


def _reject_announcement(cursor, boe_ref: str, reason: str) -> None:
    """Record a rejected announcement, so it isn't sent to Claude again on the next run"""
    cursor.execute(
        read_sql("insert_silver_rejected_announcement.sql"),
        {"boe_ref": boe_ref, "reason": reason},
    )


def _store_auction(cursor, bronze_row: dict, announcement: Announcement) -> bool:
    """
    Return True if the auction was stored, or False if it was rejected for having no valid lots

    bronze_row: Info about the auction already stored in Bronze layer (using BOE API)
    Announcement: Contains the info extracted from the auction usign Claude API
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

        ##########################
        # 1. Retrive id of catastral references of each lot, before inserting the lots
        #    1. Already stored
        #    2. Not stored -> Insert it -> Retrieve its id

        # reference_ids: Holds a list with the ids of all the ref catastral in the lot.
        #                For problematic ref catastral we get None values
        ##########################
        reference_ids = [
            _get_reference_id(cursor, raw_reference, bronze_row["boe_ref"], lot.lot_number)
            for raw_reference in lot.catastral_references
        ]
        # List with the id of all valid catastral references
        valid_reference_ids = [reference_id for reference_id in reference_ids if reference_id is not None]

        ###################
        # Lote has no valid catastral references: It isn't stored
        ###################
        if not valid_reference_ids:
            logger.warning("REJECTED %s lot %s: the lot has no valid catastral reference",
                           bronze_row["boe_ref"], lot.lot_number)
            continue

        valid_lots.append((lot, valid_reference_ids))

    ###################
    # Auction has no valid lots: It isn't stored
    ###################
    if not valid_lots:
        logger.warning("REJECTED %s: the auction has no valid lot (Claude found %d lots)",
                       bronze_row["boe_ref"], len(announcement.lots))
        _reject_announcement(cursor, bronze_row["boe_ref"], "No valid lots")
        return False

    ##########################
    # 2. Insert auction in silver.auctions
    ##########################
    cursor.execute(read_sql("insert_silver_auction.sql"), {**bronze_row, "held_date": announcement.held_date})
    auction_id = cursor.fetchone()[0]

    for lot, valid_reference_ids in valid_lots:
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
        for reference_id in valid_reference_ids:
            cursor.execute(
                read_sql("insert_silver_lot_catastral_reference.sql"),
                {"lot_id": lot_id, "reference_id": reference_id},
            )

    return True


def load_silver(conn) -> dict:
    """Load every announcement in bronze that isn't in silver yet, oldest first.

    Parameters:
    - conn: Open psycopg2 connection. The caller closes it.

    Returns the boe_refs that were loaded, the ones that were rejected and the ones that failed.
    """
    ######################################
    # 1. Check pending auctions from bronze to insert on silver
    ######################################
    # Get pending auctions from bronze to introduce in silver
    with conn.cursor() as cursor:
        cursor.execute(read_sql("select_pending_silver_announcements.sql"))
        # cursor.description holds metadata for each column in the result
        # Example: columns = ["boe_ref", "announcement_text", "publication_date", "source_url"]
        columns = [column.name for column in cursor.description]
        # .fetchall(): Returns each row as a tuple (with no column names)
        # zip(): Pair each column name with its value, and dict to turn it into a dictionary
        # Example:
        # {
        #     "boe_ref": "BOE-B-2026-34259",
        #     "announcement_text": "Anuncio de...",
        #     "publication_date": date(2026, 10, 1),
        #     "source_url": "https://...",
        # }
        pending_auctions = [dict(zip(columns, row)) for row in cursor.fetchall()]
    # Ends the transaction (psycopg2 opens one automatically, even for a SELECT)
    conn.commit()

    loaded = []
    rejected = []
    failed = []

    for pending_auction in pending_auctions:
        boe_ref = pending_auction["boe_ref"]
        try:
            ######################################
            # 2. Call Claude API to extract info in a structured way
            ######################################
            announcement = extract_info_announcement(pending_auction["announcement_text"])

            ######################################
            # Reject it if it has no held date
            ######################################
            if announcement.held_date is None:
                logger.warning("REJECTED %s: the announcement has no held date", boe_ref)
                with conn.cursor() as cursor:
                    _reject_announcement(cursor, boe_ref, "No held date")
                conn.commit()
                rejected.append(boe_ref)
                continue

            with conn.cursor() as cursor:
            ######################################
            # 3. Store auction and its lots and ref catastrales 
            ######################################
                stored = _store_auction(cursor, pending_auction, announcement)
            # One transaction per announcement: it's stored whole or not at all, and a
            # rerun doesn't pay Claude again for the ones already stored
            conn.commit()
            if stored:
                loaded.append(boe_ref)
            else:
                rejected.append(boe_ref)

        # Case 1: API (Claude or GoolZoom) is down, so stop the run
        except (anthropic.APIError, requests.RequestException):
            # Discards everything since last commit (so announcement cant end up half stored). Announcements commited earlier arent affected
            conn.rollback()
            # Re-raises the same error -> stops load_silver -> Fails Airflow task -> Airflow then retries it later -> Announcements already commited are skipped on the retry
            raise
        # Case 2: Anything else, skip this announcement
        except Exception:
            conn.rollback()
            # Logs the message with the full error traceback
            logger.exception("FAILED %s: nothing stored for this announcement", boe_ref)
            failed.append(boe_ref)

    return {"loaded": loaded, "rejected": rejected, "failed": failed}
