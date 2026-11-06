"""
Stores constants
"""

import re
from pathlib import Path

##########################
# SQL
##########################
# Where the project's include/ folder is inside the Airflow containers
SQL_DIR = Path("/usr/local/airflow/include/sql")

##########################
# BOE
##########################

# Template string: str.format() replaces it with the value of the keyword argument that has the same name
BOE_SUMARIO_ENDPOINT = "https://www.boe.es/datosabiertos/api/boe/sumario/{fecha}"

# Regex: \b: returns a match where the characters are at beginning or end of a word
AUCTION_TITLE_RE = re.compile(
    r"Delegaci[oó]n (Especial )?de Econom[ií]a y Hacienda.*\bsubasta",
    re.IGNORECASE | re.DOTALL,
)

# Titles that also mention a subasta, but only correct, suspend or cancel an earlier announcement
NON_AUCTION_TITLE_RE = re.compile(
    r"\b(correcci[oó]n de errores|rectificaci[oó]n|suspen|retira|anulaci[oó]n|desestim|exclusi[oó]n|modifica|aplazamiento)",
    re.IGNORECASE,
)

# Near miss: missed by a small margin. AUCTION_TITLE_RE misses these titles, but only just.
# Titles that look like a Hacienda auction but don't match AUCTION_TITLE_RE. They're only logged,
# so a change in the wording shows up in the Airflow log. Just "subasta" would log 100+ titles a week
# (Seguridad Social, Ministerio de Cultura...), while this one logged none between August and October 2026.
NEAR_MISS_TITLE_RE = re.compile(r"Hacienda.*\bsubasta", re.IGNORECASE | re.DOTALL)

##########################
# Goolzoom
##########################
# Template string: str.format() replaces it with the value of the keyword argument that has the same name
GOOLZOOM_REF_CAT_DATA_ENDPOINT = "https://api.goolzoom.com/v1/cadastre/cadastralreference/{catastral_reference}/data"
GOOLZOOM_TEST_REFERENCE = "15012B514003380000LQ"