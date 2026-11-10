"""BOE client: the daily summary (B1–B5) and the announcement XML (B10–B13)."""

import logging
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from subastas_analytics.clients import boe

DATA = Path(__file__).parents[1] / "data"
ANNOUNCEMENT_URL = "https://www.boe.es/diario_boe/xml.php?id=BOE-B-2026-36159"

AUCTION_TITLE = "Resolución de la Delegación de Economía y Hacienda de Segovia por la que se anuncia subasta pública"


def summary_item(identificador="BOE-B-2026-1", titulo=AUCTION_TITLE,
                 url_xml="https://www.boe.es/diario_boe/xml.php?id=BOE-B-2026-1") -> str:
    """One <item> of the summary. None leaves the tag out."""
    tags = [
        f"<identificador>{identificador}</identificador>" if identificador is not None else "",
        f"<titulo>{titulo}</titulo>",
        f"<url_xml>{url_xml}</url_xml>" if url_xml is not None else "",
    ]
    return "<item>" + "".join(tags) + "</item>"


def summary_xml(*items: str) -> bytes:
    """A summary with the same nesting as the real one."""
    return (
        '<?xml version="1.0" encoding="utf-8"?><response><data><sumario>'
        '<diario numero="276"><seccion codigo="5B"><departamento><epigrafe>'
        + "".join(items)
        + "</epigrafe></departamento></seccion></diario></sumario></data></response>"
    ).encode()


