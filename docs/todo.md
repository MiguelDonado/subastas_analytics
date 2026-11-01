## TODO

You can, but I'd still build the loader first, at least bronze → silver on a sample of announcements.

The first step of the plan is now done: docs/app-design.md is effectively the list of questions gold has to answer. The reason to load data before designing gold still holds, though:

- Silver hasn't seen real data. The riskiest parts of the project haven't been tested yet: the LLM extraction from the announcement text and the Catastro API lookups.
- Real data could change silver. You might find lots with no catastral reference, references Catastro can't find, or announcements in odd formats. Any of these could change silver, and gold is built from silver.
- Gold design depends on the data. With real rows you can see how many lots have several references, how prices and surfaces are spread, and which uses and classes actually appear. That's what you need to choose the grain and dimensions of the star schema.

So the next steps would be:
1. Bronze loader: fetch the BOE daily summaries, filter for the Hacienda auctions and store them in bronze.auctions. Start with a few weeks of data, not the full history.
2. Silver loader: extract auctions, lots and properties with the LLM, enrich the catastral references with the Catastro API, and fill the municipios.
3. Check the results against a few announcements by hand.
4. Then gold: the star schema, plus the view the app reads from.

If you'd rather design gold now, I can do it. Just expect to adjust it once real data comes in. Which would you like to start with?

I'd write the loader first, at least bronze → silver on a sample of announcements.

1. Silver hasn't seen real data yet. The fields come from LLM extraction and the Catastro API, which are the riskiest parts of the project. Once you load real announcements you'll likely find surprises: lots with no price, announcements in odd formats, references Catastro doesn't return. Any of these could change silver.
2. Gold is built from silver. If you design the star schema now and silver changes later, you redo both. With silver checked against real data, gold sits on solid ground.
3. Real data makes the dimensional design easier. You'll see the actual values, volumes and how things are distributed. That helps you decide the grain of the fact table and which attributes belong in each dimension.

One thing worth doing now, because it costs little: write down the questions gold should answer, e.g. "average starting price per m² by province and year" or "number of lots by use and class". That shapes the star schema and can show you a field silver still needs before you build the loader.

So the order I'd suggest is: list the questions, then build the loader and run it on a sample, then design the gold star schema.

5. Test it once by hand: this takes the full hour, so run it when you can leave it going. This command also saves its output to the log:

~/6.Projects/subastas_analytics/scripts/weekly_airflow.sh >> ~/6.Projects/subastas_analytics/logs/weekly_airflow.log 2>&1

### Tips for the LLM layer
- Deduplication: Don't reprocess unchanged documents. 
- Structured output: Require responses that conform to your schema.
- Model versioning: Record which model and extraction instructions produced each result.
- Retry handling: Retry temporary API failures without duplicating records.

QUALITY CHECKS

# DAG design

**Status: planned.** `dags/` only contains Astro's example DAG so far, and the code below depends on `subastas_analytics.pipeline.ingest_day`, which doesn't exist yet.

```python
from datetime import datetime, timedelta

from airflow.sdk import dag, task

from subastas_analytics.pipeline import ingest_day


@dag(
    schedule="0 0 * * 1",  # Mondays at 00:00 UTC
    start_date=datetime(2026, 10, 5),
    catchup=True,
    is_paused_upon_creation=False,
)
def bronze_boe():
    @task
    def ingest(logical_date=None):
        monday = logical_date.date()
        for days_back in range(7, 0, -1):
            ingest_day(monday - timedelta(days=days_back))

    ingest()


bronze_boe()
```

- **Period covered:** each run loads the previous Monday to Sunday, so the weeks have no gaps or overlaps.
- **`schedule`:** it must stay earlier than the cron job. If it fell after Airflow had stopped, that run would wait until the next week.
- **`catchup=True`:** required, because Airflow is off at the scheduled time. It also recovers weeks missed entirely.
- **`is_paused_upon_creation=False`:** a paused DAG wouldn't run unattended.
- **Backfilling:** move `start_date` back to an earlier Monday.

## Code structure

The logic lives in the Python package, and the DAG only schedules it. This allows the load to be run and tested from `main.py` without Airflow.

```
src/subastas_analytics/
├── boe.py        # fetch and parse BOE announcements (done)
├── bronze.py     # insert into bronze.auctions (planned)
└── pipeline.py   # ingest_day(fecha) ties them together (planned)
dags/
└── bronze_boe.py # schedules ingest_day (planned)
```

Inserts use `ON CONFLICT (boe_ref) DO NOTHING`, so retries and reruns can't create duplicates.

The Astro image doesn't include `subastas_analytics` or its dependencies automatically, so the `Dockerfile` will have to install them. Airflow itself stays out of `pyproject.toml`.

- **Interrupted runs:** a run stopped midway may not rerun by itself. Clear it in the Airflow UI to rerun it, which is safe because of the `ON CONFLICT` insert.
- **Failed days:** one bad day fails the whole week's run, and a retry repeats all 7 days.
- **Silent failures:** nothing sends an alert when a run fails, so check `logs/weekly_airflow.log` and the Airflow UI.




## Possible future improvements.

## Data modelling

- [ ] **Later-round starting prices.** Announcements can offer each lot in up to four rounds (1ª–4ª subasta), each with a lower starting price ("tipo de licitación"). For example, lot 1 of BOE-B-2026-34259 lists 5.271,11 € / 4.481 € / 3.809 € / 3.238 €. Today only the 1st-round price is stored (`lots.starting_price`). To keep every round, add a child table `lot_rounds(lot_id FK, round_number, starting_price, PK(lot_id, round_number))`. This would allow analysing the discount between rounds.
