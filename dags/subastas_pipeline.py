"""
Weekly DAG that loads the auctions published in the BOE.

================================================================================
Architecture
================================================================================
The DAG follows a medallion architecture:

- Bronze: Loads the raw announcements published in the BOE API over the past 7 days.
          The BOE API is the only raw source of the pipeline.
- Silver: Reads bronze, finds the new announcements by looking at which boe_refs aren't
          in silver yet, and loads only those after cleaning and enriching them.
          The enrichment comes from other APIs (Claude, Goolzoom). Their data isn't considered
          bronze, since these APIs can only be called using data that is already in bronze.
          Modeled in 3NF (except for province, which is kept as a plain attribute of
          municipios instead of having its own table).
- Gold: Reloads all of silver on every run.
        Dimensional model: a star schema, with the addition of a junction table between
        fact_lots and dim_catastral_references, since a lot can contain several references.

================================================================================
Scheduling
================================================================================
Unlike cgm-analytics, which runs hourly, this pipeline only runs once per week.
To avoid having the Airflow containers of this project taking up memory all the time,
an external cron job starts them (astro dev start) and stops them (astro dev stop).
The cron job only activates the containers when they are needed: it starts them on Monday
morning and stops them 2 hours later. It doesn't trigger the DAG itself.
So scheduling has two layers: the cron jobs and Airflow.

The DAG is scheduled at Monday 00:00 UTC on purpose, so that it always comes before the cron job.
When the containers start, Airflow sees the run it missed and starts it right away (catchup=True).
This is safer than scheduling it inside the cron window: cron runs on local time and Airflow on
UTC, so the two would have to be kept in sync. This way, changing the time of the cron job
or the clocks changing doesn't require any change in the DAG.

- start_date: The earliest date Airflow can schedule a run, so it never creates one before it.
              It doesn't trigger a run by itself: the first run is the first scheduled time
              on or after start_date.
- catchup=True: Airflow creates a run for every scheduled time since start_date that doesn't
                have a run yet. It's needed because Airflow is off at Monday 00:00 UTC.
                A run that failed already exists, so it isn't repeated: clear it in the UI to
                rerun it.

An old start_date with catchup=True creates one run per week since that date. Each run fetches
its own week from the BOE and sends the new announcements to Claude, so it costs API credits.

================================================================================
Monitoring
================================================================================
With two layers, there is more that can go wrong, so the pipeline relies on
healthchecks.io and follows the logic of "no news is bad news". We receive an email, and can
decide how to solve the problem, in two cases:
- The pipeline fails: A task that fails for good (on its last retry, or right away when it has no retries)
  pings /fail, and the email is immediate.
- The pipeline doesn't even execute (computer off, cron job not firing...): No ping arrives, and
  the email comes on Tuesday around 10:30 local. The check expects a ping on the same schedule as
  the cron job (Mondays at 10:30 local), plus 1 day of grace.
"""

import os
from datetime import timedelta

import requests
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import dag, task, task_group
from airflow.sdk.exceptions import AirflowFailException
from pendulum import datetime

from subastas_analytics.clients.boe import (
    fetch_announcement_xml,
    fetch_auction_candidates,
    parse_auction,
)
from subastas_analytics.clients.llm import is_auction_title
from subastas_analytics.config import SQL_DIR
from subastas_analytics.loaders.bronze import insert_auctions, stored_boe_refs
from subastas_analytics.loaders.silver import load_silver


def _ping_failure(context):
    """
    Alerts you right away. It also stops a failed catchup run from being hidden when another run succeeds in the same window.
    """
    requests.get(f"{os.environ['HEALTHCHECK_URL']}/fail", timeout = 10)


def _week_candidates(monday) -> list[tuple[str, str, str]]:
    """Return the (boe_ref, title, url_xml) candidates of the 7 days before `monday`. Only calls the BOE, so it's free."""
    candidates = []
    for days_back in range(7, 0, -1):
        candidates += fetch_auction_candidates(monday - timedelta(days=days_back))
    return candidates


