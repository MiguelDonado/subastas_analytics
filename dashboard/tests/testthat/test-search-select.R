test_that("searching updates the table and the map, and selecting a row zooms to it", {
  # Starts the app in its own R process, and opens it in a headless Chrome
  app <- AppDriver$new(app_dir = "../..", name = "search-select", load_timeout = 30000)
  # Closes Chrome and stops the app at the end, even if a check fails
  withr::defer(app$stop())

  # lots_rows_all is sent by the table once it's drawn, so the app has started
  app$wait_for_value(input = "lots_rows_all", timeout = 30000)

  # Safety check before anything else: the app must use the local database, never Neon
  expect_equal(app$get_value(export = "db_host"), "localhost")
  
  # Let the first zoom to the active lots finish before reading the starting state
  app$wait_for_idle()
  
  # Starting state: only active lots. There are some on the fixed test date
  rows_before   <- length(app$get_value(input = "lots_rows_all"))
  bounds_before <- app$get_value(input = "map_bounds")
  expect_gt(rows_before, 0)
  
  # Turn off "Solo subastas activas" and search
  app$set_inputs(only_upcoming = FALSE)
  app$click("update")
  
  # The map zoomed to the new lots: waits until its bounds are different from before,
  # and fails if they never change
  app$wait_for_value(input = "map_bounds", ignore = list(bounds_before), timeout = 10000)
  
  # The table has more lots: the expired ones are back
  expect_gt(length(app$get_value(input = "lots_rows_all")), rows_before)
  
  # Bounds after the search, to compare with the zoom to the row.
  # wait_for_idle: the table is also redrawn by the search, so the click has to wait for it
  app$wait_for_idle()
  bounds_search <- app$get_value(input = "map_bounds")
  
  # Click the first row shown (helper-click.R)
  click_row(app, 1)
  
  # It's selected. lots_rows_selected is the row's number before any sorting, so
  # it's compared with the number of the first row shown, lots_rows_all[1].
  # wait_for_value: waits until the selection reaches Shiny, instead of reading it right away
  expect_equal(
    app$wait_for_value(input = "lots_rows_selected", timeout = 10000),
    app$get_value(input = "lots_rows_all")[1]
  )
  
  # The map zoomed to that lot: the bounds change...
  app$wait_for_value(input = "map_bounds", ignore = list(bounds_search), timeout = 10000)
  bounds_row <- app$get_value(input = "map_bounds")
  # ...and the area shown is smaller than the search's, which had every lot
  expect_lt(bounds_row$north - bounds_row$south, bounds_search$north - bounds_search$south)
})