# Login: checks the user and password typed in shinymanager's login screen against app.users

# make_check_user() returns the function that checks each login, with the app's pool of
# connections inside it. It's built in app.R: secure_server(check_credentials = make_check_user(db_pool)).
# shinymanager calls that function on every login, and requires this exact input and output:
# Input: the user and password that were typed. Nothing else, so the pool can't be one of its
#        arguments: the function keeps the pool it was built with (a closure)
# Output: a list with these keys
#   result:    TRUE if the login is correct, FALSE if not
#   user_info: only when result is TRUE, a list with what the app needs to know about the user
#              (here user and user_id). The server reads them later, e.g. res_auth$user_id.
#              user_id is what the app uses; user is the name, which shinymanager itself uses
# The pool isn't read as a global variable: Shiny loads the files in R/ into a different
# environment than app.R, and from here db_pool can't be found
make_check_user <- function(pool) {
  function(user, password) {
    # $1 + params: the typed name is sent as a value, never pasted into the SQL,
    # so a name like ' OR 1=1 -- can't change the query (SQL injection)
    row <- dbGetQuery(
      pool,
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
}