@dag(
    schedule="0 0 * * 1",   # Mondays at 00:00 UTC
    # Earliest date the DAG can have a scheduled run. Airflow doesnt schedule anything before it
    start_date=datetime(2026, 10, 25),
    # Creates a run for every scheduled time since start_date that hasn't run yet
    catchup=True,
    # One run at a time: two runs in silver would select the same pending announcements and pay Claude twice (S15)
    max_active_runs=1,
    default_args={
    "retries": 3,
    "retry_delay": timedelta(minutes=2),          # first wait
    "retry_exponential_backoff": True,            # double the wait each time
    "max_retry_delay": timedelta(minutes=30),     # upper limit for any single wait,
    "on_failure_callback": _ping_failure,         # Called only when the task fails for good (after its last retry, or right away with AirflowFailException)
    },
    tags=["subastas"],
    # Makes sure the DAG starts unpaused when Airflow first registers it, so it can run without you clicking anything in the UI.
    is_paused_upon_creation=False,
    # Folder where Airflow looks for .sql files
    template_searchpath=str(SQL_DIR)
    
)
def subastas_pipeline():

    # A task group is a way to group tasks together in the UI. It doesn't affect execution order, but it makes the DAG easier to read.
    @task_group
    def bronze():
        create_table = SQLExecuteQueryOperator(
            task_id="create_table",
            conn_id="subastas_db",
            sql="create_bronze_auctions.sql"
        )

        @task
        def fetch_auctions(logical_date=None) -> list[dict]:
            """
            Downloads the raw XML of all the auctions published in the 7 days before the run's Monday.
            Returns a list of {"url", "xml"}: parse_auctions parses them.

            Every BOE call comes before any Claude call, so if the BOE fails,
            the retry doesn't pay Claude again for titles it already classified.

            Parameters:
            - logical_date: We never pass logical_date. 
                            When Airflow runs a task, it looks at the functions parameter names,
                            and if one matches a value it knows about, it passes that value in.
                            logical_date = this run's date
            """
            monday = logical_date.date()

            # 1. BOE: summaries of the 7 days (free)
            candidates = _week_candidates(monday)

            # A week with 0 candidates is common (about 1 in 7), but 2 in a row suggests AUCTION_TITLE_RE
            # no longer matches (the ministry was renamed, the wording changed...).
            # Without this check, every run would succeed with 0 auctions and no one would notice.
            # 2 weeks gives 1 or 2 false alarms a year (August), accepted on purpose: some auctions give only
            # ~3 weeks to present offers, so a higher threshold would alert too late.
            # See "Why B17 alerts after 2 weeks" in docs/6.failure_modes.md.
            # AirflowFailException fails the task without retries (they would give the same result),
            # so on_failure_callback pings /fail right away.
            if not candidates and not _week_candidates(monday - timedelta(days=7)):
                raise AirflowFailException(
                    "No auction candidates in the BOE for 2 weeks in a row. Check that AUCTION_TITLE_RE "
                    "still matches the titles: look for NEAR MISS lines in this log, or search the BOE."
                )

            # B19: a single week with 0 candidates is common (about 1 in 7), and the week before had some,
            # so it isn't an alert. Return early: there is nothing to check in bronze or send to Claude.
            if not candidates:
                print(
                    f"No auction candidates in the BOE in the 7 days before {monday}. "
                    "The week before had some, so no alert (B17 only alerts after 2 empty weeks in a row)."
                )
                return []

            # Skip the candidates already in bronze, so a rerun of this week doesn't download them
            # or pay Claude again for them. It comes after the B17 check on purpose: a rerun of a week
            # whose auctions are all stored would otherwise look like 0 candidates and alert.
            # Titles Claude rejected (B6) aren't stored, so a rerun still asks about those.
            # It compares by boe_ref, the same key as the ON CONFLICT of the insert. ON CONFLICT stays:
            # this check only avoids the cost, the constraint ON CONFLICT is what guarantees no duplicates (B14)
            conn = PostgresHook(postgres_conn_id="subastas_db").get_conn()
            try:
                stored = stored_boe_refs(conn, [boe_ref for boe_ref, _, _ in candidates])
            finally:
                conn.close()
            for boe_ref, title, _ in candidates:
                if boe_ref in stored:
                    print(f"Already in bronze.auctions, skipped (probably a rerun of this week): {boe_ref} | {title}")
            new_candidates = [(title, url) for boe_ref, title, url in candidates if boe_ref not in stored]

            # 2. BOE: raw XML of every new candidate (free, a few are discarded later)
            downloaded = [(title, url, fetch_announcement_xml(url)) for title, url in new_candidates]

            # 3. Claude: keep only the real auctions.
            # The XML is returned as text because XCom stores the return value as JSON, and bytes aren't JSON
            accepted = [
                {"url": url, "xml": xml.decode("utf-8")}
                for title, url, xml in downloaded
                if is_auction_title(title)
            ]

            rejected = len(new_candidates) - len(accepted)
            print(
                f"{len(candidates)} titles passed the regexes, {len(stored)} of them already in bronze. "
                f"Of the {len(new_candidates)} new ones, Claude confirmed {len(accepted)} as auctions "
                f"and rejected {rejected} (see the NOT AN AUCTION lines)"
            )
            return accepted

        # Parsing is its own task, and only runs on the titles Claude confirmed as auctions,
        # so a malformed announcement that isn't an auction never fails the week.
        # If it fails (no boe_ref, no text...), fetch_auctions already succeeded and its XCom is stored,
        # so Claude isn't called again, neither on a retry nor when the run is cleared with "Only failed".
        # retries=0: a parse error gives the same result on every attempt, so it alerts right away
        # An empty week (B19) needs no check: an empty list parses to [] and succeeds in a moment
        @task(retries=0)
        def parse_auctions(accepted: list[dict]) -> list[dict]:
            auctions = [parse_auction(a["xml"].encode("utf-8"), a["url"]) for a in accepted]
            print(f"Parsed {len(auctions)} auctions")
            return auctions

        # An empty week (B19) needs no check: the insert loop doesn't run, and the task succeeds with 0 inserted
        @task
        def load_auctions(auctions: list[dict]) -> int:
            conn = PostgresHook(postgres_conn_id="subastas_db").get_conn()
            try:
                inserted = insert_auctions(conn, auctions)
            finally:
                conn.close()
            print(f"Inserted {inserted}, skipped {len(auctions) - inserted}")
            return inserted

        # Passing a task's return value to another task already sets the order: fetch >> parse >> load.
        # create_table passes no data, so its order is set by hand. 
        accepted = fetch_auctions()
        load_auctions(parse_auctions(accepted))
        create_table >> accepted

    @task_group
    def silver():
        create_tables = SQLExecuteQueryOperator(
            task_id="create_tables",
            conn_id="subastas_db",
            sql="create_silver.sql"
        )

        @task
        def transform_auctions() -> None:
            """Loads every announcement in bronze that isn't in silver yet."""
            conn = PostgresHook(postgres_conn_id="subastas_db").get_conn()
            try:
                result = load_silver(conn)
            finally:
                conn.close()

            print(f"Loaded {len(result['loaded'])}, failed {len(result['failed'])}")
            # Fail the task so the problem shows in the UI and alerts you.
            # AirflowFailException fails it without retries, so on_failure_callback pings /fail right away.
            # A retry wouldn't help: the failed ones are already recorded in failed_announcements, so it
            # wouldn't find them pending. It would succeed, and the alert would never be sent
            if result["failed"]:
                raise AirflowFailException(f"Announcements that failed: {result['failed']}")

        create_tables >> transform_auctions()

    @task_group
    def gold():
        create_tables = SQLExecuteQueryOperator(
            task_id="create_tables",
            conn_id="subastas_db",
            sql="create_gold.sql"
        )

        load_tables = SQLExecuteQueryOperator(
            task_id="load_tables",
            conn_id="subastas_db",
            sql="load_gold.sql"
        )

        create_tables >> load_tables

    @task
    def ping_success():
        requests.get(os.environ["HEALTHCHECK_URL"], timeout = 10).raise_for_status()

    bronze() >> silver() >> gold() >> ping_success()

subastas_pipeline()