INSERT INTO silver.auctions (boe_ref, announcement_text, publication_date, offer_deadline, source_url, extraction_model, extraction_prompt_hash)
VALUES (%(boe_ref)s, %(announcement_text)s, %(publication_date)s, %(offer_deadline)s, %(source_url)s, %(extraction_model)s, %(extraction_prompt_hash)s)
RETURNING auction_id;   -- Return the auction_id of the row that was just inserted