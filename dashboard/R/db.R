# Database access for the dashboard: connection to subastas-db and queries.
# Connection settings come from environment variables (dashboard/.Renviron)
library(DBI)

connect_subastas_db <- function() {
  dbConnect(
    RPostgres::Postgres(),
    host     = Sys.getenv("SUBASTAS_DB_HOST"),
    port     = as.integer(Sys.getenv("SUBASTAS_DB_PORT")),
    dbname   = Sys.getenv("SUBASTAS_DB_NAME"),
    user     = Sys.getenv("SUBASTAS_DB_USER"),
    password = Sys.getenv("SUBASTAS_DB_PASSWORD")
  )
}

read_lots <- function(con) {
  dbGetQuery(con, "SELECT * FROM gold.app_lots WHERE is_latest ORDER BY offer_deadline, boe_ref, lot_number")
}


read_lot_references <- function(con) {
  dbGetQuery(con, "SELECT lot_id, catastral_reference, latitude, longitude FROM gold.app_lot_references WHERE is_latest")
}