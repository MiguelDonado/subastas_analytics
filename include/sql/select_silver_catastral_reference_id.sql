SELECT catastral_reference_id
FROM silver.catastral_references
WHERE catastral_reference = %(reference)s;