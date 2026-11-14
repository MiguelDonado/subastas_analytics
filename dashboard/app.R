library(shiny)
library(leaflet)
library(bslib)
library(DT)
library(dplyr)
library(stringr)
library(shinydisconnect)

# Lots
con <- connect_subastas_db()
lots <- read_lots(con) |>
  mutate(
    municipio = str_to_title(municipio)
  )
references <- read_lot_references(con)
dbDisconnect(con)

ui <- page_sidebar(
  disconnectMessage(
    text = "Se ha perdido la conexión con el servidor.",
    refresh = "Recargar"
  ),
  #title = "Subastas Analytics",
  window_title = "Subastas Analytics",  # name of the browser tab, since there's no title bar
  padding = "0.25rem",  # less space around the map and the table
  gap = "0.25rem",      # less space between the map and the table
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
    row_heights = c(2, 2), # 50% / 50%
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
  
  ####################
  ####################
  # TABLE
  ####################
  ####################
  
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
      escape = FALSE, # show the link as HTML
      selection = "single",  # Select only one row at a time
      options = list(
        pageLength = 5,      # 5 rows per page, so the table fits without scrolling
        lengthChange = FALSE # hide the "Show 5 entries" dropdown
      )
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
  
  ####################
  ####################
  # MAP (STATIC)
  ####################
  ####################
  
  # The parts of the map that never change go in leaflet()
  # No markers here: filtered_lots also runs at startup (ignoreNULL = FALSE),
  # so the observe below draws the first markers as soon as the app opens
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
  
  ####################
  ####################
  # MAP (DYNAMIC): Draw markers for all filtered lots in the table and zoom
  ####################
  ####################
  
  ## Points of the filtered lots: one per catastral reference
  filtered_points <- reactive(
    references |> semi_join(filtered_lots(), by = "lot_id")
  )
  
  # Changes to the map that's already drawn go through leafletProxy()
  observe({
    # As a variable cuz its used 3 times, and is clearer than calling filtered_points() each time
    points <- filtered_points()
    
    # Replace the markers
    leafletProxy("map", data=points) |> 
      clearMarkers() |> 
      # layerId: id of the marker, the catastral reference because ids must be unique
      addCircleMarkers(layerId = ~catastral_reference)    # Rather than pins cuz changing their color is easy
    
    # Zoom to the results; with no results, leave the map where it is
    # leafletProxy("map") doesn't create anything, it just sends these commands to the map called "map"
    if (nrow(points) > 0) {
      leafletProxy("map") |>
        fitBounds(min(points$longitude), min(points$latitude),
                  max(points$longitude), max(points$latitude))
    }
  })
  
  ####################
  ####################
  # Clicking a marker -> Select its row in the table
  ####################
  ####################
  
  observeEvent(input$map_marker_click, {
    points <- filtered_points()
    reference <- input$map_marker_click$id
    
    # Red markers (the selected lot) have no id: clicking one deselects the lot
    if (is.null(reference)) {
      dataTableProxy("lots") |> selectRows(NULL)
      return()
    }
    lot <- points$lot_id[points$catastral_reference == reference]
    
    # Position in filtered_lots, before any sorting or searching
    row <- which(filtered_lots()$lot_id == lot)
    
    # Position in the table as it's shown now (after sorting and searching)
    position <- which(input$lots_rows_all == row)
    
    # Sends commands to the table already drawn, without rebuilding it
    dataTableProxy("lots") |> selectRows(row)
    # Go to its page if the search box doesn't hide it
    if (length(position) > 0) {
      dataTableProxy("lots") |> selectPage(ceiling(position / 5))  # 5 = pageLength of the table
    }
  })
  
  ####################
  ####################
  # Selecting a row (by clicking it, or one of its markers) -> highlight and zoom to its markers
  ####################
  ####################
  
  # lots_rows_selected: holds the selected row's number (original table, not sorted)
  observeEvent(input$lots_rows_selected, {
    # Remove the previous highlight
    leafletProxy("map") |>  clearGroup("selected")
    
    row <- input$lots_rows_selected
    # If some row is selected
    if(!is.null(row)) {
      lot <- filtered_lots()$lot_id[row]
      points <- filtered_points() |> filter(lot_id == lot)
      
      # On top of the blue markers
      leafletProxy("map", data = points) |> 
        addCircleMarkers(
          color = "red",
          group = "selected",
        ) |> 
        fitBounds(min(points$longitude), min(points$latitude),
                 max(points$longitude), max(points$latitude))
    }
  }, 
  # Reaction is triggered even when lots_rows_selected is NULL
  # So when we deselect, the red markers are cleared, cuz clearGroup("selected") is executed.
  ignoreNULL = FALSE
  )  
  
}

shinyApp(ui, server)
