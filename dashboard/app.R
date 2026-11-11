library(shiny)
library(leaflet)
library(bslib)

lng = -3.7
lat = 40.2
zoom = 6

ui <- page_sidebar(
  title = "Subastas",
  sidebar = sidebar("Filter will go here"),
  leafletOutput("map", height = "100%")
)

server <- function(input, output, session) {
  output$map <- renderLeaflet(
    leaflet() |> 
      setView(lng = lng, lat = lat, zoom = zoom) |> 
      # Base group
      addTiles(group = "OpenStreetMap") |> 
      addProviderTiles("Esri.WorldImagery", group = "Aerial photo Esri") |> 
      addTiles(
        urlTemplate = "https://www.ign.es/wmts/pnoa-ma?request=GetTile&service=WMTS&VERSION=1.0.0&Layer=OI.OrthoimageCoverage&Style=default&Format=image/jpeg&TileMatrixSet=GoogleMapsCompatible&TileMatrix={z}&TileRow={y}&TileCol={x}",
        attribution = "PNOA © IGN", group = "Aerial photo PNOA"
      ) |> 
      # Overlay groups
      addWMSTiles(
        "https://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx",
        layers = "PARCELA,TXTPARCELA",
        options = WMSTileOptions(format = "image/png", transparent = TRUE),
        attribution = "© Dirección General del Catastro", group = "Catastro parcels"
      ) |>
      addWMSTiles(
        "https://servicios.idee.es/wms-inspire/hidrografia",
        layers = "HY.Network,HY.PhysicalWaters.Waterbodies",
        options = WMSTileOptions(format = "image/png", transparent = TRUE),
        attribution = "© IGN", group = "Hydrography"
      ) |> 
      addLayersControl(
        baseGroups = c("OpenStreetMap", "Aerial photo Esri", "Aerial photo PNOA"),
        overlayGroups = c("Catastro parcels", "Hydrography"),
        options = layersControlOptions(collapsed = FALSE)
      ) |> 
      hideGroup(c("Catastro parcels", "Hydrography"))
  )
}

shinyApp(ui, server)
