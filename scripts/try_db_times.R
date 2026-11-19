# Times the app's database work: before the pool (a new connection on every action)
# and with the pool (connections kept open). Read-only.
# Run from dashboard/, so renv is active and R reads dashboard/.Renviron (the Neon settings):
#   cd dashboard && Rscript ../scripts/try_db_times.R
library(DBI)
source("R/db.R")  # create_db_pool(), read_lots(), read_lot_references(), read_user_reviews()

cat("Database host:", Sys.getenv("SUBASTAS_DB_HOST"), "\n\n")

# Milliseconds an expression takes
ms <- function(expr) {
  start <- Sys.time()
  force(expr)
  as.numeric(difftime(Sys.time(), start, units = "secs")) * 1000
}

# Runs f() n times and prints the first time, the median and the fastest
report <- function(label, f, n = 5) {
  times <- vapply(seq_len(n), function(i) ms(f()), numeric(1))
  cat(sprintf("%-42s first %6.0f ms | median %6.0f ms | fastest %6.0f ms\n",
              label, times[1], median(times), min(times)))
  invisible(times)
}

# A new connection, the way the app connected before the pool
connect_direct <- function() {
  dbConnect(
    RPostgres::Postgres(),
    host     = Sys.getenv("SUBASTAS_DB_HOST"),
    port     = as.integer(Sys.getenv("SUBASTAS_DB_PORT")),
    dbname   = Sys.getenv("SUBASTAS_DB_NAME"),
    user     = Sys.getenv("SUBASTAS_DB_USER"),
    password = Sys.getenv("SUBASTAS_DB_PASSWORD")
  )
}

# 1. The very first connection. If Neon was asleep, this includes waking it up
first_ms <- ms(con <- connect_direct())
cat(sprintf("%-42s %6.0f ms  (includes Neon waking up, if it was asleep)\n", "First connection", first_ms))
test_user <- dbGetQuery(con, "SELECT user_id FROM app.users WHERE username = 'test'")$user_id
dbDisconnect(con)

cat("\nBefore the pool: a new connection on every action\n")
report("Row click", function() {
  con <- connect_direct()
  on.exit(dbDisconnect(con))
  read_user_reviews(con, test_user)
})
report("Start of the app (read_app_data)", function() {
  con <- connect_direct()
  on.exit(dbDisconnect(con))
  read_lots(con)
  read_lot_references(con)
})

cat("\nWith the pool: the same queries on connections kept open\n")
# Creating the pool opens its first connection, like the app's process does when it starts
create_ms <- ms(db_pool <- create_db_pool())
cat(sprintf("%-42s %6.0f ms  (once per R process)\n", "Create the pool", create_ms))
report("Row click",                        function() read_user_reviews(db_pool, test_user))
report("Start of the app (read_app_data)", function() { read_lots(db_pool); read_lot_references(db_pool) })

# 2. After more than 60 s without queries, the pool checks a connection before lending it
#    (one extra round trip). This waits 65 s to see what the first click after a pause costs
cat("\nWaiting 65 s without queries...\n")
Sys.sleep(65)
cat(sprintf("%-42s %6.0f ms  (includes the pool's check)\n", "Row click after 65 s idle",
            ms(read_user_reviews(db_pool, test_user))))

pool::poolClose(db_pool)