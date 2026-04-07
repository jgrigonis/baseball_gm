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
