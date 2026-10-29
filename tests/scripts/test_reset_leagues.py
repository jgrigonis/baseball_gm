# tests/scripts/test_reset_leagues.py
"""`cligr.py reset-leagues` deletes every league and its team files, and keeps
user accounts."""

import argparse
import uuid

import pytest

from scripts import cligr
from tests.api.test_leave_league import _league_with_history, _row_counts


def _reset(monkeypatch, yes=True, answer="n"):
    monkeypatch.setattr("builtins.input", lambda _prompt: answer)
    cligr.cmd_reset_leagues(argparse.Namespace(yes=yes))


@pytest.fixture(autouse=True)
def setup(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(cligr, "get_connection", lambda: db_conn)
    monkeypatch.setattr(cligr, "TEAM_FILES_DIR", tmp_path)
    # Leagues other tests committed would be deleted too.
    _reset(monkeypatch)
    return tmp_path


def _leagues(db):
    return db.execute("SELECT COUNT(*) AS n FROM leagues").fetchone()["n"]


def test_deletes_every_league_and_keeps_users(db_conn, factory, setup, monkeypatch):
    before = _row_counts(db_conn)
    leagues = [_league_with_history(db_conn, factory)[0] for _ in range(2)]
    for league in leagues:
        (setup / league.id / "2025").mkdir(parents=True)

    _reset(monkeypatch)

    after = _row_counts(db_conn)
    # Both leagues' Alices keep their accounts; nothing else is left.
    before["users"] += 2
    assert {t: n for t, n in after.items() if n != before[t]} == {}
    assert not any(setup.iterdir())


def test_asks_first(db_conn, factory, monkeypatch, capsys):
    factory.league()

    with pytest.raises(SystemExit) as exit_info:
        _reset(monkeypatch, yes=False, answer="n")

    assert exit_info.value.code == 1
    assert _leagues(db_conn) == 1
    assert "Aborted" in capsys.readouterr().out

    _reset(monkeypatch, yes=False, answer="y")

    assert _leagues(db_conn) == 0


def test_prints_what_it_deleted(db_conn, factory, monkeypatch, capsys):
    league = factory.league()
    user_id = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO users (id, session_token, display_name) VALUES (%s, %s, 'Dan')",
        (user_id, user_id),
    )
    users = db_conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]

    _reset(monkeypatch)

    out = capsys.readouterr().out
    assert f"Deleted Test League  [{league.id}]" in out
    assert f"Deleted 1 league(s), kept {users} user account(s)." in out


def test_nothing_to_delete(monkeypatch, capsys):
    _reset(monkeypatch)

    assert "No leagues to delete." in capsys.readouterr().out
