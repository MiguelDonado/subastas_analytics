#!/usr/bin/bash
# cron has a minimal PATH, so set it explicitly
export PATH=/usr/local/bin:/usr/bin:/bin

# exit 1: stops the script
cd /home/miguel/6.Projects/subastas_analytics || exit 1

astro dev start --no-browser || exit 1   # start Airflow
sleep 7200                               # give it 2 hours to finish
astro dev stop                           # free the RAM until next week