from datetime import timedelta
from pathlib import Path

from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import dag, task, task_group
from pendulum import datetime

from subastas_analytics.boe import get_auction_info, get_auction_urls

SQL_DIR = Path("/usr/local/airflow/include/sql")


@dag(
    schedule="0 0 * * 1",   # Mondays at 00:00 UTC
    # Earliest date the DAG can have a scheduled run. Airflow doesnt schedule anything before it
    start_date=datetime(2026, 10, 5),
    # Creates a run for every scheduled time since start_date that hasn't run yet
    catchup=True,
    default_args={
    "retries": 3,
    "retry_delay": timedelta(minutes=2),          # first wait
    "retry_exponential_backoff": True,            # double the wait each time
    "max_retry_delay": timedelta(minutes=30),     # upper limit for any single wait
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
                for url in get_auction_urls(particular_date):
                    auction = get_auction_info(url)
                    auctions.append(auction)
            print(f"Fetched {len(auctions)} auctions")
            return auctions

        @task
        def load_auctions(auctions: list[dict]) -> int:
            insert_sql = (SQL_DIR / "insert_bronze_auctions.sql").read_text()
            conn = PostgresHook(postgres_conn_id="subastas_db").get_conn()
            inserted = 0
            try:
                with conn.cursor() as cursor:
                    for auction in auctions:
                        cursor.execute(insert_sql, auction)
                        inserted += cursor.rowcount   # 1 if inserted, 0 if already stored
                conn.commit()
            finally:
                conn.close()
            print(f"Inserted {inserted}, skipped {len(auctions) - inserted}")
            return inserted

        auctions = fetch_auctions()
        loaded = load_auctions(auctions)
        create_table >> loaded

    bronze()

subastas_pipeline()