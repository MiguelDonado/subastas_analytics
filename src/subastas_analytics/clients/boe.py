"""
Discover Hacienda auctions from the BOE Open Data API daily summary

BOE API: https://www.boe.es/datosabiertos/api/api.php
"""

import logging
from datetime import date, datetime

import requests
from lxml import etree

from ..config import (
    AUCTION_TITLE_RE,
    BOE_SUMARIO_ENDPOINT,
    NEAR_MISS_TITLE_RE,
    NON_AUCTION_TITLE_RE,
)

logger = logging.getLogger(__name__)


def _fetch_boe_sumario(fecha: date, timeout: float = 30) -> bytes | None:
    """Return the raw XML summary for `fecha`, or None if no BOE was published that day."""
    response = requests.get(

        # fecha is a datetime object | strftime converts it to text
        # %Y 4-digit year |%m 2-digit month | %d 2-digit day
        BOE_SUMARIO_ENDPOINT.format(fecha=fecha.strftime("%Y%m%d")),
        # Accept: Http header a client uses to say which format it wants back.
        headers={"Accept": "application/xml"},   
        timeout=timeout,
    )
    # If that day there was no BOE published
    if response.status_code == 404:
        return None
    # If there is an error it raises an exception and exits the function
    response.raise_for_status()
    return response.content

def _parse_auction_candidates(sumario_xml: bytes) -> list[tuple[str,str]]:
    """Return the (title,`url_xml`) of every item whose title announces a Delegación de Economía y Hacienda auction."""
    root = etree.fromstring(sumario_xml)
    candidates = []
    # Iterate over all item elements
    for item in root.iter("item"):
        # Finds first child of "item" names "titulo" and returns the text inside of it
        titulo = item.findtext("titulo", default="")
        # regex.search: Returns a match object if there is a match anywhere on the string
        if not AUCTION_TITLE_RE.search(titulo):
            # Not skipped silently: if the wording of the titles changes, they show up in the log
            if NEAR_MISS_TITLE_RE.search(titulo):
                logger.warning("NEAR MISS: title mentions Hacienda and subasta but doesn't match AUCTION_TITLE_RE: %s", titulo)
            continue
        # Skip corrections, suspensions, cancellations... of an earlier auction
        if NON_AUCTION_TITLE_RE.search(titulo):
            continue
        url_xml = item.findtext("url_xml", default="").strip()
        # Never seen (0 of 40,593 items in 2025 and 2026). Skipped instead of raising, so one bad item
        # doesn't block the whole week. If the BOE stops sending it for every item, B17 alerts
        if not url_xml:
            logger.warning("NO URL_XML: auction candidate skipped because it has no url_xml: %s", titulo)
            continue
        candidates.append((titulo, url_xml))
    return candidates


def fetch_auction_candidates(fecha: date) -> list[tuple[str, str]]:
    """
    Return the (title, `url_xml`) of the items whose title passes the regexes that day.

    Claude isn't called here, so a BOE failure never wastes a Claude call.
    The caller asks Claude about each title once every BOE call is done.

    Special scenarios:

    Situation                          Returns
     No BOE                              []
     No auction candidates               []
    """
    sumario_xml = _fetch_boe_sumario(fecha)
    if sumario_xml is None:
        return []
    # The regexes are free and discard most titles. Claude catches the wording they don't cover
    return _parse_auction_candidates(sumario_xml)

def _fetch_announcement(xml_url: str, timeout: float = 30) -> bytes:
    """Return the raw XML summary for `xml_url`"""
    response = requests.get(xml_url,timeout=timeout)
    response.raise_for_status()
    return response.content

def _get_announcement_boe_ref(root: etree._Element) -> str:
    """Returns the BOE reference (id) for that auction announcement"""
    boe_ref = root.findtext("metadatos/identificador")
    return boe_ref

def _get_announcement_text(root: etree._Element, boe_ref: str) -> str:
    """
    Returns the text for auction, including the rows of any table

    Raises ValueError if there is no text: silver can't extract anything from it, and failing
    alerts instead of storing an empty announcement. The retries get the same XML, so the task
    fails and healthchecks.io alerts (B11 in docs/6.failure_modes.md).
    """
    texto = root.find("texto")
    if texto is None:
        raise ValueError(f"Announcement {boe_ref} has no <texto>")
    blocks = []
    # Iterate over direct children of "texto" in document order (p, table, ...)
    for element in texto:
        # Skip XML comments
        if not isinstance(element.tag, str):
            continue
        if element.tag == "table":
            # One line per row, cells separated by " | "
            for row in element.iter("tr"):
                cells = ["".join(cell.itertext()).strip() for cell in row if cell.tag in ("td", "th")]
                blocks.append(" | ".join(cells))
        else:
            blocks.append("".join(element.itertext()).strip())
    text = "\n".join(b for b in blocks if b)
    if not text:
        raise ValueError(f"Announcement {boe_ref} has an empty <texto>")
    return text


def _get_announcement_publication_date(root: etree._Element) -> date:
    """Returns the date in which the auction was publicated in the BOE summary"""
    publication_date_str = root.findtext("metadatos/fecha_publicacion")
    publication_date = datetime.strptime(publication_date_str, "%Y%m%d").date()
    return publication_date


def fetch_auction(xml_url: str) -> dict:
    """Return a dictionary with the relevant information for the auction according the bronze layer"""
    auction_xml = _fetch_announcement(xml_url)
    root = etree.fromstring(auction_xml)
    boe_ref = _get_announcement_boe_ref(root)
    announcement_text = _get_announcement_text(root, boe_ref)
    publication_date = _get_announcement_publication_date(root)
    return {
        "boe_ref": boe_ref,
        "announcement_text": announcement_text,
        "publication_date": publication_date.isoformat(),   # Converts the date from a Python object into plain text
        "source_url": xml_url
    }


