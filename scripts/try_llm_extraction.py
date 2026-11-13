"""Print what Claude extracts from the BOE announcements given on the script"""

import sys
from datetime import date

from dotenv import load_dotenv

from subastas_analytics.clients.boe import fetch_auction, fetch_auction_candidates
from subastas_analytics.clients.llm import extract_info_announcement, is_auction_title

load_dotenv()  # Reads ANTHROPIC_API_KEY from .env

test_date = "2026-10-21"
candidates = fetch_auction_candidates(date.fromisoformat(test_date))
urls = [url for _, title, url in candidates if is_auction_title(title)]
for url in urls:
    auction = fetch_auction(url)
    # fetch_auction returns the publication date as text, for bronze
    publication_date = date.fromisoformat(auction["publication_date"])
    announcement, extraction_model = extract_info_announcement(auction["announcement_text"], publication_date)
    print(f"\n=== {auction["boe_ref"]} | model: {extraction_model} | offer_deadline: {announcement.offer_deadline} | lots: {len(announcement.lots)}")
    for lot in announcement.lots:
        print(f"Lot {lot.lot_number} | {lot.starting_price} | {lot.catastral_references}")