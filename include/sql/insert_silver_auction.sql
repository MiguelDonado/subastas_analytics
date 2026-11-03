INSERT INTO silver.auctions (boe_ref, announcement_text, publication_date, held_at, source_url)
VALUES (%(boe_ref)s, %(announcement_text)s, %(publication_date)s, %(held_at)s, %(source_url)s)
RETURNING auction_id;   -- Return the auction_id of the row that was just inserted