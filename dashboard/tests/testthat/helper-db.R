# Deletes every note and status of the user "test", directly in the database.
# "test" in local db only exists for the e2e tests, so this leaves app.lot_reviews as it was before them.
# Connects with the same values as the app in the tests (dashboard/tests/e2e.Renviron)
delete_test_reviews <- function() {
  readRenviron("../e2e.Renviron")
  con <- DBI::dbConnect(
    RPostgres::Postgres(),
    host     = Sys.getenv("SUBASTAS_DB_HOST"),
    port     = as.integer(Sys.getenv("SUBASTAS_DB_PORT")),
    dbname   = Sys.getenv("SUBASTAS_DB_NAME"),
    user     = Sys.getenv("SUBASTAS_DB_USER"),
    password = Sys.getenv("SUBASTAS_DB_PASSWORD")
  )
  on.exit(DBI::dbDisconnect(con))  # closes the connection however this function ends
  DBI::dbExecute(con, "
    DELETE FROM app.lot_reviews
    WHERE user_id = (SELECT user_id FROM app.users WHERE username = 'test')
  ")
}