def announcement_xml(identificador="BOE-B-2026-1", fecha="20261105",
                     texto='<texto><p class="parrafo">Subasta el 17 de diciembre de 2026.</p></texto>') -> bytes:
    """An announcement. None leaves the tag out."""
    metadatos = (
        (f"<identificador>{identificador}</identificador>" if identificador is not None else "")
        + (f"<fecha_publicacion>{fecha}</fecha_publicacion>" if fecha is not None else "")
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><documento><metadatos>{metadatos}</metadatos>{texto or ""}</documento>'.encode()


######################################
# Summary download
######################################

def test_fetch_summary_asks_for_xml_of_that_day(monkeypatch, make_response):
    # Fake requests.get: it always answers 200 with a tiny body, and remembers how it was called.
    # A real call goes requests.get() -> Session.request() -> internet. The safety net in conftest.py
    # blocks Session.request(). This mock replaces requests.get(), the step before, so it answers
    # without ever calling Session.request(), and the block is never reached
    get = Mock(return_value=make_response(200, b"<response/>"))
    monkeypatch.setattr(boe.requests, "get", get)

    # Returns the body of the answer
    assert boe._fetch_boe_sumario(date(2026, 11, 5)) == b"<response/>"

    # call_args: the arguments of the last call. args are the positional ones, kwargs the name=value ones.
    # _fetch_boe_sumario calls it like this:
    #   requests.get(
    #       "https://www.boe.es/datosabiertos/api/boe/sumario/20261105",   -> args[0]
    #       headers={"Accept": "application/xml"},                         -> kwargs["headers"]
    #       timeout=30,                                                    -> kwargs["timeout"]
    #   )
    url = get.call_args.args[0]
    # The date is written as YYYYMMDD in the URL
    assert url.endswith("/sumario/20261105")
    # Asks for XML. Without this header the BOE answers in JSON
    assert get.call_args.kwargs["headers"] == {"Accept": "application/xml"}


def test_b1_no_boe_that_day(monkeypatch, make_response):
    monkeypatch.setattr(boe.requests, "get", Mock(return_value=make_response(404)))

    assert boe._fetch_boe_sumario(date(2026, 11, 8)) is None
    assert boe.fetch_auction_candidates(date(2026, 11, 8)) == []


@pytest.mark.parametrize("status_code", [400, 500, 503])
def test_b2_boe_error_fails(monkeypatch, make_response, status_code):
    monkeypatch.setattr(boe.requests, "get", Mock(return_value=make_response(status_code)))

    with pytest.raises(requests.HTTPError):
        boe.fetch_auction_candidates(date(2026, 11, 5))


######################################
# Summary parsing
######################################

def test_auction_candidate_is_returned():
    xml = summary_xml(summary_item("BOE-B-2026-36156", AUCTION_TITLE, " https://www.boe.es/x.php?id=1 "))

    assert boe._parse_auction_candidates(xml) == [
        ("BOE-B-2026-36156", AUCTION_TITLE, "https://www.boe.es/x.php?id=1"),
    ]


def test_only_auctions_are_kept_from_a_mixed_summary(caplog):
    xml = summary_xml(
        summary_item("BOE-A-1", "Resolución por la que se nombra Notario Archivero de Protocolos"),
        summary_item("BOE-B-1", AUCTION_TITLE),
        summary_item("BOE-B-2", "Corrección de errores de la Resolución de la Delegación de Economía y Hacienda de Soria, subasta"),
        summary_item("BOE-B-3", AUCTION_TITLE),
    )

    assert [boe_ref for boe_ref, _, _ in boe._parse_auction_candidates(xml)] == ["BOE-B-1", "BOE-B-3"]
    # B4: a correction is skipped with no log
    assert caplog.records == []


def test_b3_near_miss_is_logged(caplog):
    title = "Resolución de la Delegación Provincial de Hacienda de Teruel por la que se anuncia subasta"

    with caplog.at_level(logging.WARNING):
        assert boe._parse_auction_candidates(summary_xml(summary_item(titulo=title))) == []

    assert "NEAR MISS" in caplog.text
    assert title in caplog.text


@pytest.mark.parametrize("item, log", [
    (summary_item(url_xml=None), "NO URL_XML"),
    (summary_item(url_xml="  "), "NO URL_XML"),
    (summary_item(identificador=None), "NO IDENTIFICADOR"),
    (summary_item(identificador=""), "NO IDENTIFICADOR"),
])
def test_b5_candidate_without_url_or_id_is_skipped_and_logged(caplog, item, log):
    # The summary has two items:
    # - item: the bad one, missing its url_xml or identificador (from parametrize)
    # - summary_item("BOE-B-2026-2"): the good one, a complete auction
    with caplog.at_level(logging.WARNING):
        candidates = boe._parse_auction_candidates(summary_xml(item, summary_item("BOE-B-2026-2")))

    # Only the bad item is skipped, the rest of the day still loads
    assert [boe_ref for boe_ref, _, _ in candidates] == ["BOE-B-2026-2"]
    assert log in caplog.text


def test_summary_with_no_items():
    assert boe._parse_auction_candidates(summary_xml()) == []


######################################
# Announcement
######################################

def test_parse_real_announcement():
    xml = (DATA / "BOE-B-2026-36159.xml").read_bytes()

    auction = boe.parse_auction(xml, ANNOUNCEMENT_URL)

    assert auction["boe_ref"] == "BOE-B-2026-36159"
    assert auction["publication_date"] == "2026-11-05"
    assert auction["source_url"] == ANNOUNCEMENT_URL
    text = auction["announcement_text"]
    assert text.startswith("Para el día 17 de diciembre de 2026")
    assert "Referencia catastral 6913202UM5161D0008ZP." in text
    assert "1.ª subasta: 53.754,21 €" in text
    # One line per paragraph
    assert len(text.splitlines()) == 11


def test_table_rows_become_lines_and_comments_are_skipped():
    texto = (
        "<texto>"
        "<p>Lotes:</p>"
        "<!-- a comment -->"
        "<table><tr><th>Lote</th><th>Tipo</th></tr>"
        "<tr><td>1</td><td>5.271,11 €</td></tr></table>"
        "<p>  </p>"
        "</texto>"
    )

    auction = boe.parse_auction(announcement_xml(texto=texto), ANNOUNCEMENT_URL)

    # The empty paragraph is left out
    assert auction["announcement_text"] == "Lotes:\nLote | Tipo\n1 | 5.271,11 €"


@pytest.mark.parametrize("texto", [None, "<texto/>", "<texto><p> </p></texto>"])
def test_b11_announcement_without_text_fails(texto):
    with pytest.raises(ValueError, match="BOE-B-2026-1"):
        boe.parse_auction(announcement_xml(identificador="BOE-B-2026-1", texto=texto), ANNOUNCEMENT_URL)


@pytest.mark.parametrize("identificador", [None, "", "  "])
def test_b12_announcement_without_boe_ref_fails(identificador):
    with pytest.raises(ValueError, match="no metadatos/identificador") as error:
        boe.parse_auction(announcement_xml(identificador=identificador), ANNOUNCEMENT_URL)
    # The URL is in the message, since there is no boe_ref to show
    assert ANNOUNCEMENT_URL in str(error.value)


@pytest.mark.parametrize("fecha, error", [
    (None, TypeError),          # No tag: strptime gets None
    ("", ValueError),           # Empty tag
    ("05/11/2026", ValueError), # Not valid: a date, but in an unexpected format (the code expects YYYYMMDD)
])
def test_b13_announcement_without_valid_publication_date_fails(fecha, error):
    with pytest.raises(error):
        boe.parse_auction(announcement_xml(fecha=fecha), ANNOUNCEMENT_URL)


def test_b10_announcement_download_error_fails(monkeypatch, make_response):
    monkeypatch.setattr(boe.requests, "get", Mock(return_value=make_response(500)))

    with pytest.raises(requests.HTTPError):
        boe.fetch_announcement_xml(ANNOUNCEMENT_URL)