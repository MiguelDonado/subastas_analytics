# Installing the systemd timer

## Install

These need your sudo password, so run them in your own terminal, from the project folder:

```bash
sudo cp systemd/subastas-airflow.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now subastas-airflow.timer
systemctl list-timers subastas-airflow.timer
```

The last command should show the next run as the next Monday at 10:30.

If the old cron job is still there, remove it and its comment:

```bash
crontab -e
```

Enabling the timer doesn't start a run, so nothing happens until the next Monday at 10:30.

## Test the start and stop

```bash
sudo systemctl start --no-block subastas-airflow.service
```

Wait about 3 minutes, because of the 2-minute delay, then check the following:

1. `docker ps` shows the containers are up.
2. `sudo systemctl stop subastas-airflow.service` removes them from `docker ps`.
3. `journalctl -u subastas-airflow.service` shows the output.
