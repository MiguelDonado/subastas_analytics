-- Announcements in bronze that aren't in silver yet and weren't rejected, oldest first.

SELECT b.boe_ref, b.announcement_text, b.publication_date, b.source_url
FROM bronze.auctions b
LEFT JOIN silver.auctions s ON s.boe_ref = b.boe_ref
LEFT JOIN silver.rejected_announcements r ON r.boe_ref = b.boe_ref
WHERE s.boe_ref IS NULL
  AND r.boe_ref IS NULL
ORDER BY b.publication_date, b.boe_ref;