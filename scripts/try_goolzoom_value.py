"""Print what Goolzoom returns for the value (valor por el procedimiento catastral) of a catastral reference."""

import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()  # Reads GOOLZOOM_API_KEY from .env

# Reference given on the command line, or the one from Goolzoom's example
reference = sys.argv[1] if len(sys.argv) > 1 else "15012B514003380000LQ"

response = requests.get(
    f"https://api.goolzoom.com/v1/cadastre/cadastralreference/{reference}/value",
    params={"language": "es", "extended": "true"},  # extended: with the breakdown of how the value is calculated
    headers={"x-api-key": os.environ["GOOLZOOM_API_KEY"]},
    timeout=30,
)

print(response.status_code)
try:
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
except ValueError:  # not JSON
    print(response.text)