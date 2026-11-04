import os
from datetime import timedelta

import requests
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import dag, task, task_group
from pendulum import datetime

from subastas_analytics.clients.boe import fetch_auction, fetch_auction_urls
from subastas_analytics.config import SQL_DIR
from subastas_analytics.loaders.bronze import insert_auctions
from subastas_analytics.loaders.silver import load_silver


def _ping_failure(context):
    """
    Alerts you right away. It also stops a failed catchup run from being hidden when another run succeeds in the same window.
    """
    requests.get(f"{os.environ['HEALTHCHECK_URL']}/fail", timeout = 10)


@dag(
    schedule="0 0 * * 1",   # Mondays at 00:00 UTC
    # Earliest date the DAG can have a scheduled run. Airflow doesnt schedule anything before it
    start_date=datetime(2026, 10, 25),
    # Creates a run for every scheduled time since start_date that hasn't run yet
    catchup=True,
    default_args={
    "retries": 3,
    "retry_delay": timedelta(minutes=2),          # first wait
    "retry_exponential_backoff": True,            # double the wait each time
    "max_retry_delay": timedelta(minutes=30),     # upper limit for any single wait,
    "on_failure_callback": _ping_failure,         # Called only if the task fails on its last retry
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
            Downloads all the auctions published in the 7 days before the run's Monday
            
            Parameters:
            - logical_date: We never pass logical_date. 
                            When Airflow runs a task, it looks at the functions parameter names,
                            and if one matches a value it knows about, it passes that value in.
                            logical_date = this run's date
            """
            monday = logical_date.date()
            auctions = []
            for days_back in range(7,0,-1):
                particular_date = monday - timedelta(days=days_back)
                for url in fetch_auction_urls(particular_date):
                    auction = fetch_auction(url)
                    auctions.append(auction)
            print(f"Fetched {len(auctions)} auctions")
            return auctions

        @task
        def load_auctions(auctions: list[dict]) -> int:
            conn = PostgresHook(postgres_conn_id="subastas_db").get_conn()
            try:
                inserted = insert_auctions(conn, auctions)
            finally:
                conn.close()
            print(f"Inserted {inserted}, skipped {len(auctions) - inserted}")
            return inserted

        auctions = fetch_auctions()
        loaded = load_auctions(auctions)
        create_table >> loaded

    @task_group
    def silver():
        create_tables = SQLExecuteQueryOperator(
            task_id="create_tables",
            conn_id="subastas_db",
            sql="create_silver.sql"
        )

        @task
        def transform_auctions() -> dict:
            """Loads every announcement in bronze that isn't in silver yet."""
            conn = PostgresHook(postgres_conn_id="subastas_db").get_conn()
            try:
                result = load_silver(conn)
            finally:
                conn.close()

            print(f"Loaded {len(result['loaded'])}, failed {len(result['failed'])}")
            # Fail the task so the problem shows in the UI. A retry only repeats the failed ones.
            if result["failed"]:
                raise RuntimeError(f"Announcements that failed: {result['failed']}")
            return result

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