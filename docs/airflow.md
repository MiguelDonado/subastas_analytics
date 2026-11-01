# Airflow orchestration

How the pipeline is scheduled with Airflow (run through the Astro CLI), and why Airflow is only running for about two hours a week.

## Why Airflow only runs once a week

BOE data only needs loading once a week, so keeping Airflow running all the time would use RAM for nothing. This project's Airflow containers use about 1.1 GiB when running, on a laptop with 15 GiB that also runs `cgm-analytics`, which has to stay on because it fetches data hourly.

So a cron job starts Airflow every Monday, gives it two hours to finish, and stops it again. Stopping the containers frees their RAM, and the data stays in Docker volumes.

## Weekly flow

| When | What happens |
|---|---|
| Monday 00:00 UTC | The DAG's scheduled time passes. Airflow is off, so nothing runs yet. |
| Monday 10:30 local | Cron runs `scripts/weekly_airflow.sh`, which starts Airflow. |
| Right after the start | Airflow sees the missed Monday and starts that run (`catchup=True`). |
| Monday 12:30 local | The script stops Airflow. |

## Cron job

Installed with `crontab -e`:

```cron
30 10 * * 1 /home/miguel/6.Projects/subastas_analytics/scripts/weekly_airflow.sh >> /home/miguel/6.Projects/subastas_analytics/logs/weekly_airflow.log 2>&1
```

- **Schedule:** every Monday at 10:30, in the laptop's local time.
- **Logs:** the script's output and errors go to `logs/weekly_airflow.log`. The `logs/` folder is gitignored, but has to exist for the job to write there.
- **`PATH`:** cron's default `PATH` doesn't include `/usr/local/bin`, where `astro` is installed, so the script sets it explicitly.

## Ports

Set in `.astro/config.yaml`, because `cgm-analytics` already uses 8080, 5432 and 5433:

| Service | Port |
|---|---|
| Airflow UI | 8081 |
| Airflow metadata Postgres | 5434 |

`subastas-db` is exposed on `localhost:5435`, set in `docker-compose.override.yml`. This mapping is for tools on the laptop, such as `dbeaver`.

## Where the data lives

The project's data is in its own Postgres container, `subastas-db`, defined in `docker-compose.override.yml` and separate from the Postgres that stores Airflow's metadata. Airflow reaches it through the `subastas_db` connection, at `subastas-db:5432` on the Docker network.

## Known limitations

- **Laptop off or asleep at 10:30 on Monday:** cron skips that week and doesn't run it later. The next Monday's start catches up on both weeks, so the data arrives a week late but nothing is lost. This trade-off was accepted to keep cron instead of a systemd timer with `Persistent=true`.