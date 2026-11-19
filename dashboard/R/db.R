# Database access for the dashboard: connection to the database (Neon) and queries.
# Connection settings come from environment variables (dashboard/.Renviron)
library(DBI)

# Pool of connections, created once per R process and shared by all its sessions (app.R).
# Each query borrows a connection that's already open and returns it right away, instead of
# opening a new one: to Neon, opening one takes ~330 ms, about 4 round trips.
# - Defaults kept: at least 1 connection stays open, and the extra ones close after 60 s unused.
# - A connection unused for more than 60 s is checked before lending it, and replaced if it's
#   dead, e.g. after Neon went to sleep and closed it.
# The query functions below receive the pool as `con`: DBI functions work the same with it
create_db_pool <- function() {
  pool::dbPool(
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
  dbGetQuery(con, "SELECT lot_id, catastral_reference, latitude, longitude, use, class, surface, qualification FROM gold.app_lot_references WHERE is_latest")
}

# Notes and statuses of one user: one row per lot that has a note or a status
read_user_reviews <- function(con, user_id) {
  dbGetQuery(
    con, 
    "SELECT boe_ref, lot_number, notes, status FROM app.lot_reviews WHERE user_id = $1",
    params = list(user_id)
  )
}

# Save a user's note and status on a lot. 
# - notes: box's text
# - status: 'interested', 'discarded' or 'none' (not reviewed)
# Several points:
# 1. Empty is saved as NULL
# 2. Both notes and status empty -> Row is deleted
# 3. Returns how many rows it changed (from dbExecute): 0 if it deleted a row that didn't exist
save_user_review <- function(con, user_id, boe_ref, lot_number, notes, status){
  if (str_trim(notes) == "") notes <- NA_character_
  if (status == "none") status <- NA_character_
  
  if (is.na(notes) && is.na(status)) {
    dbExecute(con,
              "DELETE FROM app.lot_reviews WHERE user_id = $1 AND boe_ref = $2 AND lot_number = $3",
              params = list(user_id, boe_ref, lot_number))
  } else {
    dbExecute(con, 
          "INSERT INTO app.lot_reviews (user_id, boe_ref, lot_number, notes, status)
          VALUES ($1, $2, $3, $4, $5)
          ON CONFLICT (user_id, boe_ref, lot_number)
          DO UPDATE SET notes = EXCLUDED.notes, status = EXCLUDED.status, updated_at = now()",   # EXCLUDED.notes: note that was just sent
        params = list(user_id, boe_ref, lot_number, notes, status))
  }
}





