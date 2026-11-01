"""
Discover Hacienda auctions from the BOE Open Data API daily summary

BOE API: https://www.boe.es/datosabiertos/api/api.php
"""

from datetime import date, datetime

import requests
from lxml import etree

from .config import AUCTION_TITLE_RE, BOE_SUMARIO_ENDPOINT


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


def _parse_auction_urls(sumario_xml: bytes) -> list[str]:
    """Return the `url_xml` of every item whose title announces a Delegación de Economía y Hacienda auction."""
    root = etree.fromstring(sumario_xml)
    urls = []
    # Iterate over all item elements
    for item in root.iter("item"):
        # Finds first child of "item" names "titulo" and returns the text inside of it
        titulo = item.findtext("titulo", default="")
        # regex.search: Returns a match object if there is a match anywhere on the string
        if not AUCTION_TITLE_RE.search(titulo):
            continue
        url_xml = item.findtext("url_xml")
        if url_xml:
            urls.append(url_xml.strip())
    return urls


def get_auction_urls(fecha: date) -> list[str]:
    """Return the list of `url_xml` for the auctions published that day"""
    sumario_xml = _fetch_boe_sumario(fecha)
    if sumario_xml is None:
        return []
    urls = _parse_auction_urls(sumario_xml)
    return urls

def _fetch_announcement(xml_url: str, timeout: float = 30) -> bytes:
    """Return the raw XML summary for `xml_url`"""
    response = requests.get(xml_url,timeout=timeout)
    response.raise_for_status()
    return response.content

def _get_announcement_boe_ref(root: etree._Element) -> str:
    """Returns the BOE reference (id) for that auction announcement"""
    boe_ref = root.findtext("metadatos/identificador")
    return boe_ref

def _get_announcement_text(root: etree._Element) -> str:
    """Returns the text for auction, including the rows of any table"""
    texto = root.find("texto")
    if texto is None:
        return ""
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
    return "\n".join(b for b in blocks if b)


def _get_announcement_publication_date(root: etree._Element) -> date:
    """Returns the date in which the auction was publicated in the BOE summary"""
    publication_date_str = root.findtext("metadatos/fecha_publicacion")
    publication_date = datetime.strptime(publication_date_str, "%Y%m%d").date()
    return publication_date


def get_auction_info(xml_url: str) -> dict:
    """Return a dictionary with the relevant information for the auction according the bronze layer"""
    auction_xml = _fetch_announcement(xml_url)
    root = etree.fromstring(auction_xml)
    boe_ref = _get_announcement_boe_ref(root)
    announcement_text = _get_announcement_text(root)
    publication_date = _get_announcement_publication_date(root)
    return {
        "boe_ref": boe_ref,
        "announcement_text": announcement_text,
        "publication_date": publication_date,
        "source_url": xml_url
    }


