"""Look up catastral references in the Goolzoom API, which serves Catastro data."""

import html
import logging
import os
import re
from dataclasses import dataclass

import requests

from ..config import GOOLZOOM_REF_CAT_DATA_ENDPOINT, GOOLZOOM_TEST_REFERENCE

logger = logging.getLogger(__name__)

# To store data in a structured way
@dataclass
class CatastroInfo: 
    reference: str
    municipality: str
    province: str
    use: str                        # Main use: Agrario
    property_class: str             # Class: Rustic
    surface: float           
    latitude: float 
    longitude: float
    qualification: str | None       # Qualification of the biggest crop: MM Pinar maderable


def normalize_reference(raw: str) -> str:
    """Make sure reference is correctly written"""
    # Remove non-alphanumeric characters
    return re.sub(r"[^0-9A-Za-z]", "", raw).upper()

def _parse_area(text: str) -> float:
    # html.unescape(): Convert HTML code to the real character
    number = html.unescape(text).split()[0]
    return float(number.replace(".", "").replace(",", "."))

def _main_qualification(crops: list[dict] | None) -> str | None:
    """Return the qualification of the crop with the biggest area, or None if there are no crops"""
    if not crops:
        return None
    # Lambda function (anonymous function): 
    # The key argument in max, tell us which value we are going to use when comparing elements
    # Here the lambda function, takes the argument crop, and returns the area of the element.
    # Once we have extracted the max element, we return its qualification
    return max(crops, key=lambda crop: _parse_area(crop["Area"]))["Qualification"]

def _get(path: str, timeout: float = 30) -> requests.Response:
    """Standardize how requests are made"""
    return requests.get(
        path,
        headers={"x-api-key": os.environ["GOOLZOOM_API_KEY"]},
        timeout=timeout,
    )

def _get_data(reference: str) -> dict | None:
    """Get the data of a reference, or None if it doesn't exist"""
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

    # API also says that when a reference does not exist it returns 404
    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json()["records"]

def lookup_reference(raw_reference: str) -> CatastroInfo | None:
    """Return the Catastro data of a reference, or None if it isn't 20 characters,
    doesn't exist or has incomplete data"""
    reference = normalize_reference(raw_reference)
    # Case 1: Reference is not 20 characters long
    if len(reference) != 20:
        logger.warning("Reference %s does not have 20 characters", reference)
        return None

    records = _get_data(reference)
    # Case 2: Reference doesnt exist
    if records is None:
        logger.warning("Reference %s does not exist in Catastro", reference)
        return None

    plot = records["plot"]
    # [0]: Because it returns a list even if its one element
    # Cuz in some cases if its a building one ref catastral may hold several properties.
    property = records["properties"][0]
    fields = {
        "municipality": plot["Municipality"],
        "province": plot["Province"],
        "use": property["Main use"],
        "class": property["Class"],
        "centroid": plot["Centroid"],
    }
    # Case 3: Reference exists but some field is empty
    missing = [name for name, value in fields.items() if not value]
    if missing:
        logger.warning("Reference %s has no value for %s", reference, ", ".join(missing))
        return None

    # Case 4: Empty surface. Every property should have one, so it's a surprise: fail the announcement and alert (S34)
    # A missing key is covered too: it raises KeyError: 'Area of the property', which is already a clear error
    if not plot["Area of the property"]:
        raise ValueError(f"Reference {reference} has no surface")

    latitude, longitude = plot["Centroid"].split()
    return CatastroInfo(
        reference=reference,
        municipality=plot["Municipality"],
        province=plot["Province"],
        use=property["Main use"],
        property_class=property["Class"],
        surface=_parse_area(plot["Area of the property"]),
        latitude=float(latitude),
        longitude=float(longitude),
        qualification=_main_qualification(records.get("crops")),
    )



    




