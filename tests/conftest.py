# tests/conftest.py
import os
import pytest
import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from unittest.mock import Mock

from tests.factories.data_factory import TestDataFactory
from tests.utils import FakeTeam, FakeRNG
from src.game.game import Game
from src.db.init import init_db

# ── Repo imports ──────────────────────────────────────────────────────────────
# from src.db.repositories.bullpen_roles_repo import (
#     get_current_roles,
#     set_roles,
# )
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.pitcher_state import PitcherStateRepository
from src.db.repositories.player_games import PlayerGameRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.talent_cap_repo import TalentCapRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository


# ── Core DB fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def _session_conn(request):
    """
    Session-scoped Postgres connection.  Runs init_db exactly once for the
    whole test session, then stays open so every test can borrow it.

    The DATABASE_URL env var is the default; --db-url on the CLI overrides it.
    """
    db_url = request.config.getoption("--db-url") or os.environ.get("DATABASE_TEST_URL")
    if not db_url:
        raise RuntimeError(
            "No test database URL found. Set DATABASE_TEST_URL or pass --db-url."
        )
    conn = psycopg.connect(db_url, row_factory=dict_row)
    init_db(conn)
    # Wipe any data left over from a previous test session.
    # CASCADE handles all dependent tables.  schema_migrations is preserved.
    conn.execute("TRUNCATE TABLE leagues, seasons, teams, players, users CASCADE")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def db_conn(_session_conn):
    """
    Function-scoped fixture.  Each test runs inside a SAVEPOINT so all writes
    are invisible to other tests and are rolled back automatically on teardown.
    No schema recreation cost — just a cheap savepoint per test.

    If the test body exercises production code that calls conn.commit() or
    conn.rollback(), the savepoint will be gone by teardown.  We catch that
    and issue a plain ROLLBACK to recover the connection for the next test.
    Note: data committed by production code inside the test will persist in
    the test DB — use unique IDs in such tests to avoid cross-run collisions.
    """
    _session_conn.execute("SAVEPOINT test_savepoint")
    yield _session_conn
    try:
        _session_conn.execute("ROLLBACK TO SAVEPOINT test_savepoint")
        _session_conn.execute("RELEASE SAVEPOINT test_savepoint")
    except Exception:
        # Only issue ROLLBACK if the connection is in a genuine error state.
        # Covering two cases:
        #   - Production code called conn.commit(): savepoint is gone,
        #     ROLLBACK TO SAVEPOINT threw InvalidSavepointSpecification,
        #     which aborted the transaction → INERROR.
        #   - Production code called conn.rollback(): same result.
        # If the connection is IDLE or INTRANS for any other reason, leave
        # it alone — an unnecessary rollback() here would undo the previous
        # test's clean teardown and confuse the next test.
        if _session_conn.info.transaction_status == TransactionStatus.INERROR:
            _session_conn.rollback()


@pytest.fixture
def db_conn_factory(_session_conn):
    """
    Factory variant for tests that need to simulate multiple independent
    connections.  Each call gets its own nested savepoint.
    """
    savepoints = []

    def _make():
        sp = f"sp_{len(savepoints)}"
        _session_conn.execute(f"SAVEPOINT {sp}")
        savepoints.append(sp)
        return _session_conn

    yield _make

    for sp in reversed(savepoints):
        _session_conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
        _session_conn.execute(f"RELEASE SAVEPOINT {sp}")

@pytest.fixture
def factory(db_conn):
    return TestDataFactory(db_conn)

