"""The regexes that pick the auction candidates from the BOE summary titles (B3, B4)."""

import pytest

from subastas_analytics.config import (
    AUCTION_TITLE_RE,
    NEAR_MISS_TITLE_RE,
    NON_AUCTION_TITLE_RE,
)

# Real titles from the BOE of 5 November 2026
SEGOVIA = (
    "Resolución de la Delegación de Economía y Hacienda de Segovia por la que se anuncia la celebración "
    "de subasta pública al alza de 27 fincas rústicas propiedad de la Administración General del Estado "
    "en la provincia de Segovia, con admisión simultánea de ofertas en sobre cerrado."
)
VALLADOLID = (
    "Resolución de la Delegación Especial de Economía y Hacienda en Castilla y León-Valladolid por la que "
    "se anuncia subasta pública al alza, con admisión simultánea de ofertas en sobre cerrado, para la "
    "enajenación de un bien urbano situado en la ciudad de Valladolid."
)


@pytest.mark.parametrize("title", [
    SEGOVIA,
    VALLADOLID,
    # Without accents, as some titles are written
    "Resolucion de la Delegacion de Economia y Hacienda de Soria por la que se anuncia subasta",
    # Any case
    "RESOLUCIÓN DE LA DELEGACIÓN DE ECONOMÍA Y HACIENDA DE LUGO POR LA QUE SE ANUNCIA SUBASTA",
])
def test_auction_titles_match(title):
    assert AUCTION_TITLE_RE.search(title)
    assert not NON_AUCTION_TITLE_RE.search(title)


@pytest.mark.parametrize("title", [
    "Corrección de errores de la Resolución de la Delegación de Economía y Hacienda de Segovia por la que se anuncia subasta",
    "Rectificación del anuncio de la Delegación de Economía y Hacienda de Soria sobre subasta pública",
    "Resolución de la Delegación de Economía y Hacienda de Lugo por la que se suspende la subasta",
    "Resolución de la Delegación de Economía y Hacienda de Lugo por la que se retira el lote 3 de la subasta",
    "Resolución de la Delegación de Economía y Hacienda de Ávila de anulación de la subasta",
    "Resolución de la Delegación de Economía y Hacienda de León de exclusión de lotes de la subasta",
    "Resolución de la Delegación de Economía y Hacienda de León por la que se modifica la subasta",
    "Resolución de la Delegación de Economía y Hacienda de Cuenca de aplazamiento de la subasta",
])
def test_b4_corrections_are_caught_by_non_auction_regex(title):
    """B4: they pass AUCTION_TITLE_RE, and NON_AUCTION_TITLE_RE discards them."""
    assert AUCTION_TITLE_RE.search(title)
    assert NON_AUCTION_TITLE_RE.search(title)


@pytest.mark.parametrize("title", [
    "Anuncio de la Tesorería General de la Seguridad Social de subasta de bienes inmuebles",
    "Resolución de la Delegación de Economía y Hacienda de Segovia sobre arrendamiento de fincas",
])
def test_b3_other_titles_dont_match(title):
    assert not AUCTION_TITLE_RE.search(title)
    assert not NEAR_MISS_TITLE_RE.search(title)


def test_b3_near_miss_title():
    """B3: mentions Hacienda and subasta, but not with the expected wording, so it's only logged."""
    title = "Resolución de la Delegación Provincial de Hacienda de Teruel por la que se anuncia subasta"
    assert not AUCTION_TITLE_RE.search(title)
    assert NEAR_MISS_TITLE_RE.search(title)