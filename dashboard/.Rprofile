# Posit Package Manager instead of plain CRAN: on Linux it serves precompiled packages,
# so installs take seconds instead of compiling. renv records this URL in renv.lock.
# Before activate.R, so renv starts with it
options(repos = c(CRAN = "https://packagemanager.posit.co/cran/latest"))

source("renv/activate.R")
