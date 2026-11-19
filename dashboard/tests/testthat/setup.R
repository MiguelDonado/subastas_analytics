# Runs once before the e2e tests: starts a blank Postgres, fills it with the tables of the repo
# and the data of e2e_data.sql, and stops it at the end.
# Paths are relative to dashboard/tests/testthat, where testthat runs the tests

# Already loaded by shinytest2::test_app(). Written here so renv finds shinytest2
# when scanning the code and keeps it in renv.lock
library(shinytest2)

CONTAINER <- "subastas-db-e2e"
SQL_DIR   <- "../../../include/sql"

# Blank Postgres 17, with no volume: every run starts from an empty database.
# POSTGRES_PASSWORD and POSTGRES_DB are read by the image to create its owner user (postgres)
# and the database. Only for this throwaway container, so they can be written here
status <- system2("docker", c(
  "run", "-d", "--rm", "--name", CONTAINER,
  "-e", "POSTGRES_PASSWORD=postgres",
  "-e", "POSTGRES_DB=subastas",
  "-p", "127.0.0.1:5435:5432",
  "postgres:17"
))
if (status != 0) stop("Couldn't start ", CONTAINER, ". Is it already running? Stop it with: docker stop ", CONTAINER)

# Stops the container when all the tests have finished, even if one failed. --rm then deletes it
withr::defer(system2("docker", c("stop", CONTAINER)), testthat::teardown_env())

# Wait up to 30 seconds until Postgres accepts connections.
# -h 127.0.0.1: on its first start the image runs a temporary Postgres to create the database,
# reachable only from inside, and then restarts it. Asking through the network only answers
# once the real one is up
ready <- FALSE
for (i in 1:30) {
  if (system2("docker", c("exec", CONTAINER, "pg_isready", "-q", "-h", "127.0.0.1")) == 0) { ready <- TRUE; break }
  Sys.sleep(1)
}
if (!ready) stop("Postgres in ", CONTAINER, " wasn't ready after 30 seconds")

# Runs a .sql file with the psql inside the container, as the owner.
# ON_ERROR_STOP: stops at the first error, instead of going on and failing later in a test
run_sql <- function(file) {
  status <- system2(
    "docker", c("exec", "-i", CONTAINER, "psql", "-U", "postgres", "-d", "subastas", "-q", "-v", "ON_ERROR_STOP=1"),
    stdin = file
  )
  if (status != 0) stop("Loading ", file, " into ", CONTAINER, " failed")
}

# 1. Tables and views from the current code. Bronze and silver aren't needed: the app only reads gold and app
run_sql(file.path(SQL_DIR, "create_gold.sql"))
run_sql(file.path(SQL_DIR, "create_app.sql"))
run_sql(file.path(SQL_DIR, "create_app_role.sql"))

# 2. The app's database user gets the password of tests/e2e.Renviron
#    (create_app_role.sql leaves it without one, so it never ends up in git)
status <- system2("docker", c(
  "exec", CONTAINER, "psql", "-U", "postgres", "-d", "subastas", "-q", "-v", "ON_ERROR_STOP=1",
  "-c", shQuote("ALTER ROLE subastas_app PASSWORD 'subastas_app'")
))
if (status != 0) stop("Setting the password of subastas_app failed")

# 3. The data: 210 lots in gold and the user "test"
run_sql("../e2e_data.sql")

# The app connects to this container with the values in dashboard/tests/e2e.Renviron,
# which app.R reads itself in shiny.testmode

# Google Chrome, not the snap Chromium: the snap sandbox stops shinytest2 from closing it,
# so every run would leave a Chromium process behind. GitHub's runners have it in the same place
Sys.setenv(CHROMOTE_CHROME = "/usr/bin/google-chrome")
