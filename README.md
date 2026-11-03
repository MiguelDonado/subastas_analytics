## Extraction source
**BOE Open Data API**
**GoolZoom API**

## Tech stack
Airflow
UV
Claude API (messages API)
Data Modeling
API calls
Cron job monitoring (healthchecks.io)

## LLM layer
- This is a GenAI application because it makes API calls to an LLM. It sends the full announcement text and the instructions, and gets back the extracted data.
- Define a structured output schema: You want predictable, structured data that your database can consume. 
    

