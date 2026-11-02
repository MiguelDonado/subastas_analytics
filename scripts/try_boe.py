"""Print the Hacienda auctions the BOE published on the dates given on the command line."""

import sys
from datetime import date

from dotenv import load_dotenv

from subastas_analytics.boe import get_auction_info, get_auction_urls

load_dotenv()

test_date = "2026-10-21"

urls = get_auction_urls(date.fromisoformat(test_date))
print(f"\n=== {test_date}: {len(urls)} auctions")
for url in urls:
    auction = get_auction_info(url)
    print(auction["boe_ref"], "|", auction["publication_date"], "|", auction["source_url"])
    print(f"{len(auction['announcement_text'])} characters:", auction["announcement_text"][:200])