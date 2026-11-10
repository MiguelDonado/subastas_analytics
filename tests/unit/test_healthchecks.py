"""Failure alert: a problem with healthchecks.io never hides the error being reported."""

from unittest.mock import Mock

import requests

from subastas_analytics.clients import healthchecks

URL = "https://hc-ping.com/test-uuid"


def test_ping_failure_calls_fail(monkeypatch):
    monkeypatch.setenv("HEALTHCHECK_URL", URL)
    get = Mock()
    monkeypatch.setattr(healthchecks.requests, "get", get)

    healthchecks.ping_failure()

    assert get.call_args.args[0] == f"{URL}/fail"


def test_ping_failure_only_logs_when_healthchecks_is_down(monkeypatch, caplog):
    monkeypatch.setenv("HEALTHCHECK_URL", URL)
    monkeypatch.setattr(healthchecks.requests, "get", Mock(side_effect=requests.ConnectionError("down")))

    # No exception: the error that triggered the alert is the one that must reach Airflow
    healthchecks.ping_failure()

    assert "Could not ping healthchecks.io" in caplog.text