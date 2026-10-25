# tests/api/web/test_quiet_polls.py
"""Background polls stay out of the access log while they succeed."""

import logging

import pytest

from src.api.main import _QuietPolls


def _record(path, status):
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", path, "1.1", status),
        None,
    )


@pytest.mark.parametrize(
    "path, status, logged",
    [
        ("/leagues/abc/sim/status", 200, False),
        ("/leagues/abc/lobby/gms", 200, False),
        ("/leagues/abc/sim/status", 307, True),  # signed out: still logged
        ("/leagues/abc/sim/status", 403, True),
        ("/leagues/abc/sim", 200, True),
        ("/leagues/abc/standings", 200, True),
    ],
)
def test_only_successful_polls_are_hidden(path, status, logged):
    assert _QuietPolls().filter(_record(path, status)) is logged
