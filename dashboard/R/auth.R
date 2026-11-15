# Login: checks the user and password typed in shinymanager's login screen against app.users

# The name check_user isn't required: the function is passed to shinymanager in the server,
# secure_server(check_credentials = check_user), and shinymanager calls it on every login.
# Any name works, but shinymanager requires this exact input and output:
# Input: the user and password that were typed
# Output: a list with these keys
#   result:    TRUE if the login is correct, FALSE if not
#   user_info: only when result is TRUE, a list with what the app needs to know about the user
#              (here user and user_id). The server reads them later, e.g. res_auth$user_id.
#              user_id is what the app uses; user is the name, which shinymanager itself uses
check_user <- function(user, password) {
  con <- connect_subastas_db()
  on.exit(dbDisconnect(con))  # closes the connection however the function ends

  # $1 + params: the typed name is sent as a value, never pasted into the SQL,
  # so a name like ' OR 1=1 -- can't change the query (SQL injection)
  row <- dbGetQuery(
    con,
    "SELECT user_id, password_hash FROM app.users WHERE username = $1",
    params = list(user)
  )

  # Unknown user and wrong password give the same answer, so the login doesn't reveal which names exist.
  # password_verify hashes the typed password with the salt stored in the hash, and compares
  ok <- nrow(row) == 1 && sodium::password_verify(row$password_hash, password)

  if (ok) {
    list(result = TRUE, user_info = list(user = user, user_id = row$user_id))
  } else {
    list(result = FALSE)
  }
}