@pytest.fixture
def db_seed(db_conn):
    """
    Baseline rows that satisfy FK constraints for most repo tests.
    Inserts: 1 league, 11 seasons, 21 teams, 13 players, 5 games.
    Returns the db_conn so tests can add more rows on top.
    """
    with db_conn.cursor() as cur:
        # League
        cur.execute(
            "INSERT INTO leagues (id, name, state) VALUES (%s, %s, %s)",
            ("league-1", "League 1", "season"),
        )
        # Seasons
        for row in [
            ("season-1",    2025, "Season 1"),
            ("season-2",    2026, "Season 2"),
            ("season-10",   2026, "Season 2"),
            ("season-11",   2026, "Season 2"),
            ("season-2023", 2023, "Season 1"),
            ("season-2024", 2024, "Season 2"),
            ("season-2025", 2025, "Season 3"),
            ("season-2026", 2026, "Season 4"),
            ("S1",          2026, "Season 1"),
            ("test-season", 2026, "Season 1"),
            ("season-3025", 2025, "Season 3"),
        ]:
            cur.execute("INSERT INTO seasons (id, year, name) VALUES (%s, %s, %s)", row)
        # Teams
        for row in [
            ("team-1",    "City 1",    "Team 1"),
            ("team-2",    "City 2",    "Team 2"),
            ("team-home", "Home City", "Homers"),
            ("team-away", "Away City", "Visitors"),
            ("home-team", "Home City", "Homers"),
            ("away-team", "Away City", "Visitors"),
            ("BOS",       "Boston",    "Rots"),
            ("home-11",   "home",      "home"),
            ("home-12",   "home",      "home"),
            ("home-13",   "home",      "home"),
            ("home-14",   "home",      "home"),
            ("home-15",   "home",      "home"),
            ("away-11",   "away",      "away"),
            ("away-12",   "away",      "away"),
            ("away-13",   "away",      "away"),
            ("away-14",   "away",      "away"),
            ("away-15",   "away",      "away"),
            ("team-a",    "away",      "away"),
            ("team-b",    "away",      "away"),
            ("team-c",    "away",      "away"),
            ("team-d",    "away",      "away"),
        ]:
            cur.execute("INSERT INTO teams (id, city, mascot) VALUES (%s, %s, %s)", row)
        # Players
        for row in [
            ("p1",       "John", "Doe", "R", "R", "cf"),
            ("p2",       "Jane", "Doe", "L", "L", "ss"),
            ("player-0", "Joe",  "Doe", "R", "R", "cf"),
            ("player-1", "John", "Doe", "R", "R", "cf"),
            ("player-2", "Jane", "Doe", "L", "L", "ss"),
            ("player-3", "John", "Doe", "R", "R", "cf"),
            ("player-4", "Jane", "Doe", "L", "L", "ss"),
            ("P001",     "Jane", "Doe", "L", "L", "ss"),
            ("P002",     "Jane", "Doe", "L", "L", "ss"),
            ("P003",     "Jane", "Doe", "L", "L", "ss"),
            ("P004",     "Jane", "Doe", "L", "L", "ss"),
            ("P005",     "Jane", "Doe", "L", "L", "ss"),
            ("P006",     "Jane", "Doe", "L", "L", "ss"),
        ]:
            cur.execute(
                "INSERT INTO players (id, first_name, last_name, bats, throws, position)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                row,
            )
        # Games
        for i in range(5):
            cur.execute(
                "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id, completed)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (f"game-{i}", f"2025-04-{i+1:02d}", "season-1", "team-home", "team-away", 0),
            )
    return db_conn

# def insert_more_teams(db_conn):
#     teams = [
#         ("home-1", "Home Team", "Home Team"),
#         ("away-1", "Away Team", "Away Team"),
#         ("home-2", "Home Team", "Home Team"),
#         ("away-2", "Away Team", "Away Team"),
#         ("home-3", "Home Team", "Home Team"),
#         ("away-3", "Away Team", "Away Team"),
#         ("home-4", "Home Team", "Home Team"),
#         ("away-4", "Away Team", "Away Team"),
#         ("home-5", "Home Team", "Home Team"),
#         ("away-5", "Away Team", "Away Team"),
#     ]
#     for team in teams:
#         db_conn.execute(
#             """
#             INSERT INTO teams (id, city, mascot)
#             VALUES (?, ?, ?)
#             """,
#             team,
#         )

