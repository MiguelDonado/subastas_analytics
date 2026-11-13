"""Fixtures for the integration tests: a real Postgres with the project's tables."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import psycopg2
import pytest
from helpers import PUBLICATION_DATE, TEXT_PREFIX, announcement, catastro_info
from testcontainers.community.postgres import PostgresContainer

from subastas_analytics.clients.goolzoom import normalize_reference
from subastas_analytics.clients.llm import MODEL
from subastas_analytics.loaders.bronze import insert_auctions

SQL_DIR = Path(__file__).parents[2] / "include" / "sql"

# The tables a test can write to. Emptied before every test
TABLES = [
    "bronze.auctions",
    "silver.auctions",
    "silver.lots",
    "silver.municipios",
    "silver.catastral_references",
    "silver.lots_catastral_references",
    "silver.failed_announcements",
    "gold.dim_date",
    "gold.dim_auctions",
    "gold.dim_catastral_references",
    "gold.fact_lots",
    "gold.lots_catastral_references_bridge",
]


@pytest.fixture(scope="session")
def postgres() -> Iterator[dict]:
    """Start one Postgres 17 container for the whole test session, with the bronze, silver and gold tables.

    scope="session": it runs once, before the first test that asks for it, and the container is
    deleted after the last test. Starting one per test would take seconds each.
    The same major version as subastas-db, so the SQL behaves the same as in production.

    It returns the connection details, not the container. testcontainers asks Docker for the host and
    port through `requests`, which the safety net blocks during a test. So they're read here, once,
    while the container starts (before the safety net is in place).
    """
    with PostgresContainer("postgres:17") as container:
        connection_details = {
            "host": container.get_container_host_ip(),
            "port": container.get_exposed_port(5432),
            "user": container.username,
            "password": container.password,
            "dbname": container.dbname,
        }
        connection = psycopg2.connect(**connection_details)
        cursor = connection.cursor()
        cursor.execute((SQL_DIR / "create_bronze_auctions.sql").read_text())
        cursor.execute((SQL_DIR / "create_silver.sql").read_text())
        cursor.execute((SQL_DIR / "create_gold.sql").read_text())
        connection.commit()
        connection.close()
        yield connection_details
    # Leaving the `with` stops and deletes the container


@pytest.fixture
def conn(postgres):
    """A new connection for each test, to tables that start empty.

    load_silver commits, so a rollback can't undo what a test did. TRUNCATE empties every table instead,
    and RESTART IDENTITY makes the ids start at 1 again.
    """
    connection = psycopg2.connect(**postgres)
    with connection.cursor() as cursor:
        cursor.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY")
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture(autouse=True)
def sql_dir(monkeypatch):
    """Point read_sql() to include/sql on this computer.

    read_sql() builds the path of each .sql file from SQL_DIR, which points inside the Airflow containers
    (/usr/local/airflow/include/sql). But here pytest runs outside them, on this computer, where that folder
    doesn't exist. It replaces it with the path to include/sql on this computer, so read_sql() can find the .sql files.
    """
    monkeypatch.setattr("subastas_analytics.loaders.common.SQL_DIR", SQL_DIR)


@pytest.fixture
def add_bronze(conn):
    """Add announcements to bronze.auctions, so load_silver finds them pending.

    It returns a function: add_bronze("BOE-B-1", "BOE-B-2"). 
    Each text is "Text of <boe_ref>", so the fake Claude knows which announcement it was sent. 
    It uses the real insert of the bronze loader.

    The announcement_text is designed that way so that we can easily identify in the fake Claude calls 
    to which announcement it corresponds.
    """
    def _add(*boe_refs: str, publication_date=PUBLICATION_DATE) -> None:
        insert_auctions(conn, [
            {
                "boe_ref": boe_ref,
                "announcement_text": TEXT_PREFIX + boe_ref,
                "publication_date": publication_date,
                "source_url": f"https://www.boe.es/diario_boe/xml.php?id={boe_ref}",
            }
            for boe_ref in boe_refs
        ])

    return _add


# The three fakes below are autouse: load_silver calls all three, so a test that forgot one would reach the
# real function. A test that needs to change what a fake does, or check its calls, asks for it by name,
# and gets the same fake that load_silver uses in that test.

@pytest.fixture(autouse=True)
def claude(monkeypatch):
    """Fake extract_info_announcement. By default, every announcement has one valid lot with REF_A.

    To change the answer for one announcement, set it in claude.answers:
    - an Announcement: Claude returns it, with MODEL as the model
    - an (Announcement, model) tuple: Claude returns it, answered by that model (a fallback)
    - an error: Claude raises it
    claude.call_count is the number of calls, so the number of announcements paid for.
    """
    answers = {}

    def extract(text: str, publication_date: date):
        answer = answers.get(text.removeprefix(TEXT_PREFIX), announcement())
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, tuple):
            return answer
        return answer, MODEL

    fake = Mock(side_effect=extract)
    fake.answers = answers
    # Patched in silver, where it's used: silver imported the name with `from ..clients.llm import ...`
    monkeypatch.setattr("subastas_analytics.loaders.silver.extract_info_announcement", fake)
    return fake


@pytest.fixture(autouse=True)
def goolzoom(monkeypatch):
    """Fake lookup_reference. By default, every reference exists and is complete (catastro_info).

    To change the answer for one reference, set it in goolzoom.answers, by its normalized form:
    - a CatastroInfo: Goolzoom returns it
    - None: the reference is rejected (wrong length, not found or incomplete)
    - an error: Goolzoom raises it
    """
    answers = {}

    def lookup(raw_reference: str):
        reference = normalize_reference(raw_reference)
        if reference not in answers:
            return catastro_info(reference)
        answer = answers[reference]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    fake = Mock(side_effect=lookup)
    fake.answers = answers
    monkeypatch.setattr("subastas_analytics.loaders.silver.lookup_reference", fake)
    return fake


@pytest.fixture(autouse=True)
def ping(monkeypatch):
    """Fake ping_failure, so a test can check whether the failure alert was sent."""
    fake = Mock()
    monkeypatch.setattr("subastas_analytics.loaders.silver.ping_failure", fake)
    return fake

