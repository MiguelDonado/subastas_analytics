"""Print what Goolzoom returns for the references given on the command line."""

import sys

from dotenv import load_dotenv

from subastas_analytics.config import GOOLZOOM_TEST_REFERENCE
from subastas_analytics.clients.goolzoom import lookup_reference

load_dotenv()  # Reads GOOLZOOM_API_KEY from .env

reference = GOOLZOOM_TEST_REFERENCE
fake_reference = "24142A501999990000RX"

# Prints CatastroInfo object
print(lookup_reference(reference))

# Prints None 
print(lookup_reference(fake_reference))