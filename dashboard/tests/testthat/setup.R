# Runs once before the e2e tests: starts the local Postgres, and stops it at the end.
# Paths are relative to dashboard/tests/testthat, where testthat runs the tests

# Already loaded by shinytest2::test_app(). Written here so renv finds shinytest2
# when scanning the code and keeps it in renv.lock
library(shinytest2)

# Local database, the one used before moving to Neon. Its data is in a Docker volume
DB_ENV_FILE <- "../../../subastas-db.env"
CONTAINER   <- "subastas-db-e2e"

# --rm: the container is deleted when it stops. The data stays in the volume
status <- system2("docker", c(
  "run", "-d", "--rm", "--name", CONTAINER,
  "--env-file", DB_ENV_FILE,
  "-v", "subastas-analytics_42239a_subastas_db_data:/var/lib/postgresql/data",
  "-p", "127.0.0.1:5435:5432",
  "postgres:17"
))
if (status != 0) stop("Couldn't start ", CONTAINER, ". Is it already running? Stop it with: docker stop ", CONTAINER)

# Stops the container when all the tests have finished, even if one failed
withr::defer(system2("docker", c("stop", CONTAINER)), testthat::teardown_env())

# docker run returns before Postgres accepts connections: wait up to 30 seconds
ready <- FALSE
for (i in 1:30) {
  if (system2("docker", c("exec", CONTAINER, "pg_isready", "-q")) == 0) { ready <- TRUE; break }
  Sys.sleep(1)
}
if (!ready) stop("Postgres in ", CONTAINER, " wasn't ready after 30 seconds")

# The app connects to this container with the values in dashboard/tests/e2e.Renviron,
# which app.R reads itself in shiny.testmode

# Google Chrome, not the snap Chromium: the snap sandbox stops shinytest2 from closing it,
# so every run would leave a Chromium process behind
Sys.setenv(CHROMOTE_CHROME = "/usr/bin/google-chrome")