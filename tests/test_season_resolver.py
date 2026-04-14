# tests/league/test_season_resolver.py
import sqlite3
import pytest
from pathlib import Path


def make_db(tmp_path: Path, seasons: list[dict]) -> Path:
    """Create a temp SQLite DB with the given seasons."""
    db = tmp_path / "league.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE seasons (id TEXT, year INTEGER, name TEXT)")
    conn.executemany("INSERT INTO seasons VALUES (:id, :year, :name)", seasons)
    conn.commit()
    conn.close()
    return db


def resolve(season_arg):
    """Call resolve_season with the tmp db path patched in."""
    # from src.league.season_resolver import resolve_season

    # with patch("src.league.season_resolver.LEAGUE_FILES_DIR", str(db_path.parent)):
    #     return resolve_season(season_arg)
    pass


# ---------------------------------------------------------------------------
# Auto-select
# ---------------------------------------------------------------------------


def test_auto_selects_single_season(tmp_path):
    db = make_db(tmp_path, [{"id": "abc123", "year": 2025, "name": "Season1"}])
    path, sid, label = resolve(db, None)
    assert sid == "abc123"
    assert label == "Season1 (2025)"
    assert path == db


def test_auto_select_fails_with_multiple_seasons(tmp_path):
    db = make_db(
        tmp_path,
        [
            {"id": "aaa", "year": 2024, "name": "Season1"},
            {"id": "bbb", "year": 2025, "name": "Season2"},
        ],
    )
    with pytest.raises(SystemExit):
        resolve(db, None)


# ---------------------------------------------------------------------------
# Match by year
# ---------------------------------------------------------------------------


def test_match_by_year(tmp_path):
    db = make_db(
        tmp_path,
        [
            {"id": "aaa", "year": 2024, "name": "Season1"},
            {"id": "bbb", "year": 2025, "name": "Season2"},
        ],
    )
    _, sid, label = resolve(db, "2025")
    assert sid == "bbb"
    assert label == "Season2 (2025)"


# ---------------------------------------------------------------------------
# Match by name
# ---------------------------------------------------------------------------


def test_match_by_name(tmp_path):
    db = make_db(
        tmp_path,
        [
            {"id": "aaa", "year": 2024, "name": "Season1"},
            {"id": "bbb", "year": 2025, "name": "Season2"},
        ],
    )
    _, sid, label = resolve(db, "Season1")
    assert sid == "aaa"
    assert label == "Season1 (2024)"


# ---------------------------------------------------------------------------
# Match by id
# ---------------------------------------------------------------------------


def test_match_by_id(tmp_path):
    db = make_db(
        tmp_path,
        [
            {"id": "aaa", "year": 2024, "name": "Season1"},
            {"id": "bbb", "year": 2025, "name": "Season2"},
        ],
    )
    _, sid, label = resolve(db, "bbb")
    assert sid == "bbb"


# ---------------------------------------------------------------------------
# Not found
# ---------------------------------------------------------------------------


def test_not_found_raises(tmp_path):
    db = make_db(tmp_path, [{"id": "aaa", "year": 2024, "name": "Season1"}])
    with pytest.raises(SystemExit):
        resolve(db, "nonexistent")


# ---------------------------------------------------------------------------
# Empty DB
# ---------------------------------------------------------------------------


def test_empty_db_raises(tmp_path):
    db = make_db(tmp_path, [])
    with pytest.raises(SystemExit):
        resolve(db, None)
