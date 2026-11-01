"""Extract auction lots from the text of a BOE announcement using Claude."""

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """\
You extract structured data from Spanish BOE announcements of public auctions \
held by the Delegaciones de Economía y Hacienda.

Each announcement lists one or more lots (lotes). A lot can contain several \
properties (fincas), and a property can have several catastral references. \
Each lot has a starting price (tipo de licitación) per auction round.

Rules:
- Copy property descriptions and catastral references exactly as written; do not translate or summarize.
- If a property lists several catastral references, return each one as a separate item.
- Prices are written in Spanish format ("5.271,11 €"); return them as numbers in euros (5271.11).
- Only return the first-round price (1ª subasta). If the text gives none for a lot, return null.
- If a field is missing from the text, leave it empty or null; never invent values.
- If the announcement offers no lots (for example, it only modifies or cancels an earlier auction), return an empty list."""


class Finca(BaseModel):
    descripcion: str = Field(description="Property description, copied verbatim from the text")
    referencias_catastrales: list[str] = Field(description="Catastral references of this property")


class Lote(BaseModel):
    numero: str = Field(description='Lot identifier as written, e.g. "1" or "Único"')
    fincas: list[Finca]
    precio: float | None = Field(description="Tipo de licitación of the 1ª subasta, in euros")


class Anuncio(BaseModel):
    lotes: list[Lote]


def extract_lots(text: str) -> Anuncio:
    """Ask Claude to extract the lots of an announcement, validated against `Anuncio`."""
    client = anthropic.Anthropic()
    
    # messages.parse: Is used when we are using structured outputs when our schema is a Pydantic model
    response = client.beta.messages.parse(
        model=MODEL,
        # It counts only output, not input.
        # Maximum number of tokens Claude may generate in its response
        # (it includes reasoning tokens and the structured output response)
        max_tokens=16000,
        # General instructions for the model
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"<anuncio>\n{text}\n</anuncio>"}],
        # Converts the Pydantic class into a JSON Schema and sends it with the request
        # The API uses structured outputs, the model's output is constrained to that schema
        output_format=Anuncio,
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
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined the request: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Response was cut off by max_tokens; the announcement may have too many lots")
    return response.parsed_output