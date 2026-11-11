"""Goolzoom client: checks of a catastral reference (S22–S28, S34)."""

import copy
from unittest.mock import Mock

import pytest
import requests

from subastas_analytics.clients import goolzoom
from subastas_analytics.clients.goolzoom import CatastroInfo
from subastas_analytics.config import GOOLZOOM_TEST_REFERENCE

REFERENCE = "6913202UM5161D0008ZP"

# Hand-written with the keys lookup_reference reads, not copied from a real answer
RECORDS = {
    "plot": {
        "Municipality": "VALLADOLID",
        "Province": "VALLADOLID",
        "Centroid": "41.6406 -4.7247",
        "Area of the property": "1.234,5 m&sup2;",
    },
    "properties": [{"Main use": "Residencial", "Class": "Urbano"}],
    "crops": [
        {"Area": "100 m&sup2;", "Qualification": "C- Labor o labradío secano"},
        {"Area": "2.500 m&sup2;", "Qualification": "MM Pinar maderable"},
    ],
}


@pytest.fixture
def records():
    """A fresh copy for each test, so a test that changes it doesn't affect the others."""
    return copy.deepcopy(RECORDS)


@pytest.fixture
def goolzoom_returns(monkeypatch):
    """Make _get_data return the given records, and give back the mock to check how it was called."""
    def _set(records):
        get_data = Mock(return_value=records)
        monkeypatch.setattr(goolzoom, "_get_data", get_data)
        return get_data

    return _set


######################################
# Small helpers
######################################

@pytest.mark.parametrize("raw, expected", [
    ("6913202UM5161D0008ZP", "6913202UM5161D0008ZP"),
    ("6913202 UM5161D 0008 ZP", "6913202UM5161D0008ZP"),
    ("6913202-um5161d-0008-zp", "6913202UM5161D0008ZP"),
    (" 6913202UM5161D0008ZP.", "6913202UM5161D0008ZP"),
])
def test_normalize_reference(raw, expected):
    assert goolzoom.normalize_reference(raw) == expected


@pytest.mark.parametrize("text, expected", [
    ("500 m&sup2;", 500.0),
    ("1.234,5 m&sup2;", 1234.5),
    ("1.234.567 m²", 1234567.0),
    ("0,75 m&sup2;", 0.75),
])
def test_parse_area(text, expected):
    assert goolzoom._parse_area(text) == expected


def test_main_qualification_is_the_biggest_crop():
    # Compared as numbers, not text: "2.500" is bigger than "100"
    assert goolzoom._main_qualification(RECORDS["crops"]) == "MM Pinar maderable"


@pytest.mark.parametrize("crops", [None, []])
def test_s25_no_crops_gives_no_qualification(crops):
    assert goolzoom._main_qualification(crops) is None


######################################
# Request
######################################

def test_request_sends_api_key(monkeypatch, make_response):
    monkeypatch.setenv("GOOLZOOM_API_KEY", "test-key")
    get = Mock(return_value=make_response(200))
    monkeypatch.setattr(goolzoom.requests, "get", get)

    goolzoom._get("https://api.goolzoom.com/x")

    assert get.call_args.kwargs["headers"] == {"x-api-key": "test-key"}
    assert get.call_args.kwargs["timeout"] > 0


def test_existing_reference_returns_records(monkeypatch, make_response):
    monkeypatch.setattr(goolzoom, "_get", Mock(return_value=make_response(200, json_body={"records": RECORDS})))

    assert goolzoom._get_data(REFERENCE) == RECORDS


def test_s23_reference_not_found_404(monkeypatch, make_response):
    get = Mock(return_value=make_response(404))
    monkeypatch.setattr(goolzoom, "_get", get)

    assert goolzoom._get_data(REFERENCE) is None
    # 404 is clear, so the test reference isn't needed
    assert get.call_count == 1


