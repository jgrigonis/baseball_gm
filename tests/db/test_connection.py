# tests/db/test_connection.py

import logging
from unittest.mock import MagicMock

import psycopg
import pytest

from src.db.connection import rollback_quietly


class TestRollbackQuietly:
    def test_rolls_back(self):
        conn = MagicMock()
        rollback_quietly(conn)
        conn.rollback.assert_called_once()

    def test_failed_rollback_is_logged_not_raised(self, caplog):
        conn = MagicMock()
        conn.rollback.side_effect = psycopg.OperationalError("connection lost")

        with caplog.at_level(logging.WARNING):
            rollback_quietly(conn)

        (record,) = caplog.records
        assert record.getMessage() == "Rollback failed"
        assert record.exc_info is not None

    def test_non_database_error_propagates(self):
        """Only database errors are tolerated; a bug still surfaces."""
        conn = MagicMock()
        conn.rollback.side_effect = AttributeError("not a connection")

        with pytest.raises(AttributeError):
            rollback_quietly(conn)
