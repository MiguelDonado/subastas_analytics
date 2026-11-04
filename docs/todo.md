### Tips for the LLM layer
- Deduplication: Don't reprocess unchanged documents. 
- Model versioning: Record which model and extraction instructions produced each result.
- Retry handling: Retry temporary API failures without duplicating records.

Extract qualification as well in the future

- **Interrupted runs:** a run stopped midway may not rerun by itself. Clear it in the Airflow UI to rerun it, which is safe because of the `ON CONFLICT` insert.
- **Failed days:** one bad day fails the whole week's run, and a retry repeats all 7 days.

- I think it should look not only 7 days before in the dag timedelta, but 14 days before for redundancy, because dag runs once per week, and imaging one week doesnt run, if only looks 7 days behind i would lose data.


Because it's part of the Astro project, the database starts and stops with Airflow, so it's only available during the weekly run or when Airflow is started by hand. The data stays in the `subastas_db_data` volume while it's stopped, but `astro dev kill` will most likely delete that volume. The Shiny app will need the database running, so this has to be revisited when the app is built.


Ensure costs and failures are handled so I do not end up spending too much API credits.

workflow diagram

quality checks

logs very well


# Improvements
- [] Use systemd timer instead of cron. It has the advantage that if computer is off, it would trigger the script whenever computer starts, whereas cron doesnt. If computer off, during cron schedule, cron job would not be executed.