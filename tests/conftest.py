"""Fixtures shared by every test."""

import json

import anthropic
import pytest
import requests


def _blocked(*args, **kwargs):
    # pytest.fail raises a BaseException, not an Exception, so the `except Exception` in the code
    # can't catch it and hide it
    pytest.fail("A test tried to call a real API. Mock it instead.")


@pytest.fixture(autouse=True)
def block_real_apis(monkeypatch):
    """Safety net: no test can call Claude, the BOE, Goolzoom or healthchecks.io for real.

    autouse=True: it runs for every test without asking for it. A test reaches an API only
    through its own mock, which replaces these blocks for that test.
    """
    # Every requests call (requests.get included) goes through Session.request
    monkeypatch.setattr(requests.Session, "request", _blocked)
    monkeypatch.setattr(anthropic, "Anthropic", _blocked)

    # Basically it means replace requests.get() with _blocked(*args, **kwargs). So whatever arguments
    # I passed to requests.get() are passed to _blocked()


@pytest.fixture
def make_response():
    """Build a real requests.Response, so raise_for_status() behaves as it does with a real API.

    A fixture can return a function: the test calls it with the values it needs.
    """
    def _make(status_code: int, content: bytes = b"", json_body=None) -> requests.Response:
        response = requests.Response()
        response.status_code = status_code
        # You can provide either content or json_body to define the body of your fake HTTP response
        response._content = json.dumps(json_body).encode() if json_body is not None else content
        return response

    return _make