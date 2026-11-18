test_that("a saved note and status show in the row, and come back when it's selected again", {
  # Starts with no notes for "test", and deletes the ones it writes at the end, even if a check fails
  delete_test_reviews()
  withr::defer(delete_test_reviews())

  app <- AppDriver$new(app_dir = "../..", name = "note-status", load_timeout = 30000)
  withr::defer(app$stop())
  app$wait_for_value(input = "lots_rows_all", timeout = 30000)

  # Safety check before anything else: the app must use the local database, never Neon
  expect_equal(app$get_value(export = "db_host"), "localhost")
  app$wait_for_idle()

  # Select the first row: Guardar is enabled
  click_row(app, 1)
  app$wait_for_value(input = "lots_rows_selected", timeout = 10000)
  app$wait_for_idle()
  expect_false(app$get_js("$('#save_note').prop('disabled')"))

  # Set a status and a note, and save them
  app$set_inputs(status = "interested", note = "Nota del test e2e")
  app$click("save_note")
  app$wait_for_idle()

  # The selected row shows them. Estado and Nota are its last two cells
  cells <- unlist(app$get_js(
    "Array.from(document.querySelectorAll('#lots tbody tr.selected td')).map(td => td.innerText)"
  ))
  expect_equal(tail(cells, 2), c("Interesado", "Nota del test e2e"))

  # Click it again to deselect it: the card goes back to empty
  click_row(app, 1)
  app$wait_for_idle()
  expect_null(app$get_value(input = "lots_rows_selected"))
  expect_equal(app$get_value(input = "status"), "none")
  expect_equal(app$get_value(input = "note"), "")
  expect_true(app$get_js("$('#save_note').prop('disabled')"))

  # Select it again: the saved values come back from the database
  click_row(app, 1)
  app$wait_for_value(input = "lots_rows_selected", timeout = 10000)
  app$wait_for_idle()
  expect_equal(app$get_value(input = "status"), "interested")
  expect_equal(app$get_value(input = "note"), "Nota del test e2e")
  expect_false(app$get_js("$('#save_note').prop('disabled')"))
})