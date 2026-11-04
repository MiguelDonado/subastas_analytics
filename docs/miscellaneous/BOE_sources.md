# Data sources: Hacienda RSS vs. BOE Open Data API

Two ways to collect the State asset auctions (*subastas y concursos de bienes del Patrimonio del Estado*) published by the Delegaciones de Economía y Hacienda.

## Hacienda RSS feed

`https://www.hacienda.gob.es/_layouts/15/RssSubastas.aspx?hiloId=12`

Official RSS feed attached to the [Hacienda auctions listing](https://www.hacienda.gob.es/es-ES/Areas%20Tematicas/Patrimonio%20del%20Estado/Gestion%20Patrimonial%20del%20Estado/Paginas/Subastas/ListadoSubastasConcursos.aspx). Each item has a title, the link to the detail page, the delegación, the auction date/time and the publication date.

**Advantages**
- Clean RSS 2.0 XML, trivial to parse.
- Scoped to Patrimonio del Estado auctions only, so no filtering is needed.
- Links to the Hacienda detail page, the only place where the *pliego de condiciones* PDF is published.

**Disadvantages**
- Only the **8 most recent** items, so there is no history (the listing page itself shows 25).
- Lot data (descriptions, prices, catastral references) is not in the feed. You have to scrape the detail page and parse the pliego PDF.
- The site is SharePoint/ASP.NET. Its REST endpoints (`/_api`, `ListData.svc`) are disabled, and the listing pagination uses `__VIEWSTATE` form posts, so a backfill means scraping.
- Brittle: any redesign of the site breaks the scraper.

## BOE Open Data API

1. Daily summary: `GET https://www.boe.es/datosabiertos/api/boe/sumario/YYYYMMDD` (`Accept: application/json`)
2. Announcement: `GET https://www.boe.es/diario_boe/xml.php?id=BOE-B-YYYY-NNNNN`

Auctions appear in section *V. Anuncios – B. Otros anuncios oficiales*, department *MINISTERIO DE HACIENDA*, with titles like *"Resolución de la Delegación de Economía y Hacienda de … por la que se anuncia subasta…"*.

**Advantages**
- Official, documented, stable API with persistent identifiers (`BOE-B-…`).
- Full history: you can walk every daily summary to backfill and then load new days incrementally.
- The announcement text contains every lot, its location, area, catastral reference and *tipo de licitación* for each auction round, which is more detail than the Hacienda detail page.
- Each announcement also links to its official PDF (`url_pdf`).
- The same feed covers other bodies' auctions (Defensa, Seguridad Social) if the scope grows.

**Disadvantages**
- The `<analisis>` block is empty for these announcements, so the lot data is free text and needs regex/NLP extraction.
- Text format varies between delegaciones and over time, so the parsers need maintenance.
- Needs filtering (section + department + title), and the Defensa and Seguridad Social auctions published in the same section must be excluded.
- The *pliego de condiciones* is only referenced in prose ("disponible en www.hacienda.gob.es"), with no URL.
- Coverage of every Hacienda auction is not yet verified.

## Decision

Use the **BOE API as the primary source** for discovery, history and lot data. Use the **Hacienda RSS as a secondary check** of coverage, and as the way to fetch pliego PDFs if they are ever needed.

