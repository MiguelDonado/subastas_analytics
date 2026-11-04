#!/usr/bin/bash
# Starts the Airflow containers of this project, gives the weekly run time to finish, and stops them.
#
# Unlike cgm-analytics, which runs hourly, this pipeline only runs once per week. To avoid having
# the containers taking up memory all the time, a cron job runs this script on Monday mornings,
# so they are only active when they are needed.
#
# This script doesn't trigger the DAG. The DAG is scheduled at Monday 00:00 UTC, so that it always
# comes before the cron job. When the containers start, Airflow sees the run it missed and starts it
# right away (catchup=True). This way, changing the time of the cron job doesn't require any change
# in the DAG.

# Add a timestamp to each line of output, including errors
exec > >(while IFS= read -r line; do printf '%(%F %T %z)T %s\n' -1 "$line"; done) 2>&1

# PATH is the list of folders where the shell looks for commands.
# cron doesn't load the terminal's configuration (~/.bashrc...), so it uses a minimal PATH,
# usually just /usr/bin:/bin. astro is in /usr/local/bin, so without this line the job would
# fail with "astro: command not found", even if the script works when run from a terminal.
export PATH=/usr/local/bin:/usr/bin:/bin

# exit 1: stops the script
cd /home/miguel/6.Projects/subastas_analytics || exit 1

astro dev start --no-browser || exit 1   # start Airflow
sleep 7200                               # give it 2 hours to finish
astro dev stop                           # free the RAM until next week