# Clicks the n-th row shown in the table (1 = top row of the current page), like a real mouse.
# app$click() only sends a "click" event, but DT selects rows on "mousedown",
# so the three events a real click sends are dispatched, in the same order.
# The first cell (the deadline) is clicked, not the Anuncio cell, whose link would open a new tab
click_row <- function(app, n = 1) {
  app$run_js(sprintf("
    const cell = document.querySelector('#lots tbody tr:nth-child(%d) td');
    ['mousedown', 'mouseup', 'click'].forEach(type =>
      cell.dispatchEvent(new MouseEvent(type, { bubbles: true }))
    );
  ", n))
}

# Clicks a marker on the map, like a person with the mouse.
# 1. Asks Leaflet where the marker of that catastral reference is on the page, in pixels
#    (in app.R each marker's id is its catastral reference).
# 2. Tells Chrome to press and release the left mouse button at that position
click_marker <- function(app, reference) {
  # 1. Chrome can only click at a position in pixels, so first ask Leaflet, inside the page,
  #    where the marker is. Returns [x, y]
  xy <- app$get_js(sprintf("
    // The Leaflet map drawn by leafletOutput('map')
    const map = HTMLWidgets.find('#map').getMap();
    // The marker: app.R adds each one with layerId = catastral reference, so Leaflet keeps it under that id
    const marker = map.layerManager.getLayer('marker', '%s');
    // Its latitude and longitude turned into pixels inside the map box (from the map's top-left corner)
    const point = map.latLngToContainerPoint(marker.getLatLng());
    // Where the map box is on the page: it doesn't start at the page's corner, the sidebar is on its left
    const box = map.getContainer().getBoundingClientRect();
    // The marker's position on the whole page: where the map starts + where the marker is inside it
    [box.left + point.x, box.top + point.y]
  ", reference))

  # 2. Chrome's own way of simulating the mouse. To the page it's the same as a person clicking:
  #    Chrome finds what's under the pointer (the marker) and sends it every event of a real click
  chrome <- app$get_chromote_session()
  # A click is pressing the left button and releasing it, at the same position
  for (type in c("mousePressed", "mouseReleased")) {
    chrome$Input$dispatchMouseEvent(type = type, x = xy[[1]], y = xy[[2]], button = "left", clickCount = 1)
  }
}