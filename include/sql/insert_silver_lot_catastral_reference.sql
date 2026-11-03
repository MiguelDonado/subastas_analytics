-- ON CONFLICT: a lot can repeat a reference, for example written once with spaces and once without.

INSERT INTO silver.lots_catastral_references (lot_id, catastral_reference_id)
VALUES (%(lot_id)s, %(reference_id)s)
ON CONFLICT (lot_id, catastral_reference_id) DO NOTHING;