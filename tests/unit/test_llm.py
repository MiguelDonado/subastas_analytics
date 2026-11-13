"""Claude client: one call per input, and an error instead of a guess (B8, S5, S6, S12).

Claude is never called: the `claude` fixture replaces anthropic.Anthropic with a MagicMock,
and each test sets what the fake response contains.

Note:
I have not reviewed this test file.
"""

import logging
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from anthropic.types.beta import BetaFallbackMessageIterationUsage

from subastas_analytics.clients import llm
from subastas_analytics.clients.llm import Announcement, Lot, TitleCheck

TITLE = "Resolución de la Delegación de Economía y Hacienda de Segovia por la que se anuncia subasta"
ANNOUNCEMENT = Announcement(
    offer_deadline=date(2026, 12, 17),
    lots=[Lot(lot_number=1, starting_price=53754.21, catastral_references=["6913202UM5161D0008ZP"])],
)
PUBLICATION_DATE = date(2026, 11, 5)


def fake_response(parsed_output=None, stop_reason="end_turn", model=llm.MODEL, iterations=None):
    """Only the fields llm.py reads from a real response."""
    return SimpleNamespace(
        parsed_output=parsed_output,
        stop_reason=stop_reason,
        stop_details=None,
        model=model,
        usage=SimpleNamespace(iterations=iterations),
    )


def fallback_usage(model: str) -> BetaFallbackMessageIterationUsage:
    return BetaFallbackMessageIterationUsage(
        type="fallback_message", model=model,
        input_tokens=10, output_tokens=10, cache_creation_input_tokens=0, cache_read_input_tokens=0,
    )


@pytest.fixture
def claude(monkeypatch):
    """A fake Claude client. Replaces the safety net's block for this test only.

    Both replace the same thing, anthropic.Anthropic, so the order decides:
    1. The safety net (autouse) runs first: anthropic.Anthropic = _blocked
    2. This fixture runs after it: anthropic.Anthropic = the fake client. The last one set wins
    3. When the test ends, monkeypatch undoes both in reverse order: back to _blocked, then to the real class
    """
    client = MagicMock()
    monkeypatch.setattr(llm.anthropic, "Anthropic", MagicMock(return_value=client))
    return client


def set_extraction_response(claude, response):
    # extract_info_announcement uses `with client.beta.messages.stream(...) as stream:`,
    # so the response comes from the object that __enter__ returns
    stream = claude.beta.messages.stream.return_value.__enter__.return_value
    stream.get_final_message.return_value = response


######################################
# Title classification (bronze)
######################################

def test_title_is_an_auction_with_one_call(claude):
    claude.beta.messages.parse.return_value = fake_response(TitleCheck(is_auction=True))

    assert llm.is_auction_title(TITLE) is True

    claude.beta.messages.parse.assert_called_once()
    kwargs = claude.beta.messages.parse.call_args.kwargs
    assert kwargs["model"] == llm.MODEL
    assert kwargs["max_tokens"] == 2048
    assert TITLE in kwargs["messages"][0]["content"]


def test_b6_title_rejected_by_claude_is_logged(claude, caplog):
    claude.beta.messages.parse.return_value = fake_response(TitleCheck(is_auction=False))

    with caplog.at_level(logging.WARNING):
        assert llm.is_auction_title(TITLE) is False

    assert "NOT AN AUCTION" in caplog.text


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_b8_title_refused_or_cut_off_raises(claude, stop_reason):
    claude.beta.messages.parse.return_value = fake_response(stop_reason=stop_reason)

    with pytest.raises(RuntimeError, match="title") as error:
        llm.is_auction_title(TITLE)
    assert TITLE in str(error.value)
    # No second attempt inside the function: Airflow's retries are the only ones
    claude.beta.messages.parse.assert_called_once()


######################################
# Announcement extraction (silver)
######################################

def test_extraction_returns_the_announcement_and_model_with_one_call(claude):
    set_extraction_response(claude, fake_response(ANNOUNCEMENT))

    assert llm.extract_info_announcement("Texto del anuncio", PUBLICATION_DATE) == (ANNOUNCEMENT, llm.MODEL)

    claude.beta.messages.stream.assert_called_once()
    kwargs = claude.beta.messages.stream.call_args.kwargs
    assert kwargs["model"] == llm.MODEL
    assert kwargs["output_format"] is Announcement
    assert kwargs["output_config"] == {"effort": llm.EXTRACTION_EFFORT}
    assert kwargs["messages"][0]["content"] == (
        "<fecha_publicacion>2026-11-05</fecha_publicacion>\n<anuncio>\nTexto del anuncio\n</anuncio>"
    )


def test_s12_extraction_after_a_fallback_returns_the_fallback_model(claude):
    set_extraction_response(claude, fake_response(ANNOUNCEMENT, iterations=[fallback_usage("claude-sonnet-5-5")]))

    _, model = llm.extract_info_announcement("Texto del anuncio", PUBLICATION_DATE)

    assert model == "claude-sonnet-5-5"


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_s5_s6_extraction_refused_or_cut_off_raises(claude, stop_reason):
    """S5, S6: a RuntimeError, so load_silver records the announcement as FAILED."""
    set_extraction_response(claude, fake_response(stop_reason=stop_reason))

    with pytest.raises(RuntimeError):
        llm.extract_info_announcement("Texto del anuncio", PUBLICATION_DATE)
    claude.beta.messages.stream.assert_called_once()


######################################
# Model that answered
######################################

@pytest.mark.parametrize("iterations", [
    None,
    [],
    # A refused attempt is a normal entry, not a fallback
    [SimpleNamespace(model="claude-opus-5-5")],
])
def test_serving_model_without_fallback(iterations):
    assert llm._serving_model(fake_response(model="claude-opus-5-5", iterations=iterations)) == "claude-opus-5-5"


def test_serving_model_after_refused_attempt_and_fallback():
    iterations = [SimpleNamespace(model="claude-opus-5-5"), fallback_usage("claude-sonnet-5-5")]

    assert llm._serving_model(fake_response(model="claude-opus-5-5", iterations=iterations)) == "claude-sonnet-5-5"