# def insert_games(db_conn):
#     db_conn.execute(
#         """
#         INSERT INTO games (id, game_date, season_id, series_id, home_team_id, away_team_id, completed)
#         VALUES (?, ?, ?, ?, ?, ?, ?)
#         """,
#         ("game-0", "2025-04-01", "season-1", None, "team-home", "team-away", 0),
#     )
#     db_conn.execute(
#         """
#         INSERT INTO games (id, game_date, season_id, series_id, home_team_id, away_team_id, completed)
#         VALUES (?, ?, ?, ?, ?, ?, ?)
#         """,
#         ("game-1", "2025-04-02", "season-1", None, "team-home", "team-away", 0),
#     )
#     db_conn.execute(
#         """
#         INSERT INTO games (id, game_date, season_id, series_id, home_team_id, away_team_id, completed)
#         VALUES (?, ?, ?, ?, ?, ?, ?)
#         """,
#         ("game-2", "2025-04-03", "season-1", None, "team-home", "team-away", 0),
#     )
#     db_conn.execute(
#         """
#         INSERT INTO games (id, game_date, season_id, series_id, home_team_id, away_team_id, completed)
#         VALUES (?, ?, ?, ?, ?, ?, ?)
#         """,
#         ("game-3", "2025-04-04", "season-1", None, "team-home", "team-away", 0),
#     )
#     db_conn.execute(
#         """
#         INSERT INTO games (id, game_date, season_id, series_id, home_team_id, away_team_id, completed)
#         VALUES (?, ?, ?, ?, ?, ?, ?)
#         """,
#         ("game-4", "2025-04-05", "season-1", None, "team-home", "team-away", 0),
#     )
#     db_conn.commit()
#     return ["game-0", "game-1", "game-2"]


    


# ── Repository fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def player_repo(db_conn):
    return PlayerRepository(db_conn)


@pytest.fixture
def player_status_repo(db_conn):
    return PlayerStatusRepository(db_conn)


@pytest.fixture
def season_repo(db_conn):
    return SeasonRepository(db_conn)


@pytest.fixture
def league_repo(db_conn):
    return LeagueRepository(db_conn)


@pytest.fixture
def games_repo(db_conn):
    return GameRepository(db_conn)


@pytest.fixture
def talent_cap_repo(db_conn):
    return TalentCapRepository(db_conn)


@pytest.fixture
def pitcher_state_repo(db_conn):
    return PitcherStateRepository(db_conn)


@pytest.fixture
def player_games_repo(db_conn):
    return PlayerGameRepository(db_conn)


@pytest.fixture
def team_rotations_repo(db_conn):
    return TeamRotationsRepository(db_conn)


# ── Game engine fixtures (unchanged from original) ────────────────────────────

@pytest.fixture
def home_team():
    return FakeTeam(name="Home")


@pytest.fixture
def away_team():
    return FakeTeam(name="Away")


@pytest.fixture
def game(home_team, away_team):
    game = Game(
        home_team=home_team,
        away_team=away_team,
        rng=FakeRNG([0.5] * 100),
    )
    game._sync_players()
    return game


@pytest.fixture
def game_no_rng(home_team, away_team):
    game = Game(
        home_team=home_team,
        away_team=away_team,
    )
    game._sync_players()
    return game


@pytest.fixture
def mock_teams():
    """Create mock teams for testing."""
    home = Mock()
    home.record = Mock()
    home.record.id = "home-123"
    home.record.city = "Home"
    home.record.mascot = "Team"
    home.name = "Home Team"
    home.has_lineup = True
    home.players = []
    home.pitch_team.lineup = []

    away = Mock()
    away.record = Mock()
    away.record.id = "away-456"
    away.record.city = "Away"
    away.record.mascot = "Team"
    away.name = "Away Team"
    away.has_lineup = True
    away.players = []
    away.pitch_team.lineup = []

    return home, away


# ── pytest options ────────────────────────────────────────────────────────────

def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", default=False)
    parser.addoption(
        "--db-url",
        action="store",
        default=None,
        help="Postgres connection URL for the test database. "
             "Falls back to the DATABASE_TEST_URL environment variable.",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--slow"):
        skip_slow = pytest.mark.skip(reason="use --slow to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
