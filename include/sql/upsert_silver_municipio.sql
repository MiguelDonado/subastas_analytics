-- DO UPDATE changes nothing, but unlike DO NOTHING it makes RETURNING give the id of an existing row.

INSERT INTO silver.municipios (municipio, province)
VALUES (%(municipality)s, %(province)s)
ON CONFLICT (municipio, province) DO UPDATE SET municipio = EXCLUDED.municipio
RETURNING municipio_id;