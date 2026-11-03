"""Check that Claude tells auctions apart from notices that only change an earlier auction.

Calls is_auction_title directly, without the regex filter, so it also tests the notices the
regex would have dropped. Each title is one API call.
"""

from dotenv import load_dotenv

from subastas_analytics.clients.llm import is_auction_title

load_dotenv()  # Reads ANTHROPIC_API_KEY from .env

# (title, expected is_auction)
TITLES = [
    # Real auctions from the BOE, including later rounds and goods that aren't properties
    ("Resolución de la Delegación de Economía y Hacienda de Huelva, por la que se convoca tercera subasta de varios inmuebles propiedad del Estado, sitos en la provincia de Huelva.", True),
    ("Anuncio de la Delegación de Economía y Hacienda en Pontevedra por el que se convoca tercera y cuarta subasta de varios lotes de fincas rústicas situadas en A Estrada, Cuntis y Vila de Cruces.", True),
    ("Resolución de la Delegación Especial de Economía y Hacienda en Cantabria convocando subasta pública de diversos inmuebles el 8 de octubre de 2025.", True),
    ("Resolución de la Delegación de Economía y Hacienda en Cádiz por la que se anuncia la enajenación de un bien mueble en pública subasta.", True),
    # Real notices from the BOE
    ("Corrección de errores del anuncio de la Delegación de Economía y Hacienda de Cuenca de subasta pública de varias fincas urbanas.", False),
    ("Resolución de la Delegación de Economía y Hacienda en Granada, por la que se retira el Lote 1 de la subasta pública de bienes inmuebles convocada por la Administración General del Estado.", False),
    ("Resolución de la Delegación de Economía y Hacienda en Alicante por la que se acuerda la suspensión de la subasta pública de bienes inmuebles propiedad de la Administración General del Estado.", False),
    ("Resolución de la Delegación de Economía y Hacienda en Asturias, por la que se acuerda la anulación de la venta por subasta pública del lote nº 17 de la subasta de 28-10-2026.-.", False),
    ("Resolución de la Delegación de Economía y Hacienda de León por la que se acuerda desestimar lote 12 de la subasta fincas rústicas a celebrar el 26 de noviembre de 2026.", False),
    ("Anuncio de la Delegación Especial de Economía y Hacienda en la Comunidad Valenciana-Valencia sobre la rectificación del anuncio de licitación de subasta patrimonial.", False),
    # Made up: notices with wording the regex doesn't cover. This is what the LLM check is for
    ("Resolución de la Delegación de Economía y Hacienda en Burgos por la que se deja sin efecto la subasta pública convocada para el 12 de marzo de 2027.", False),
    ("Anuncio de la Delegación de Economía y Hacienda en Lugo sobre la revocación de la subasta pública de fincas rústicas publicada el 5 de febrero de 2027.", False),
    ("Resolución de la Delegación de Economía y Hacienda en Toledo por la que se acuerda el desistimiento de la subasta de un inmueble en la provincia de Toledo.", False),
    ("Anuncio de la Delegación de Economía y Hacienda en Zamora por el que se amplía el plazo de presentación de ofertas de la subasta pública convocada el 4 de enero de 2027.", False),
    ("Anuncio de la Delegación de Economía y Hacienda en Soria por el que se declara desierta la subasta pública celebrada el 20 de enero de 2027.", False),
]

failures = 0
for title, expected in TITLES:
    result = is_auction_title(title)
    if result != expected:
        failures += 1

print(f"\n{len(TITLES) - failures}/{len(TITLES)} correct")
