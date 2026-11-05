"""Print what Claude extracts from the BOE announcements given on the script"""

import sys
from datetime import date

from dotenv import load_dotenv

from subastas_analytics.clients.boe import fetch_auction, fetch_auction_urls
from subastas_analytics.clients.llm import extract_info_announcement

load_dotenv()  # Reads ANTHROPIC_API_KEY from .env

test_date = "2026-10-21"
urls = fetch_auction_urls(date.fromisoformat(test_date))
for url in urls:
    auction = fetch_auction(url)
    announcement, extraction_model = extract_info_announcement(auction["announcement_text"])
    print(f"\n=== {auction["boe_ref"]} | model: {extraction_model} | held_date: {announcement.held_date} | lots: {len(announcement.lots)}")
    for lot in announcement.lots:
        print(f"Lot {lot.lot_number} | {lot.starting_price} | {lot.catastral_references}")