library(shiny)
library(leaflet)
library(bslib)
library(DT)

# Santiago de Compostela (initial default view)
lng = -8.5448
lat = 42.8782
zoom = 13

# Lots
con <- connect_subastas_db()
lots <- read_lots(con)
dbDisconnect(con)

ui <- page_sidebar(
  title = "Subastas",
  sidebar = sidebar("Filter will go here"),
  layout_columns(
    col_widths = 12,
    row_heights = c(3, 2), # 60% / 40%
    card(leafletOutput("map"), full_screen = TRUE),
    card(DTOutput("lots"), full_screen = TRUE, class = "small") # small text
  )
)

server <- function(input, output, session) {
  output$lots <- renderDT(lots)
  output$map <- renderLeaflet(
    leaflet() |> 
      setView(lng = lng, lat = lat, zoom = zoom) |> 
      ############
      # Base group
      ############
      addTiles(
        urlTemplate = "https://www.ign.es/wmts/pnoa-ma?request=GetTile&service=WMTS&VERSION=1.0.0&Layer=OI.OrthoimageCoverage&Style=default&Format=image/jpeg&TileMatrixSet=GoogleMapsCompatible&TileMatrix={z}&TileRow={y}&TileCol={x}",
        attribution = "PNOA © IGN", group = "Satelite"
      ) |>
      addTiles(
        urlTemplate = "https://www.ign.es/wmts/ign-base?request=GetTile&service=WMTS&VERSION=1.0.0&Layer=IGNBaseOrto&Style=default&Format=image/png&TileMatrixSet=GoogleMapsCompatible&TileMatrix={z}&TileRow={y}&TileCol={x}",
        attribution = "© IGN", group = "Satelite"
      ) |>
      addTiles(
        urlTemplate = "https://www.ign.es/wmts/mapa-raster?request=GetTile&service=WMTS&VERSION=1.0.0&Layer=MTN&Style=default&Format=image/jpeg&TileMatrixSet=GoogleMapsCompatible&TileMatrix={z}&TileRow={y}&TileCol={x}",
        attribution = "MTN © IGN", group = "Mapa Topografico"
      ) |>
      ############
      # Overlay groups
      ############
      addWMSTiles(
        "https://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx",
        layers = "PARCELA,TXTPARCELA",
        options = WMSTileOptions(format = "image/png", transparent = TRUE),
        attribution = "© Dirección General del Catastro", group = "Parcelas catastro"
      ) |>
      addWMSTiles(
        "https://servicios.idee.es/wms-inspire/hidrografia",
        layers = "HY.Network,HY.PhysicalWaters.Waterbodies",
        options = WMSTileOptions(format = "image/png", transparent = TRUE),
        attribution = "© IGN", group = "Hidrografia"
      ) |> 
      # Contour lines are 50 m apart. 
      # They only show when you're zoomed in close
      addWMSTiles(
        "https://servicios.idee.es/wms-inspire/mdt",
        layers = "EL.ContourLine",
        options = WMSTileOptions(format = "image/png", transparent = TRUE),
        attribution = "© IGN", group = "Curvas de nivel"
      ) |>
      ############
      # Layers control
      ############
      addLayersControl(
        baseGroups = c("Satelite", "Mapa Topografico"),
        overlayGroups = c("Parcelas catastro", "Hidrografia", "Curvas de nivel"),
        options = layersControlOptions(collapsed = FALSE)
      ) |> 
      hideGroup(c("Parcelas catastro", "Hidrografia", "Curvas de nivel"))
  )
}

shinyApp(ui, server)