def test_s23_reference_not_found_502_while_test_reference_works(monkeypatch, make_response):
    # When side_effect is a list, the mock returns its items one per call, in order:
    # call 1 (the reference) gets 502, call 2 (the test reference) gets 200
    get = Mock(side_effect=[make_response(502), make_response(200)])
    monkeypatch.setattr(goolzoom, "_get", get)

    assert goolzoom._get_data(REFERENCE) is None
    # call_args_list holds every call to _get, in order: [0] is the first, [1] is the second.
    # .args[0] is the first positional argument, the URL, which contains the reference.
    # So the second call was for the test reference, not another try with the same one
    assert GOOLZOOM_TEST_REFERENCE in get.call_args_list[1].args[0]


def test_s26_goolzoom_down_502_for_test_reference_too(monkeypatch, make_response):
    monkeypatch.setattr(goolzoom, "_get", Mock(side_effect=[make_response(502), make_response(502)]))

    with pytest.raises(requests.HTTPError):
        goolzoom._get_data(REFERENCE)


@pytest.mark.parametrize("status_code", [401, 429, 500])
def test_s27_other_goolzoom_errors_raise(monkeypatch, make_response, status_code):
    monkeypatch.setattr(goolzoom, "_get", Mock(return_value=make_response(status_code)))

    with pytest.raises(requests.HTTPError):
        goolzoom._get_data(REFERENCE)


######################################
# lookup_reference
######################################

def test_valid_reference(goolzoom_returns, records):
    goolzoom_returns(records)

    assert goolzoom.lookup_reference("6913202 UM5161D 0008 ZP") == CatastroInfo(
        reference=REFERENCE,
        municipality="VALLADOLID",
        province="VALLADOLID",
        use="Residencial",
        property_class="Urbano",
        surface=1234.5,
        latitude=41.6406,
        longitude=-4.7247,
        qualification="MM Pinar maderable",
    )


@pytest.mark.parametrize("raw", ["6913202UM5161D0008Z", "6913202UM5161D0008ZPX", ""])
def test_s22_reference_without_20_characters_is_rejected_without_calling_goolzoom(goolzoom_returns, raw):
    get_data = goolzoom_returns(RECORDS)

    assert goolzoom.lookup_reference(raw) is None
    get_data.assert_not_called()


def test_s23_reference_that_doesnt_exist_is_rejected(goolzoom_returns):
    goolzoom_returns(None)

    assert goolzoom.lookup_reference(REFERENCE) is None


@pytest.mark.parametrize("section, key", [
    ("plot", "Municipality"),
    ("plot", "Province"),
    ("plot", "Centroid"),
    ("property", "Main use"),
    ("property", "Class"),
])
def test_s24_reference_with_an_empty_field_is_rejected(goolzoom_returns, records, caplog, section, key):
    target = records["plot"] if section == "plot" else records["properties"][0]
    target[key] = ""
    goolzoom_returns(records)

    assert goolzoom.lookup_reference(REFERENCE) is None
    assert "has no value for" in caplog.text


def test_s25_reference_without_crops_is_stored_with_no_qualification(goolzoom_returns, records):
    del records["crops"]
    goolzoom_returns(records)

    assert goolzoom.lookup_reference(REFERENCE).qualification is None


def test_s34_empty_surface_fails(goolzoom_returns, records):
    records["plot"]["Area of the property"] = ""
    goolzoom_returns(records)

    with pytest.raises(ValueError, match=REFERENCE):
        goolzoom.lookup_reference(REFERENCE)


def test_s34_missing_surface_fails(goolzoom_returns, records):
    del records["plot"]["Area of the property"]
    goolzoom_returns(records)

    with pytest.raises(KeyError, match="Area of the property"):
        goolzoom.lookup_reference(REFERENCE)


# S28: a surprise, so it raises (FAILED in silver) instead of rejecting the lot quietly
def test_s28_missing_plot_fails(goolzoom_returns, records):
    del records["plot"]
    goolzoom_returns(records)

    with pytest.raises(KeyError):
        goolzoom.lookup_reference(REFERENCE)


def test_s28_empty_properties_fails(goolzoom_returns, records):
    records["properties"] = []
    goolzoom_returns(records)

    with pytest.raises(IndexError):
        goolzoom.lookup_reference(REFERENCE)