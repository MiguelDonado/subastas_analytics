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

## Failure alerts

[healthchecks.io](https://healthchecks.io) emails me when the weekly run fails or doesn't finish on time. Its check waits for a ping from the DAG, so it also notices when Airflow never ran. An email sent by Airflow couldn't cover that, because Airflow has to be running to send it.

The DAG sends two pings:

- **Success:** `ping_success` is the last task and only runs if bronze and silver both succeeded.
- **Failure:** `_ping_failure` calls the `/fail` URL when a task fails on its last retry. A failure that a retry fixes sends no alert.

| What happens | Result |
|---|---|
| The run succeeds | Success ping, no email |
| A task fails on its last retry | `/fail` ping, immediate email |
| The laptop is off, or Airflow doesn't start | No ping, email when the grace time ends |
| The script stops Airflow at 12:30 before the run finishes | No ping, email when the grace time ends |

The check is set up on healthchecks.io with these values:

- **Period: 7 days.** How often a ping is expected. It restarts from each success ping.
- **Grace time: 1 day.** How long to wait after the period before alerting. A run that never happened is flagged about a day later.

A new check only starts counting after its first ping. The `/fail` ping ignores both values. If one run fails and another succeeds in the same window, the check ends up as OK, but the `/fail` email has already been sent.

The URL goes in `.env` as `HEALTHCHECK_URL`, and `astro dev restart` is needed after changing it. Anyone with the URL can send pings, so it stays out of git. It can't be used to read any data, and it can be replaced from the healthchecks.io dashboard if it leaks.

The email only says that something went wrong, so the cause has to be found in the Airflow UI. `REJECTED` references don't fail the run, so they send no alert and only appear in the task log.

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

## Known limitations

- **Laptop off or asleep at 10:30 on Monday:** cron skips that week and doesn't run it later. The next Monday's start catches up on both weeks, so the data arrives a week late but nothing is lost. This trade-off was accepted to keep cron instead of a systemd timer with `Persistent=true`.