"""
Stores constants
"""

import re

##########################
# BOE 
##########################

# Template string: str.format() replaces it with the value of the keyword argument that has the same name
BOE_SUMARIO_ENDPOINT = "https://www.boe.es/datosabiertos/api/boe/sumario/{fecha}"

# Regex: \b: returns a match where the characters are at beginning or end of a word
AUCTION_TITLE_RE = re.compile(
    r"Delegaci[oó]n de Econom[ií]a y Hacienda.*\bsubasta",
    re.IGNORECASE | re.DOTALL,
)

##########################
# Goolzoom 
##########################
# Template string: str.format() replaces it with the value of the keyword argument that has the same name
GOOLZOOM_REF_CAT_DATA_ENDPOINT = "https://api.goolzoom.com/v1/cadastre/cadastralreference/{catastral_reference}/data"
GOOLZOOM_TEST_REFERENCE = "15012B514003380000LQ"