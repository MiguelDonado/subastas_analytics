# App design

Design of the final application: a Shiny for Python app to explore the auctioned properties, filter them, see them on a map and mark the ones of interest.

## Layout
- **Left sidebar:** filters.
- **Main area, top:** map with the results.
- **Main area, bottom:** table with the results and their main characteristics.

Clicking a row in the table moves the map to that place. Clicking a point on the map highlights its row in the table.

## Map
QGIS is a desktop application and can't be embedded in a Shiny page, so the app uses a web map library: **ipyleaflet**, through `shinywidgets`.
- It has a built-in control to switch between layers.
- It can move the map to a point (`fly_to`) without redrawing it, which is what clicking a row needs.
- It reports marker clicks back to Shiny, so the map can also select rows in the table.

Layers, all from public map services:
- **Base map:** OpenStreetMap.
- **Aerial photo:** PNOA orthophoto from the IGN.
- **Catastro parcels:** the Catastro's public map service (WMS), which draws the parcel outlines over the map.

QGIS is still useful outside the app, to explore the data or prepare layers.

## One table row = one lot
Prices are stored per **lot**, but coordinates and surface are stored per **catastral reference**, and one lot can have several. So each table row is a lot, with:
- total surface (sum of its catastral references)
- starting price
- price per m²
- municipio and province
- use and class

Clicking a row shows all of the lot's catastral references on the map, zoomed to fit them. The price and surface filters work on these lot-level values.

Each row also links to the BOE announcement (`source_url`) and to the property's Catastro page, to check the source in one click.

## Filters
- **Province:** multi-select box; empty means all provinces.
- **Municipio:** multi-select, narrowed to the provinces chosen.
- **Starting price:** range.
- **Surface:** range.
- **Price per m²:** range. Probably the most useful number for comparing properties.
- **Use** and **class** (urbano / rústico).
- **Auction date:** range, plus an "only auctions not held yet" switch. Past auctions are mostly useful for analysis, not for deciding.
- **Status:** filter by the user's mark (see below), e.g. hide the discarded ones.

## Marking lots of interest
The user can mark each lot as **interested / maybe / discarded** and add a free-text note.

These marks are data the user enters, while bronze, silver and gold are written by the pipeline and can be rebuilt. So they live in their own schema, outside the medallion layers:

```
app.lot_reviews (boe_ref, lot_number, status, notes, updated_at)
```

The table is keyed by **`boe_ref` + `lot_number`**, not `lot_id`. `lot_id` is generated automatically, so rebuilding silver gives every lot a new number and the marks would point to the wrong lots. The BOE reference and lot number never change.

## What this means for gold
The app needs a table with one row per lot holding everything it shows and filters on. Gold can still be a star schema for analysis, and the app reads from a view built on it that joins in `app.lot_reviews`.
