"""Print the Hacienda auctions the BOE published on the dates given on the command line."""

import sys
from datetime import date

from dotenv import load_dotenv

from subastas_analytics.clients.boe import fetch_auction, fetch_auction_candidates
from subastas_analytics.clients.llm import is_auction_title

load_dotenv()

test_date = "2026-10-21"

candidates = fetch_auction_candidates(date.fromisoformat(test_date))
urls = [url for title, url in candidates if is_auction_title(title)]
print(f"\n=== {test_date}: {len(urls)} auctions")
for url in urls:
    auction = fetch_auction(url)
    print(auction["boe_ref"], "|", auction["publication_date"], "|", auction["source_url"])
    print(f"{len(auction['announcement_text'])} characters:", auction["announcement_text"][:200])