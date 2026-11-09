## Extraction source
**BOE Open Data API**
**GoolZoom API**
**Claude API**

## Tech stack
Airflow
Systemd timers
Job Monitoring (Healtchecks.io)
UV
APIs and SDK
GenAI (Messages API Claude)




Data Modeling


## LLM layer
- This is a GenAI application because it makes API calls to an LLM. It sends the full announcement text and the instructions, and gets back the extracted data.
- Define a structured output schema: You want predictable, structured data that your database can consume. 
    


## Ports

Set in `.astro/config.yaml`, because `cgm-analytics` already uses 8080, 5432 and 5433:

| Service | Port |
|---|---|
| Airflow UI | 8081 |
| Airflow metadata Postgres | 5434 |

`subastas-db` is exposed on `localhost:5435`, set in `docker-compose.override.yml`. This mapping is for tools on the laptop, such as `dbeaver`.