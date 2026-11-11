"""The DAG: its settings, its task order, and what its own tasks do (B2, B6, B10, B14, B17, B19, S13, S15).

Needs Airflow, so it only runs in the Astro container: `astro dev pytest tests/dags`.

Each test gets a task's function with dag.get_task(...).python_callable and calls it directly. The BOE,
Claude, the database and the loaders are replaced with fakes in the DAG module, where the tasks look them up.
"""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pendulum
import pytest
import requests
import subastas_pipeline
from airflow.dag_processing.dagbag import DagBag
from airflow.sdk.exceptions import AirflowFailException

# The Monday of a run, as Airflow passes it in logical_date
MONDAY = pendulum.datetime(2026, 11, 9, tz="UTC")
# The 7 days fetch_auctions reads: from the Monday before to the Sunday
WEEK = [date(2026, 11, 2) + timedelta(days=i) for i in range(7)]
PREVIOUS_WEEK = [day - timedelta(days=7) for day in WEEK]


@pytest.fixture
def dag():
    return subastas_pipeline.subastas_pipeline()


def task_function(dag, task_id: str):
    """The Python function behind a task, which the test can call like any function."""
    return dag.get_task(task_id).python_callable


def candidate(boe_ref: str) -> tuple[str, str, str]:
    """A (boe_ref, title, url_xml) as fetch_auction_candidates returns it."""
    return boe_ref, f"Title of {boe_ref}", f"https://www.boe.es/diario_boe/xml.php?id={boe_ref}"


@pytest.fixture
def fakes(monkeypatch):
    """Replace everything fetch_auctions calls. Change `candidates` to set what each day's summary has.

    - candidates: {day: [candidate, ...]}. A day not listed has none
    - fetch_auction_candidates, fetch_announcement_xml: the BOE
    - is_auction_title: Claude, says yes to every title by default
    - stored_boe_refs: the ones already in bronze, none by default
    - postgres: PostgresHook
    """
    candidates = {}
    fake = SimpleNamespace(
        candidates=candidates,
        fetch_auction_candidates=Mock(side_effect=lambda day: candidates.get(day, [])),
        fetch_announcement_xml=Mock(side_effect=lambda url: f"<xml of {url}>".encode()),
        is_auction_title=Mock(return_value=True),
        stored_boe_refs=Mock(return_value=set()),
        postgres=Mock(),
    )
    monkeypatch.setattr(subastas_pipeline, "fetch_auction_candidates", fake.fetch_auction_candidates)
    monkeypatch.setattr(subastas_pipeline, "fetch_announcement_xml", fake.fetch_announcement_xml)
    monkeypatch.setattr(subastas_pipeline, "is_auction_title", fake.is_auction_title)
    monkeypatch.setattr(subastas_pipeline, "stored_boe_refs", fake.stored_boe_refs)
    monkeypatch.setattr(subastas_pipeline, "PostgresHook", fake.postgres)
    return fake


######################################
# The DAG
######################################

def test_dag_imports_without_errors():
    """The same check the scheduler does when it reads the dags folder."""
    dag_bag = DagBag(dag_folder=subastas_pipeline.__file__, include_examples=False)

    assert dag_bag.import_errors == {}
    assert list(dag_bag.dags) == ["subastas_pipeline"]


def test_dag_settings(dag):
    assert dag.schedule == "0 0 * * 1"   # Mondays at 00:00 UTC, before the systemd timer starts Airflow
    assert dag.catchup is True           # B16: the missed Mondays run when Airflow starts
    assert dag.max_active_runs == 1      # S15: two runs in silver at once would pay Claude twice
    assert dag.default_args["retries"] == 3
    assert dag.default_args["on_failure_callback"] is subastas_pipeline._on_task_ping_failure


def test_parse_auctions_has_no_retries(dag):
    """B11–B13: a parse error gives the same result on every attempt, so it alerts right away."""
    assert dag.get_task("bronze.parse_auctions").retries == 0


def test_task_order(dag):
    order = [
        "bronze.create_table",
        "bronze.fetch_auctions",
        "bronze.parse_auctions",
        "bronze.load_auctions",
        "silver.create_tables",
        "silver.transform_auctions",
        "gold.create_tables",
        "gold.load_tables",
        "ping_success",
    ]
    # Each task runs right after the one before it, and only after it
    for before, after in zip(order, order[1:]):
        assert [task.task_id for task in dag.get_task(after).upstream_list] == [before]
    assert dag.get_task(order[0]).upstream_list == []


def test_failure_callback_pings_fail(monkeypatch):
    ping_failure = Mock()
    monkeypatch.setattr(subastas_pipeline, "ping_failure", ping_failure)

    subastas_pipeline._on_task_ping_failure({})

    ping_failure.assert_called_once()


######################################
# bronze.fetch_auctions
######################################

def test_fetch_asks_for_the_7_days_before_the_monday(dag, fakes):
    fakes.candidates[WEEK[0]] = [candidate("BOE-B-1")]

    task_function(dag, "bronze.fetch_auctions")(logical_date=MONDAY)

    assert [call.args[0] for call in fakes.fetch_auction_candidates.call_args_list] == WEEK


def test_fetch_returns_the_xml_of_the_titles_claude_confirms(dag, fakes, caplog):
    fakes.candidates[WEEK[0]] = [candidate("BOE-B-1"), candidate("BOE-B-2")]
    # B6: Claude rejects the 2nd title
    fakes.is_auction_title.side_effect = lambda title: title != "Title of BOE-B-2"

    accepted = task_function(dag, "bronze.fetch_auctions")(logical_date=MONDAY)

    url = candidate("BOE-B-1")[2]
    # The XML is returned as text, because XCom stores the return value as JSON
    assert accepted == [{"url": url, "xml": f"<xml of {url}>"}]
    assert fakes.is_auction_title.call_count == 2


