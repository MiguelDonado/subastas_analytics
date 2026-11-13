library(shiny)
library(leaflet)
library(bslib)
library(DT)
library(dplyr)
library(stringr)


# Santiago de Compostela (initial default view)
# lng = -8.5448
# lat = 42.8782
# zoom = 13

# Lots
con <- connect_subastas_db()
lots <- read_lots(con) |>
  mutate(
    municipio = str_to_title(municipio)
  )
references <- read_lot_references(con)
dbDisconnect(con)

ui <- page_sidebar(
  title = "Subastas Analytics",
  # Filters: an empty filter lets every lot through
  sidebar = sidebar(
    open = "always",
    selectizeInput(
      "province", 
      "Provincia", 
      sort(unique(lots$province)), 
      multiple = TRUE,
      options = list(placeholder = "Todas", plugins = list("remove_button"))
    ),
    numericInput("price_max", "Precio máximo (€)", NA),
    numericInput("surface_min", "Superficie mínima (m²)", NA),
    input_switch("only_upcoming", "Solo subastas activas", value=TRUE),
    actionButton("update", "Buscar")
  ),
  layout_columns(
    col_widths = 12,
    row_heights = c(3, 2), # 60% / 40%
    card(leafletOutput("map"), full_screen = TRUE),
    card(DTOutput("lots"), full_screen = TRUE, class = "small") # small text
  )
)

server <- function(input, output, session) {
  # Lots that match the filters
  filtered_lots <- eventReactive(input$update, {
    lots |>
      filter(
        # First part of each line checks whether you left that filter empty
        # If you did the line is true for every lot, so it doesnt remove anything
        is.null(input$province)  | province %in% input$province,
        is.na(input$price_max)   | starting_price <= input$price_max,
        is.na(input$surface_min) | total_surface >= input$surface_min,
        
        # If switch is off -> First part is TRUE, so it doesnt apply any filter
        # filter(TRUE): Returns all rows
        !input$only_upcoming     | offer_deadline >= Sys.Date()
      )
  }, ignoreNULL = FALSE)

  output$lots <- renderDT(
    filtered_lots() |>
      mutate(
        qualification = coalesce(qualification, "-"),
        announcement_url = paste0('<a href="', announcement_url, '" target="_blank">', boe_ref, '</a>')
      ) |>
      select(
        offer_deadline,
        province,
        municipio,
        starting_price,
        total_surface,
        price_per_m2,
        class,
        use,
        qualification,
        reference_count,
        lot_number,
        announcement_url
      ) |>
      datatable(
        colnames = c(
        "Plazo ofertas"         = "offer_deadline",
        "Provincia"             = "province",
        "Municipio"             = "municipio",
        "Precio salida"         = "starting_price",
        "Superficie (m²)"       = "total_surface",
        "€/m²"                  = "price_per_m2",
        "Clase"                 = "class",
        "Uso"                   = "use",
        "Cultivo"               = "qualification",
        "Inmuebles"             = "reference_count",
        "Nº lote"               = "lot_number",
        "Anuncio"               = "announcement_url"
      ),
      escape = FALSE # show the link as HTML
    ) |>
      formatCurrency("Precio salida", currency = " €", 
                     before = FALSE, mark = ".", dec.mark = ",", 
                     digits = 0) |> 
      formatRound("Superficie (m²)", digits = 0, mark = ".", dec.mark = ",") |>
      formatDate("Plazo ofertas",
                 method = "toLocaleDateString", params = list("es-ES")) |> 
      formatCurrency("€/m²", currency = " €", before = FALSE,
                     mark = ".", dec.mark = ",", digits = 2)
  )
  
  # Static aspects goes with leaflet()
  output$map <- renderLeaflet(
    leaflet() |> 
      ############
      # Base group
      ############
      addTiles(
        urlTemplate = "https://www.ign.es/wmts/pnoa-ma?request=GetTile&service=WMTS&VERSION=1.0.0&Layer=OI.OrthoimageCoverage&Style=default&Format=image/jpeg&TileMatrixSet=GoogleMapsCompatible&TileMatrix={z}&TileRow={y}&TileCol={x}",
        attribution = "PNOA © IGN", group = "Mapa Satelite"
      ) |>
      addTiles(
        urlTemplate = "https://www.ign.es/wmts/ign-base?request=GetTile&service=WMTS&VERSION=1.0.0&Layer=IGNBaseOrto&Style=default&Format=image/png&TileMatrixSet=GoogleMapsCompatible&TileMatrix={z}&TileRow={y}&TileCol={x}",
        attribution = "© IGN", group = "Mapa Satelite"
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
  
  ## Points of the filtered lots: one per catastral reference
  
  filtered_points <- reactive(
    references |> semi_join(filtered_lots(), by = "lot_id")
  )
  
  # Dynamic aspects or updates that is needed should go along leafletProxy()
  observe({
    # As a variable cuz its used 3 times, and is clearer than calling filtered_points() each time
    points <- filtered_points()
    
    # Replace the markers
    leafletProxy("map", data=points) |> 
      clearMarkers() |> 
      addCircleMarkers()    # Rather than pins cuz changing their color is easy
    
    # Zoom to the results; with no results, leave the map where it is
    if (nrow(points) > 0) {
      leafletProxy("map") |>
        fitBounds(min(points$longitude), min(points$latitude),
                  max(points$longitude), max(points$latitude))
    }
  })
}

shinyApp(ui, server)
