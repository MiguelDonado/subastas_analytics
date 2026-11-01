# Data modelling

## Medallion architecture
The warehouse will follow the medallion architecture (bronze, silver, gold).

For the application that reads from gold, and what it needs from the data, see [app-design.md](app-design.md).

## Indexes in the silver schema
How indexes work in PostgreSQL and which ones the silver schema has ([silver_schema.sql](../data_modeling/silver/silver_schema.sql)).

### What an index is
An index works like the index at the back of a book. Without one, PostgreSQL finds rows by reading the whole table (a *sequential scan*). An index is a separate, sorted structure (a B-tree) that maps a column's values to where those rows are stored, so PostgreSQL can jump straight to the rows it needs.

Indexes have costs:
- They take disk space.
- Every insert, update or delete also has to update each index on the table, so writes get a little slower.

### Indexes PostgreSQL creates automatically
Every `PRIMARY KEY` and every `UNIQUE` constraint gets an index. PostgreSQL needs it to check quickly that a new value doesn't already exist.

| Table | Automatic indexes |
|---|---|
| `auctions` | `auction_id` (PK), `boe_ref` (UNIQUE), `source_url` (UNIQUE) |
| `lots` | `lot_id` (PK), `(auction_id, lot_number)` (UNIQUE) |
| `properties` | `property_id` (PK) |
| `municipios` | `municipio_id` (PK), `(municipio, province)` (UNIQUE) |
| `catastral_references` | `catastral_reference_id` (PK), `catastral_reference` (UNIQUE) |

### Indexes created explicitly, and why
PostgreSQL does **not** automatically index the column that holds a foreign key. It indexes only the side being pointed to, which is already a primary key. So the schema adds indexes on the foreign-key columns:

- `properties.lot_id` (`ix_properties_lot_id`)
- `catastral_references.property_id` (`ix_catastral_references_property_id`)
- `catastral_references.municipio_id` (`ix_catastral_references_municipio_id`)

They help in two ways:
1. **Joins.** Queries like "give me the properties of lot 5" or "the references in municipio 12" go straight to the matching rows instead of scanning the table.
2. **Delete checks.** When a lot is deleted, `ON DELETE CASCADE` has to find its properties, then their references. When someone tries to delete a municipio, PostgreSQL has to check that no reference points to it. Without the index, each of these is a full table scan.

`lots.auction_id` doesn't need its own index. The `UNIQUE (auction_id, lot_number)` index starts with `auction_id`, and PostgreSQL can use it to find rows by `auction_id` alone.

### How much it matters here
The tables will hold thousands of rows, not millions, so scanning them is cheap and the difference is barely noticeable. Indexing foreign-key columns is still standard practice, and it costs almost nothing at this size.