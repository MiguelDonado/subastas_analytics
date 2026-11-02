# Session notes: subastas_analytics

## Done
- **BOE parsing:** fixed `boe.py` so it reads `identificador` and `fecha_publicacion` from inside `<metadatos>`. `publication_date` is now returned as an ISO string.
- **Astro:** set up the project with the Airflow UI on port 8081 and its metadata Postgres on 5434. Removed the unrelated `astro` package that had been installed with uv.
- **Data database:** `subastas-db` is defined in `docker-compose.override.yml`, on `localhost:5435`.
- **DAG:** `dags/subastas_pipeline.py` runs `create_table`, then `fetch_auctions`, then `load_auctions`. The SQL is in `include/sql/`.
- **Scheduling:** a cron job runs `scripts/weekly_airflow.sh` on Mondays at 10:30. It starts Airflow, waits two hours and stops it, and logs to `logs/weekly_airflow.log`.
- **Docs:** added `docs/airflow.md`.
- **First load:** `bronze.auctions` has 9 rows, published between October 1 and October 22.

## Decisions
| Decision | Why |
|---|---|
| Run Airflow only during a weekly window | Saves RAM (about 1.1 GiB) the rest of the week |
| Schedule the DAG for Mondays at 00:00 UTC with `catchup=True` | Airflow is off at that time, so catchup creates the run when it starts |
| Load the previous Monday to Sunday in each run | Weeks have no gaps or overlaps |
| Keep cron rather than a systemd timer | Simpler, and a missed week is caught up the following Monday |
| Keep `subastas-db` in the Astro project | Same setup as `cgm-analytics`, though the database stops with Airflow |
| Use one DAG for all layers | The layers always run in order, on the same schedule |
| Use `ON CONFLICT DO NOTHING` | Re-runs can't create duplicates, and bronze rows stay as first received |

## Problems found
- **API key in git:** `.env.bak` was committed because of a backup step. There was no remote, and the decision was to recreate the repo.
- **`%` in SQL comments:** the driver reads placeholders inside comments too, which caused `positional and named placeholders cannot be mixed`. Keep `%` out of comments in query files.

## Still to do
1. **Check today's run:** see `logs/weekly_airflow.log` and the Airflow UI, and look for rows published after October 22.
2. **Test a re-run:** clear a finished run and check that its log says `Inserted 0`.
3. **Add the DAG setting:** `is_paused_upon_creation=False` was still missing from the DAG when last checked.
4. **Check git before committing:** make sure `.env`, `.env.bak` and `subastas-db.env` aren't tracked.
5. **Spot-check the data:** compare a few rows with the BOE announcements.
6. **Build silver:** add LLM extraction and Catastro enrichment, then add task groups to the DAG.
7. **Plan for the Shiny app:** it will need the database running outside the weekly window.

## Things to watch
- **Time limit:** silver could take longer than the two-hour window and get cut off.
- **Deleting data:** `astro dev kill` will most likely delete the database volume.
- **Failure alerts:** nothing notifies you when a run fails, so check the log and the UI.