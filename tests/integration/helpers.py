"""Small functions used by the integration tests: they build the test data and read the database.

They're plain functions, imported with `from helpers import ...`. That works because pytest adds the
folder of each test file (tests/integration) to the places Python imports from.
"""

from datetime import date

import anthropic
import httpx2

from subastas_analytics.clients.goolzoom import CatastroInfo
from subastas_analytics.clients.llm import Announcement, Lot

# Catastral references, already 20 characters, so lookup_reference's normalize_reference leaves them as they are
REF_A = "1111111AA1111A0001AA"
REF_B = "2222222BB2222B0001BB"
REF_C = "3333333CC3333C0001CC"
REF_D = "4444444DD4444D0001DD"

PUBLICATION_DATE = date(2026, 11, 5)
HELD_DATE = date(2026, 12, 17)

# The text stored in bronze for each announcement. The fake Claude reads the boe_ref back from it
TEXT_PREFIX = "Text of "


def lot(number: int = 1, price: float | None = 50000.0, references: list[str] | None = None) -> Lot:
    """A lot as Claude would return it. By default: lot 1, 50,000 €, reference REF_A."""
    return Lot(lot_number=number, starting_price=price, catastral_references=references if references is not None else [REF_A])


def announcement(*lots: Lot, held_date: date | None = HELD_DATE) -> Announcement:
    """An announcement as Claude would return it. With no lots given, it has one valid lot."""
    return Announcement(held_date=held_date, lots=list(lots) if lots else [lot()])


def catastro_info(reference: str, **changes) -> CatastroInfo:
    """A complete reference as lookup_reference would return it, in Valladolid. `changes` replaces any field."""
    values = {
        "reference": reference,
        "municipality": "VALLADOLID",
        "province": "VALLADOLID",
        "use": "Residencial",
        "property_class": "Urbano",
        "surface": 75.0,
        "latitude": 41.64,
        "longitude": -4.72,
        "qualification": None,
    }
    return CatastroInfo(**{**values, **changes})


def claude_error(error_class: type[anthropic.APIError]) -> anthropic.APIError:
    """
    This helper creates realistic Anthropic SDK exceptions so that tests can simulate different API failures.

    It handles two categories differently:
    - Connection errors: No HTTP response exists because the request never received an answer.
    - HTTP errors: An HTTP response exists with the appropriate status code (400, 401, 429, 500, etc.).
    The resulting exception can then be passed to our claude fake to test how load_silver() handles failures.
    """
    # Nothing is sent is just an object
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    # A connection error has no response: the request never got an answer
    if issubclass(error_class, anthropic.APIConnectionError):
        return error_class(request=request)
    status_codes = {
        anthropic.BadRequestError: 400,
        anthropic.AuthenticationError: 401,
        anthropic.PermissionDeniedError: 403,
        anthropic.NotFoundError: 404,
        anthropic.RateLimitError: 429,
        anthropic.InternalServerError: 500,
        anthropic.OverloadedError: 529,
    }
    response = httpx2.Response(status_codes[error_class], request=request)
    return error_class(f"Fake {error_class.__name__}", response=response, body=None)


def claude_calls(claude) -> list[str]:
    """The boe_refs that were sent to the fake Claude, in order. One item per call, so one per paid call."""
    return [call.args[0].removeprefix(TEXT_PREFIX) for call in claude.call_args_list]


def rows(conn, sql: str) -> list[tuple]:
    """Run a SELECT and return its rows."""
    cursor = conn.cursor()
    cursor.execute(sql)
    return cursor.fetchall()