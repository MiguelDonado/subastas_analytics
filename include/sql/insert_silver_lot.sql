INSERT INTO silver.lots (auction_id, lot_number, starting_price)
VALUES (%(auction_id)s, %(lot_number)s, %(starting_price)s)
RETURNING lot_id;