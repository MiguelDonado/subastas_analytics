test_that("clicking a marker selects its row, zooms to it and opens its popup", {
  app <- AppDriver$new(app_dir = "../..", name = "marker", load_timeout = 30000)
  withr::defer(app$stop())
  app$wait_for_value(input = "lots_rows_all", timeout = 30000)
  expect_equal(app$get_value(export = "db_host"), "localhost")
  app$wait_for_idle()
  bounds_start <- app$get_value(input = "map_bounds")
  
  # The only marker in Valladolid: lot 1 of BOE-B-2026-36159
  click_marker(app, "6913202UM5161D0008ZP")
  
  # Its row is selected and shown: the table moved to its page
  app$wait_for_value(input = "lots_rows_selected", timeout = 10000)
  app$wait_for_idle()
  cells <- unlist(app$get_js(
    "Array.from(document.querySelectorAll('#lots tbody tr.selected td')).map(td => td.innerText)"
  ))
  expect_true("BOE-B-2026-36159" %in% cells)
  
  # The map zoomed in to it
  app$wait_for_value(input = "map_bounds", ignore = list(bounds_start), timeout = 10000)
  bounds_marker <- app$get_value(input = "map_bounds")
  expect_lt(bounds_marker$north - bounds_marker$south, bounds_start$north - bounds_start$south)
  
  # Its popup is open, with its catastral reference
  popup <- app$get_js("document.querySelector('.leaflet-popup-content')?.innerText ?? ''")
  expect_match(popup, "6913202UM5161D0008ZP", fixed = TRUE)
})