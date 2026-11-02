"""Look up catastral references in the Goolzoom API, which serves Catastro data."""

import html
import os
import re
from dataclasses import dataclass

import requests

from .config import GOOLZOOM_REF_CAT_DATA_ENDPOINT, GOOLZOOM_TEST_REFERENCE


# To store data in a structured way
@dataclass
class CatastroInfo: 
    reference: str
    municipality: str
    province: str
    use: str | None                 # Main use: Agrario
    property_class: str             # Class: Rustic
    surface: float           
    latitude: float 
    longitude: float
    

def _normalize_reference(raw: str) -> str:
    """Make sure reference is correctly written"""
    # Remove non-alphanumeric characters
    return re.sub(r"[^0-9A-Za-z]", "", raw).upper()

def _get(path: str, timeout: float = 30) -> requests.Response:
    """Standardize how requests are made"""
    return requests.get(
        path,
        headers={"x-api-key": os.environ["GOOLZOOM_API_KEY"]},
        timeout=timeout,
    )

def _get_data(reference: str) -> dict | None:
    path = GOOLZOOM_REF_CAT_DATA_ENDPOINT.format(catastral_reference=reference)
    response = _get(path)
    # Goolzoom answers 502 both for a reference that doesn't exist and for an outage.
    # To distinguish in scenario we are, we check with a reference that we know it exists
    # If still does not work then we will know is because API is down.
    if response.status_code == 502:
        _get(
            GOOLZOOM_REF_CAT_DATA_ENDPOINT.format(catastral_reference=GOOLZOOM_TEST_REFERENCE)
        ).raise_for_status() 
        # If we reach this point, it means the reference did not exist and API is working
        return None
    # If there is an error it raises an exception and exists the function

    # API also says that when a reference does not exist it returns 404
    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json()["records"]

def _parse_area(text: str | None) -> float | None:
    if not text:
        return None
    # html.unescape(): Convert HTML code to the real character
    number = html.unescape(text).split()[0]
    return float(number.replace(".", "").replace(",", "."))

def lookup_reference(raw_reference: str) -> CatastroInfo | None:
    """Return the Catastro data of a reference, or None if it isn't 20 characters or
    doesn't exist"""
    reference = _normalize_reference(raw_reference)
    # Case 1: Reference is not 20 characters long
    if len(reference) != 20:
        return None

    records = _get_data(reference)
    # Case 2: Reference doesnt exist
    if records is None:
        return None

    plot = records["plot"]
    property = records["properties"][0]
    latitude, longitude = plot["Centroid"].split()
    return CatastroInfo(
        reference=reference,
        municipality=plot["Municipality"],
        province=plot["Province"],
        use=property["Main use"],
        property_class=property["Class"],
        surface=_parse_area(plot["Area of the property"]),
        latitude=float(latitude),
        longitude=float(longitude)
    )



    




