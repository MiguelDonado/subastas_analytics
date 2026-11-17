- Nice to have: e2e tests, and switching to an open-source LLM to cut costs.
- Optimize app so that it works faster in connect.posit.cloud
- write readme
- record videos
- Leer este informe sobre los bosques de Galicia. /home/miguel/6.Projects/subastas_analytics/assets/reports/Publicación_IFN4_Galicia.pdf
- Anotar todo lo que vi con claude sobre el data analysis y sitios en los que podia obtener precios de referencia con los que comparar., ver assets/reports y anotar esto sobre el valor de referencia - It starts from an average value per crop or land-use group (módulo de valor medio). That covers all rustic uses, not only farmland, so it should include forest land too.
- That average is then adjusted for location, agronomic and socioeconomic factors. This partly answers your point that a lot near the village is worth more than one in the middle of nowhere.
- It's based on real sale prices reported by notaries.
- Right now i can say geospatial visualization, but i cannot say gis. To make it gis it would have to include spatial analysis, like distance to nearest village...
- Make an applicaiton in the future and an API that allows to query database.

## Additions for a data analysis part
Right now the project doesn't include a data analysis part. The app shows the lots and lets me filter them and mark a decision, but it doesn't draw conclusions on its own: no summaries, trends, comparisons or models. I do the analysis myself while using it.

- Market price benchmark: compare each lot's €/m² with the Ministry of Agriculture's average land price for its province and crop type (Encuesta de Precios de la Tierra).
- Compare with similar lots: percentile of €/m² among lots with the same province, use and crop type. Only useful once location is included too (for example distance to the nearest village), otherwise a well-located lot looks expensive.
- Where and when: number of lots and €/m² by province and month, to see where the supply is and which areas are cheaper.
- Learn from my reviews: compare the lots marked Interesado with the Descartado ones, and later a model that flags lots I would probably like.
- Final price: check if the BOE publishes the winning bid. If it does, store it and predict the final price of new lots.
