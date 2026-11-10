"""The safety net in tests/conftest.py really blocks the APIs, so no test can spend Claude credits."""

import anthropic
import pytest
import requests

# pytest.fail raises this type
Failed = pytest.fail.Exception


def test_requests_get_is_blocked():
    with pytest.raises(Failed, match="real API"):
        requests.get("https://www.boe.es")


def test_claude_client_is_blocked():
    with pytest.raises(Failed, match="real API"):
        anthropic.Anthropic()


def test_block_is_not_caught_by_except_exception():
    """load_silver catches Exception to record a FAILED announcement. The block must get past it."""
    with pytest.raises(Failed):
        try:
            anthropic.Anthropic()
        except Exception:
            pass