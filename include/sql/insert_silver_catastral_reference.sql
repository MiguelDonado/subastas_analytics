INSERT INTO silver.catastral_references
    (catastral_reference, latitude, longitude, use, class, surface, qualification, municipio_id)
VALUES
    (%(reference)s, %(latitude)s, %(longitude)s, %(use)s, %(property_class)s, %(surface)s, %(qualification)s, %(municipio_id)s)
RETURNING catastral_reference_id;