def test_b2_boe_summary_error_fails_before_claude(dag, fakes):
    # The 1st day has a candidate, the 2nd day's summary fails
    fakes.fetch_auction_candidates.side_effect = [[candidate("BOE-B-1")], requests.HTTPError("503")]

    with pytest.raises(requests.HTTPError):
        task_function(dag, "bronze.fetch_auctions")(logical_date=MONDAY)

    fakes.is_auction_title.assert_not_called()


def test_b10_announcement_download_error_fails_before_claude(dag, fakes):
    """Every BOE call comes before any Claude call, so a retry never pays Claude again for titles it classified."""
    fakes.candidates[WEEK[0]] = [candidate("BOE-B-1"), candidate("BOE-B-2")]
    fakes.fetch_announcement_xml.side_effect = [b"<xml/>", requests.HTTPError("500")]

    with pytest.raises(requests.HTTPError):
        task_function(dag, "bronze.fetch_auctions")(logical_date=MONDAY)

    fakes.is_auction_title.assert_not_called()


def test_b14_candidates_already_in_bronze_are_skipped(dag, fakes):
    fakes.candidates[WEEK[0]] = [candidate("BOE-B-1"), candidate("BOE-B-2")]
    fakes.stored_boe_refs.return_value = {"BOE-B-1"}

    accepted = task_function(dag, "bronze.fetch_auctions")(logical_date=MONDAY)

    # Asked about every candidate, by boe_ref
    assert fakes.stored_boe_refs.call_args.args[1] == ["BOE-B-1", "BOE-B-2"]
    # BOE-B-1 isn't downloaded or sent to Claude
    assert [call.args[0] for call in fakes.fetch_announcement_xml.call_args_list] == [candidate("BOE-B-2")[2]]
    assert [call.args[0] for call in fakes.is_auction_title.call_args_list] == ["Title of BOE-B-2"]
    assert [auction["url"] for auction in accepted] == [candidate("BOE-B-2")[2]]
    # The connection is closed
    fakes.postgres.return_value.get_conn.return_value.close.assert_called_once()


def test_b17_two_empty_weeks_fail_without_retries(dag, fakes):
    with pytest.raises(AirflowFailException, match="2 weeks in a row"):
        task_function(dag, "bronze.fetch_auctions")(logical_date=MONDAY)

    # It also read the week before, to be sure
    assert [call.args[0] for call in fakes.fetch_auction_candidates.call_args_list] == WEEK + PREVIOUS_WEEK
    fakes.is_auction_title.assert_not_called()
    fakes.postgres.assert_not_called()


def test_b19_one_empty_week_returns_nothing_without_alerting(dag, fakes):
    fakes.candidates[PREVIOUS_WEEK[0]] = [candidate("BOE-B-1")]

    assert task_function(dag, "bronze.fetch_auctions")(logical_date=MONDAY) == []

    fakes.is_auction_title.assert_not_called()
    fakes.postgres.assert_not_called()


######################################
# bronze.parse_auctions
######################################

def test_parse_turns_the_xml_back_into_bytes(dag, monkeypatch):
    parse_auction = Mock(return_value={"boe_ref": "BOE-B-1"})
    monkeypatch.setattr(subastas_pipeline, "parse_auction", parse_auction)

    result = task_function(dag, "bronze.parse_auctions")([{"url": "https://x", "xml": "<xml/>"}])

    assert result == [{"boe_ref": "BOE-B-1"}]
    parse_auction.assert_called_once_with(b"<xml/>", "https://x")


######################################
# silver.transform_auctions
######################################

@pytest.fixture
def silver_fakes(monkeypatch):
    fake = SimpleNamespace(load_silver=Mock(return_value={"loaded": ["BOE-B-1"], "failed": []}), postgres=Mock())
    monkeypatch.setattr(subastas_pipeline, "load_silver", fake.load_silver)
    monkeypatch.setattr(subastas_pipeline, "PostgresHook", fake.postgres)
    return fake


def test_transform_succeeds_when_nothing_failed(dag, silver_fakes):
    assert task_function(dag, "silver.transform_auctions")() is None


def test_s13_transform_fails_without_retries_when_an_announcement_failed(dag, silver_fakes):
    """S13: the failed ones are already recorded, so a retry would succeed and the alert would never be sent."""
    silver_fakes.load_silver.return_value = {"loaded": ["BOE-B-1"], "failed": ["BOE-B-2"]}

    with pytest.raises(AirflowFailException, match="BOE-B-2"):
        task_function(dag, "silver.transform_auctions")()


def test_transform_closes_the_connection_when_silver_stops(dag, silver_fakes):
    """STOPPED: the error reaches Airflow, so it retries, and the connection is still closed."""
    silver_fakes.load_silver.side_effect = requests.ConnectionError("Goolzoom down")

    with pytest.raises(requests.ConnectionError):
        task_function(dag, "silver.transform_auctions")()

    silver_fakes.postgres.return_value.get_conn.return_value.close.assert_called_once()


######################################
# ping_success
######################################

def test_ping_success_pings_healthchecks(dag, monkeypatch):
    monkeypatch.setenv("HEALTHCHECK_URL", "https://hc-ping.com/test-uuid")
    get = Mock()
    monkeypatch.setattr(subastas_pipeline.requests, "get", get)

    task_function(dag, "ping_success")()

    assert get.call_args.args[0] == "https://hc-ping.com/test-uuid"
    get.return_value.raise_for_status.assert_called_once()