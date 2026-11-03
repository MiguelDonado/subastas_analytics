"""Print the Hacienda auctions the BOE published on the dates given on the command line."""

import sys
from datetime import date

from dotenv import load_dotenv

from subastas_analytics.clients.boe import fetch_auction, fetch_auction_urls

load_dotenv()

test_date = "2026-10-21"

urls = fetch_auction_urls(date.fromisoformat(test_date))
print(f"\n=== {test_date}: {len(urls)} auctions")
for url in urls:
    auction = fetch_auction(url)
    print(auction["boe_ref"], "|", auction["publication_date"], "|", auction["source_url"])
    print(f"{len(auction['announcement_text'])} characters:", auction["announcement_text"][:200])