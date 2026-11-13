"""Classify auctions and extract relevant information from the announcement text of a BOE Auction using Claude."""

import hashlib
import json
import logging
from datetime import date

import anthropic
from anthropic.types.beta import BetaFallbackMessageIterationUsage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"

TITLE_SYSTEM_PROMPT = """\
You classify the titles of Spanish BOE announcements from the Delegaciones de Economía y Hacienda.

is_auction is true if the title calls or announces an auction (subasta), in any round, \
including a new auction of goods that were offered before.

is_auction is false if the title only changes an auction that was already announced: \
it corrects, rectifies, suspends, withdraws or excludes lots from, cancels, postpones or modifies it, \
or it reports its result."""


class TitleCheck(BaseModel):
    is_auction: bool = Field(description="True if the title announces an auction, false if it only changes an earlier one")


def is_auction_title(title: str) -> bool:
    """Ask Claude whether a title announces an auction, rather than changing an earlier one."""
    client = anthropic.Anthropic()

    response = client.beta.messages.parse(
        model=MODEL,
        # Thinking counts towards this limit, so it leaves room for more than the short answer
        max_tokens=2048,
        system=TITLE_SYSTEM_PROMPT,
        # <titulo>...</titulo>: To distinguish the part to process from the rest of the prompt
        messages=[{"role": "user", "content": f"<titulo>\n{title}\n</titulo>"}],
        output_format=TitleCheck,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )

    # Raise instead of guessing: an Airflow retry is better than keeping or losing an announcement by mistake
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined the request for title: {title}. {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError(f"Response was cut off by max_tokens for title: {title}")

    is_auction = response.parsed_output.is_auction
    # The regexes are already restrictive, so a title that passes them is expected to be an auction.
    # A rejection is a surprise, so it's logged to be checked
    if not is_auction:
        logger.warning("NOT AN AUCTION: title passed the regexes but Claude rejected it: %s", title)
    return is_auction

SYSTEM_PROMPT = """\
You extract structured data from Spanish BOE announcements of public auctions \
held by the Delegaciones de Economía y Hacienda.

Each announcement lists one or more lots (lotes). A lot can contain several catastral references. \
Each lot has a starting price (tipo de licitación) per auction round. \
The BOE publication date is given in <fecha_publicacion>.

Rules:
- offer_deadline: the earliest date by which an offer must be submitted.
  - If offers can be submitted in sealed envelopes (sobres), return the last day to submit them, even if there is also bidding at the public act. \
If the announcement doesn't give that day, return the date the auction is held (fecha de celebración).
  - If there are no envelopes and offers are only made at the public act, return the date the auction is held (fecha de celebración).
  - If the announcement moves the date, return the new one. If it gives neither date, return null.
  - If the deadline is given as a period instead of a date (e.g. "30 días naturales desde el día siguiente a la publicación"), calculate it from the publication date. Count "días hábiles" as Monday to Friday and ignore holidays.
- lot_number: an integer. "Lote nº 3" is 3 and "Uno)" is 1. A single lot with no number ("Lote único") is 1.
- starting_price: the price of the earliest round offered in this announcement, normally the 1ª subasta. A notice calling only a 3ª subasta gives the 3ª subasta price. Prices are written in Spanish format ("5.271,11 €"); return them as numbers in euros (5271.11). If the text gives none for a lot, return null.
- catastral_references: every catastral reference of the properties being sold in the lot, as separate items, copied exactly as written. Ignore references of adjoining parcels mentioned in the boundaries (linderos).
- If a field is missing from the text, leave it empty or null; never invent values.
"""


class Lot(BaseModel):
    lot_number: int = Field(description='Lot number as an integer')
    starting_price: float | None = Field(description="Tipo de licitación of the earliest round offered, in euros")
    catastral_references: list[str] = Field(description="Catastral references of the properties in this lot")


class Announcement(BaseModel):
    offer_deadline: date | None = Field(description="Earliest date by which an offer must be submitted")
    lots: list[Lot]


EXTRACTION_EFFORT = "low"

# Short fingerprint of the extraction instructions. It changes by itself whenever
# SYSTEM_PROMPT, the Announcement schema or EXTRACTION_EFFORT changes.
PROMPT_HASH = hashlib.sha256(
    (SYSTEM_PROMPT + json.dumps(Announcement.model_json_schema(), sort_keys=True) + EXTRACTION_EFFORT).encode()
).hexdigest()[:12]


def _serving_model(response) -> str:
    """Return the model that produced the response, which is a different one after a fallback.

    The API can list the attempts behind a response in `response.usage.iterations`:
    - A normal request may have no list at all (None), which is why the loop uses `or []`.
    - An attempt that was refused is added as a normal entry, even if it used a fallback model.
    - The fallback attempt that produced the final answer is added as an object of type
      `BetaFallbackMessageIterationUsage`, and its `model` is the model that answered.

    If no entry has that type, no fallback produced the answer, so the model is `response.model`.
    """
    for iteration in response.usage.iterations or []:
        if isinstance(iteration, BetaFallbackMessageIterationUsage):
            return iteration.model
    return response.model


def extract_info_announcement(text: str, publication_date: date) -> tuple[Announcement, str]:
    """Ask Claude to extract the lots of an announcement, validated against `Announcement`.

    publication_date is sent too, because some deadlines are written as a number of days from it.
    Returns the extracted data and the model that produced it.
    """
    client = anthropic.Anthropic()

    # Streaming: long announcements can take minutes, and the SDK requires it for high max_tokens.
    # get_final_message() waits for the end and returns the same object as a normal request.
    with client.beta.messages.stream(
        model=MODEL,
        # It counts only output, not input.
        # Maximum number of tokens Claude may generate in its response
        # (it includes reasoning tokens and the structured output response)
        max_tokens=64000,
        # General instructions for the model
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": (
            f"<fecha_publicacion>{publication_date.isoformat()}</fecha_publicacion>\n"
            f"<anuncio>\n{text}\n</anuncio>"
        )}],
        # Converts the Pydantic class into a JSON Schema and sends it with the request
        # The API uses structured outputs, the model's output is constrained to that schema
        output_format=Announcement,
        # This task does not require a lot of thinking
        output_config={"effort": EXTRACTION_EFFORT},
        # Recent models like Opus 5.5 run safety classifiers on each request, with categories such as cyber,
        # bio and reasoning_extraction
        # Beta: Is how Anthropic releases features that work but aren't final yet.
        # You have to opt in to each one explicitly.
        # The data marks a version of the feature
        betas=["server-side-fallback-2026-07-01"],
        # What to do on a refusal. "default" lets Anthropic pick the fallback model based on refusal category
        fallbacks="default",
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined the request: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Response was cut off by max_tokens; the announcement may have too many lots")
    return response.parsed_output, _serving_model(response)