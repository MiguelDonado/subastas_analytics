-- Named placeholders, so I can pass the dictionary that parse_auction returns
-- straight to cursor.execute(insert_sql, auction).
-- Positional placeholders are also valid, but values are then matched by position,
-- so I would have to pass a tuple in the right order.

-- ON CONFLICT: If a record with the same boe_ref already exists in the database, don't insert it again.

INSERT INTO bronze.auctions (boe_ref, announcement_text, publication_date, source_url)
VALUES (%(boe_ref)s, %(announcement_text)s, %(publication_date)s, %(source_url)s)
ON CONFLICT (boe_ref) DO NOTHING;