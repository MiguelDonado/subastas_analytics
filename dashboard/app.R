library(shiny)
library(leaflet)
library(bslib)
library(DT)
library(dplyr)


# Santiago de Compostela (initial default view)
lng = -8.5448
lat = 42.8782
zoom = 13

# Lots
con <- connect_subastas_db()
lots <- read_lots(con) |>
  mutate(
    municipio = tools::toTitleCase(tolower(municipio)),
    price_per_m2 = starting_price / total_surface
  ) 
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
  output$lots <- renderDT(
    lots |>
      mutate(
        qualification = coalesce(qualification, "-"),
        announcement_url = paste0('<a href="', announcement_url, '" target="_blank">BOE</a>')
      ) |>
      select(
        total_surface, 
        starting_price, 
        municipio, 
        province, 
        class, 
        qualification, 
        use, 
        price_per_m2,
        reference_count,
        publication_date, 
        held_date, 
        lot_number, 
        announcement_url
      ) |> 
      datatable(
        colnames = c(
        "Superficie (m²)"       = "total_surface",
        "Precio salida"         = "starting_price",
        "Municipio"             = "municipio",
        "Provincia"             = "province",
        "Clase"                 = "class",
        "Cultivo"               = "qualification",
        "Uso"                   = "use",
        "€/m²"                  = "price_per_m2",
        "Inmuebles"             = "reference_count",
        "Publicacion"           = "publication_date",
        "Celebracion"           = "held_date",
        "Nº lote"               = "lot_number",
        "Anuncio"               = "announcement_url"
      ),
      escape = FALSE # show the link as HTML
    ) |>
      formatCurrency("Precio salida", currency = " €", 
                     before = FALSE, mark = ".", dec.mark = ",", 
                     digits = 0) |> 
      formatRound("Superficie (m²)", digits = 0, mark = ".", dec.mark = ",") |>
      formatDate(c("Publicacion", "Celebracion"),
                 method = "toLocaleDateString", params = list("es-ES")) |> 
      formatCurrency("€/m²", currency = " €", before = FALSE,
                     mark = ".", dec.mark = ",", digits = 2)
  )
      
  output$map <- renderLeaflet(
    leaflet() |> 
      setView(lng = lng, lat = lat, zoom = zoom) |> 
      ############
      # Base group
      ############
      addTiles(
        urlTemplate = "https://www.ign.es/wmts/pnoa-ma?request=GetTile&service=WMTS&VERSION=1.0.0&Layer=OI.OrthoimageCoverage&Style=default&Format=image/jpeg&TileMatrixSet=GoogleMapsCompatible&TileMatrix={z}&TileRow={y}&TileCol={x}",
        attribution = "PNOA © IGN", group = "Mapa Satelite"
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
        baseGroups = c("Mapa Satelite", "Mapa Topografico"),
        overlayGroups = c("Parcelas catastro", "Hidrografia", "Curvas de nivel"),
        options = layersControlOptions(collapsed = FALSE)
      ) |> 
      hideGroup(c("Parcelas catastro", "Hidrografia", "Curvas de nivel"))
  )
}

shinyApp(ui, server)
