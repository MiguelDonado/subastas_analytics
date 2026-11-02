"""Extract relevant information from the text of a BOE Auction announcement using Claude."""

from datetime import datetime

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """\
You extract structured data from Spanish BOE announcements of public auctions \
held by the Delegaciones de Economía y Hacienda.

Each announcement lists one or more lots (lotes). A lot can contain several \
properties (fincas), and each property can have several catastral references. \
Each lot has a starting price (tipo de licitación) per auction round.

Rules:
- held_at: the local date and time of the public act or the opening of the offers, not the deadline for submitting them. If the announcement moves the auction to a new date, return the new date. If it gives no date, return null.
- lot_number: an integer. "Lote nº 3" is 3 and "Uno)" is 1. A single lot with no number ("Lote único") is 1.
- starting_price: the price of the earliest round offered in this announcement, normally the 1ª subasta. A notice calling only a 3ª subasta gives the 3ª subasta price. Prices are written in Spanish format ("5.271,11 €"); return them as numbers in euros (5271.11). If the text gives none for a lot, return null.
- catastral_references: every catastral reference of the properties being sold in the lot, as separate items, copied exactly as written. Ignore references of adjoining parcels mentioned in the boundaries (linderos).
- If a field is missing from the text, leave it empty or null; never invent values.
- If the announcement offers no lots (for example, it only modifies or cancels an earlier auction), return an empty list of lots, even if it describes the affected lot."""


class Lot(BaseModel):
    lot_number: int = Field(description='Lot number as an integer')
    starting_price: float | None = Field(description="Tipo de licitación of the earliest round offered, in euros")
    catastral_references: list[str] = Field(description="Catastral references of the properties in this lot")


class Announcement(BaseModel):
    held_at: datetime | None = Field(description="Local date and time the auction is held")
    lots: list[Lot]


def extract_info_announcement(text: str) -> Announcement:
    """Ask Claude to extract the lots of an announcement, validated against `Announcement`."""
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
        messages=[{"role": "user", "content": f"<anuncio>\n{text}\n</anuncio>"}],
        # Converts the Pydantic class into a JSON Schema and sends it with the request
        # The API uses structured outputs, the model's output is constrained to that schema
        output_format=Announcement,
        # This task does not require a lot of thinking
        output_config={"effort": "low"},
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
    return response.parsed_output