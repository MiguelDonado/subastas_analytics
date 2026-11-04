# Local environment

Where the logs and the data of the local Airflow setup (run through the Astro CLI) are, and which ports it uses. For how the pipeline is scheduled and monitored, see [scheduling-monitoring.md](scheduling-monitoring.md).

## Logs

`logging.getLogger(__name__)` doesn't create a log file. It only creates a logger named after the module, such as `subastas_analytics.loaders.silver`. When a task is running, Airflow writes that logger's messages, and anything sent with `print`, to the log of that task. So the `REJECTED` and `FAILED` messages from `load_silver` are in the log of the silver task that called it.

Each attempt of each task has its own file:

```
/usr/local/airflow/logs/dag_id=subastas_pipeline/run_id=<run>/task_id=<task>/attempt=<n>.log
```

- **Where to read them:** in the Airflow UI, open the run, click the task and go to its logs. There is one log per attempt, so a retry can repeat the same message.
- **Where they are stored:** in a Docker volume, not in the project's `logs/` folder, which only has `weekly_airflow.log`, the output of the cron script. `astro dev kill` will most likely delete that volume.

## Ports

Set in `.astro/config.yaml`, because `cgm-analytics` already uses 8080, 5432 and 5433:

| Service | Port |
|---|---|
| Airflow UI | 8081 |
| Airflow metadata Postgres | 5434 |

`subastas-db` is exposed on `localhost:5435`, set in `docker-compose.override.yml`. This mapping is for tools on the laptop, such as `dbeaver`.

## Where the data lives

The project's data is in its own Postgres container, `subastas-db`, defined in `docker-compose.override.yml` and separate from the Postgres that stores Airflow's metadata. Airflow reaches it through the `subastas_db` connection, at `subastas-db:5432` on the Docker network.