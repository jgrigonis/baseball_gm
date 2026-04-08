# tests/conftest.py
import sqlite3
import pytest
from unittest.mock import Mock

from tests.utils import FakeTeam, FakeRNG
from src.game.game import Game
from src.db.init import init_db

# ── Repo imports ──────────────────────────────────────────────────────────────
from src.db.repositories.bullpen_roles_repo import (
    get_current_roles,
    set_roles,
)
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.pitcher_state import PitcherStateRepository
from src.db.repositories.player_games import PlayerGameRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.talent_cap_repo import TalentCapRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository


# ── Core DB fixture ───────────────────────────────────────────────────────────

@pytest.fixture
def db_conn():
    """
    In-memory SQLite connection initialised with the real production schema
    (schema.py) and all migrations applied.

    This is the single source of truth for test DB setup.  When the project
    migrates to Postgres, only this fixture needs to change.

    Scoped to 'function' (default) so every test gets a clean slate.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()

@pytest.fixture
def db_conn_factory():
    """Factory that creates fresh initialised DB connections. Use when a test
    needs more than one independent connection."""
    conns = []
    def _make():
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conns.append(conn)
        return conn
    yield _make
    for c in conns:
        c.close()


@pytest.fixture
def db_seed(db_conn):
    """
    Baseline rows that satisfy FK constraints for most repo tests.
    Inserts: 1 league, 2 seasons, 4 teams, 5 games, 2 players.
    Returns the db_conn so tests can add more rows on top.
    """
    # Leagues
    db_conn.execute(
        """
        INSERT INTO leagues (id, name, state)
        VALUES (?, ?, ?)
        """,
        ("league-1", "League 1", "season"),
    )
    # Seasons
    db_conn.executemany(
        "INSERT INTO seasons (id, year, name) VALUES (?, ?, ?)",
        [
            ("season-1", 2025, "Season 1"), 
            ("season-2", 2026, "Season 2"),
            ("season-10", 2026, "Season 2"),
            ("season-11", 2026, "Season 2"),
            ("season-2023", 2023, "Season 1"),
            ("season-2024", 2024, "Season 2"),
            ("season-2025", 2025, "Season 3"),
            ("season-2026", 2026, "Season 4"),
            ("S1", 2026, "Season 1"),
            ("test-season", 2026, "Season 1"),
            ("season-3025", 2025, "Season 3"),
        ],
    )
    # Teams
    db_conn.executemany(
        "INSERT INTO teams (id, city, mascot) VALUES (?, ?, ?)",
        [
            ("team-1",    "City 1",    "Team 1"),
            ("team-2",    "City 2",    "Team 2"),
            ("team-home", "Home City", "Homers"),
            ("team-away", "Away City", "Visitors"),
            ("home-team", "Home City", "Homers"),
            ("away-team", "Away City", "Visitors"),
            ("BOS", "Boston", "Rots"),
            ("home-11",    "home",    "home"),
            ("home-12",    "home",    "home"),
            ("home-13",    "home",    "home"),
            ("home-14",    "home",    "home"),
            ("home-15",    "home",    "home"),
            ("away-11",    "away",    "away"),
            ("away-12",    "away",    "away"),
            ("away-13",    "away",    "away"),
            ("away-14",    "away",    "away"),
            ("away-15",    "away",    "away"),
            ("team-a",    "away",    "away"),
            ("team-b",    "away",    "away"),
            ("team-c",    "away",    "away"),
            ("team-d",    "away",    "away"),
        ],
    )
    # Players
    db_conn.executemany(
        "INSERT INTO players (id, first_name, last_name, bats, throws, position)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("p1", "John", "Doe",  "R", "R", "cf"),
            ("p2", "Jane", "Doe",  "L", "L", "ss"),
            ("player-0", "Joe", "Doe",  "R", "R", "cf"),
            ("player-1", "John", "Doe",  "R", "R", "cf"),
            ("player-2", "Jane", "Doe",  "L", "L", "ss"),
            ("player-3", "John", "Doe",  "R", "R", "cf"),
            ("player-4", "Jane", "Doe",  "L", "L", "ss"),
            ("P001", "Jane", "Doe",  "L", "L", "ss"),
            ("P002", "Jane", "Doe",  "L", "L", "ss"),
            ("P003", "Jane", "Doe",  "L", "L", "ss"),
            ("P004", "Jane", "Doe",  "L", "L", "ss"),
            ("P005", "Jane", "Doe",  "L", "L", "ss"),
            ("P006", "Jane", "Doe",  "L", "L", "ss"),
        ],
    )
    # Games (season-1, using team-home vs team-away)
    db_conn.executemany(
        "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id, completed)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [(f"game-{i}", f"2025-04-{i+1:02d}", "season-1", "team-home", "team-away", 0)
         for i in range(5)],
    )
    db_conn.commit()
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
        help="Postgres connection URL (e.g. postgresql://user:pass@localhost/test). "
             "When set, db_conn uses Postgres instead of SQLite.",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--slow"):
        skip_slow = pytest.mark.skip(reason="use --slow to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
