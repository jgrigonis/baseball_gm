# tests/db/test_locks.py
"""league_lock lets one request at a time advance a league, across
connections (so across server processes), and holds through commits."""

import os
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

from src.db.locks import LeagueBusy, league_lock


@pytest.fixture
def other_conn(request):
    """A second, independent connection, like another server process."""
    url = request.config.getoption("--db-url") or os.environ["DATABASE_TEST_URL"]
    conn = psycopg.connect(url, row_factory=dict_row)
    yield conn
    conn.close()


def test_second_connection_is_turned_away(db_conn, other_conn):
    league_id = str(uuid.uuid4())
    with league_lock(other_conn, league_id):
        with pytest.raises(LeagueBusy):
            with league_lock(db_conn, league_id):
                pass


def test_released_after_the_block(db_conn, other_conn):
    league_id = str(uuid.uuid4())
    with league_lock(other_conn, league_id):
        pass
    with league_lock(db_conn, league_id):
        pass


def test_held_through_commits(db_conn, other_conn):
    """The sim commits after every game; the lock must outlive those."""
    league_id = str(uuid.uuid4())
    with league_lock(other_conn, league_id):
        other_conn.commit()
        with pytest.raises(LeagueBusy):
            with league_lock(db_conn, league_id):
                pass


def test_leagues_dont_block_each_other(db_conn, other_conn):
    with league_lock(other_conn, str(uuid.uuid4())):
        with league_lock(db_conn, str(uuid.uuid4())):
            pass


def test_released_after_a_failed_statement(db_conn, other_conn):
    league_id = str(uuid.uuid4())
    with pytest.raises(psycopg.errors.UndefinedTable):
        with league_lock(other_conn, league_id):
            other_conn.execute("SELECT * FROM no_such_table")
    with league_lock(db_conn, league_id):
        pass


def test_connection_closing_releases_it(db_conn, request):
    url = request.config.getoption("--db-url") or os.environ["DATABASE_TEST_URL"]
    league_id = str(uuid.uuid4())
    crashed = psycopg.connect(url, row_factory=dict_row)
    with league_lock(crashed, league_id):
        crashed.close()
        with league_lock(db_conn, league_id):
            pass


def test_wait_gets_the_lock_once_its_let_go(db_conn, other_conn):
    """A release during a multi-day sim waits for the day to end."""
    import threading

    league_id = str(uuid.uuid4())
    held = threading.Event()

    def sim_day():
        with league_lock(other_conn, league_id):
            held.set()
            threading.Event().wait(0.5)

    t = threading.Thread(target=sim_day)
    t.start()
    held.wait()
    with league_lock(db_conn, league_id, wait=5):
        pass
    t.join()


def test_wait_gives_up_after_the_wait(db_conn, other_conn):
    league_id = str(uuid.uuid4())
    with league_lock(other_conn, league_id):
        with pytest.raises(LeagueBusy):
            with league_lock(db_conn, league_id, wait=0.3):
                pass
