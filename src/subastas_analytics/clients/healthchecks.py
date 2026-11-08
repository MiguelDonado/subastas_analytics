"""Send failure alerts to healthchecks.io."""

import logging
import os

import requests

logger = logging.getLogger(__name__)


def ping_failure() -> None:
    """Ping /fail, which alerts you right away. A problem with healthchecks.io is only logged, so it can't replace the error being reported."""
    try:
        requests.get(f"{os.environ['HEALTHCHECK_URL']}/fail", timeout=10)
    except requests.RequestException:
        logger.exception("Could not ping healthchecks.io")