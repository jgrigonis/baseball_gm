# tests/league/test_snake_draft.py
"""
Unit tests for SnakeDraft.

Tests cover:
- Draft order: worst record first, no-game teams at end
- Pool loading: only unattached prospects included
- Snake order: round 1 worst→best, round 2 best→worst
- Pick assignment: player added to team_players, status set to minors
- Pool exhaustion: graceful handling
- RosterAssigner called for every team
- draft_results.csv written with correct format
- Overall pick numbering
"""

import csv
import random
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from src.league.offseason.snake_draft import SnakeDraft, ROUNDS

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

MINIMAL_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    bats TEXT NOT NULL,
    throws TEXT NOT NULL,
    position TEXT
);

CREATE TABLE IF NOT EXISTS player_skills (
    player_id TEXT PRIMARY KEY,
    age INTEGER NOT NULL DEFAULT 17,
    clutch INTEGER NOT NULL DEFAULT 50,
    speed INTEGER NOT NULL DEFAULT 50,
    power INTEGER NOT NULL DEFAULT 50,
    eye INTEGER NOT NULL DEFAULT 50,
    contact INTEGER NOT NULL DEFAULT 50,
    base_running INTEGER NOT NULL DEFAULT 50,
    bunting INTEGER NOT NULL DEFAULT 50,
    catching INTEGER NOT NULL DEFAULT 50,
    infield INTEGER NOT NULL DEFAULT 50,
    outfield INTEGER NOT NULL DEFAULT 50,
    arm INTEGER NOT NULL DEFAULT 50,
    accuracy INTEGER NOT NULL DEFAULT 50,
    stamina INTEGER NOT NULL DEFAULT 50,
    recovery INTEGER NOT NULL DEFAULT 50,
    ground_balls INTEGER NOT NULL DEFAULT 50,
    strikes INTEGER NOT NULL DEFAULT 50,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS player_status (
    player_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN (
        'unassigned', '26man', '40man', 'minors', 'free_agent', 'prospect'
    )),
    since TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    mascot TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_players (
    team_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    PRIMARY KEY (team_id, player_id)
);

CREATE TABLE IF NOT EXISTS seasons (
    id TEXT PRIMARY KEY,
    year INTEGER
);

CREATE TABLE IF NOT EXISTS leagues (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS league_season_teams (
    league_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    PRIMARY KEY (league_id, season_id, team_id)
);

CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    series_id TEXT,
    home_team_id TEXT NOT NULL,
    away_team_id TEXT NOT NULL,
    completed INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS team_game_stats (
    game_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    win INTEGER,
    loss INTEGER,
    PRIMARY KEY (game_id, team_id)
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(MINIMAL_SCHEMA)
    yield connection
    connection.close()


@pytest.fixture
def rng():
    return random.Random(42)


@pytest.fixture
def draft(conn, rng):
    return SnakeDraft(conn, rng)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_player_counter = 0


def insert_team(conn, team_id, city="Test", mascot="Team"):
    conn.execute(
        "INSERT OR IGNORE INTO teams (id, city, mascot) VALUES (?, ?, ?)",
        (team_id, city, mascot),
    )
    conn.commit()


def insert_season(conn, season_id, year=2026):
    conn.execute(
        "INSERT OR IGNORE INTO seasons (id, year) VALUES (?, ?)",
        (season_id, year),
    )
    conn.commit()


def insert_league_season_team(conn, season_id, team_id, league_id="league-1"):
    conn.execute(
        "INSERT OR IGNORE INTO leagues (id, name) VALUES (?, ?)",
        (league_id, "Test League"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO league_season_teams (league_id, season_id, team_id) VALUES (?, ?, ?)",
        (league_id, season_id, team_id),
    )
    conn.commit()


def insert_game_result(conn, season_id, team_id, wins, losses):
    """Insert game rows to represent a team's record."""
    for i in range(wins):
        game_id = f"game-{team_id}-w{i}"
        conn.execute(
            "INSERT OR IGNORE INTO games (id, season_id, home_team_id, away_team_id) VALUES (?, ?, ?, ?)",
            (game_id, season_id, team_id, "dummy"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO team_game_stats (game_id, team_id, win, loss) VALUES (?, ?, 1, 0)",
            (game_id, team_id),
        )
    for i in range(losses):
        game_id = f"game-{team_id}-l{i}"
        conn.execute(
            "INSERT OR IGNORE INTO games (id, season_id, home_team_id, away_team_id) VALUES (?, ?, ?, ?)",
            (game_id, season_id, team_id, "dummy"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO team_game_stats (game_id, team_id, win, loss) VALUES (?, ?, 0, 1)",
            (game_id, team_id),
        )
    conn.commit()


def insert_prospect(conn, player_id, team_id=None, rating_skills=None):
    """Insert a prospect player, optionally on a team."""
    conn.execute(
        "INSERT OR IGNORE INTO players (id, first_name, last_name, bats, throws, position) VALUES (?,?,?,?,?,?)",
        (player_id, "Test", "Player", "R", "R", "of"),
    )
    skills = rating_skills or {}
    conn.execute(
        """INSERT OR IGNORE INTO player_skills
           (player_id, age, strikes, stamina, recovery, accuracy, clutch,
            speed, power, arm, eye, contact, base_running,
            bunting, catching, infield, outfield, ground_balls)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            player_id,
            20,
            skills.get("strikes", 50),
            skills.get("stamina", 50),
            skills.get("recovery", 50),
            skills.get("accuracy", 50),
            skills.get("clutch", 50),
            skills.get("speed", 50),
            skills.get("power", 50),
            skills.get("arm", 50),
            skills.get("eye", 50),
            skills.get("contact", 50),
            skills.get("base_running", 50),
            skills.get("bunting", 50),
            skills.get("catching", 50),
            skills.get("infield", 50),
            skills.get("outfield", 50),
            skills.get("ground_balls", 50),
        ),
    )
    conn.execute(
        "INSERT OR IGNORE INTO player_status (player_id, status, since) VALUES (?, 'prospect', '2025-01-01')",
        (player_id,),
    )
    if team_id:
        conn.execute(
            "INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)",
            (team_id, player_id),
        )
    conn.commit()


def setup_basic_draft(conn, n_teams=4, n_prospects=200, season_id="season-1"):
    """Set up a minimal but complete draft scenario."""
    insert_season(conn, season_id)

    teams = []
    for i in range(n_teams):
        team_id = f"team-{i}"
        insert_team(conn, team_id, city=f"City{i}", mascot=f"Team{i}")
        insert_league_season_team(conn, season_id, team_id)
        # Vary records: team-0 worst, team-(n-1) best
        wins = i * 10
        losses = (n_teams - 1 - i) * 10
        insert_game_result(conn, season_id, team_id, wins, losses)
        teams.append(team_id)

    for j in range(n_prospects):
        insert_prospect(conn, f"prospect-{j}")

    return teams


# ---------------------------------------------------------------------------
# _build_draft_order
# ---------------------------------------------------------------------------


class TestBuildDraftOrder:
    def test_worst_record_first(self, conn, draft):
        insert_season(conn, "s1")
        insert_team(conn, "t-good", "Good", "Team")
        insert_team(conn, "t-bad", "Bad", "Team")
        insert_league_season_team(conn, "s1", "t-good")
        insert_league_season_team(conn, "s1", "t-bad")
        insert_game_result(conn, "s1", "t-good", wins=80, losses=20)
        insert_game_result(conn, "s1", "t-bad", wins=20, losses=80)

        order = draft._build_draft_order("s1")

        assert order[0]["team_id"] == "t-bad"
        assert order[1]["team_id"] == "t-good"

    def test_no_games_team_goes_last(self, conn, draft):
        insert_season(conn, "s1")
        insert_team(conn, "t-played", "Played", "Team")
        insert_team(conn, "t-new", "New", "Team")
        insert_league_season_team(conn, "s1", "t-played")
        insert_league_season_team(conn, "s1", "t-new")
        insert_game_result(conn, "s1", "t-played", wins=50, losses=50)
        # t-new has no games

        order = draft._build_draft_order("s1")

        assert order[-1]["team_id"] == "t-new"

    def test_returns_all_teams(self, conn, draft):
        insert_season(conn, "s1")
        for i in range(6):
            insert_team(conn, f"t{i}", f"City{i}", "Team")
            insert_league_season_team(conn, "s1", f"t{i}")
            insert_game_result(conn, "s1", f"t{i}", wins=i * 10, losses=(5 - i) * 10)

        order = draft._build_draft_order("s1")
        assert len(order) == 6

    def test_includes_team_names(self, conn, draft):
        insert_season(conn, "s1")
        insert_team(conn, "t1", "Boston", "Red Sox")
        insert_league_season_team(conn, "s1", "t1")
        insert_game_result(conn, "s1", "t1", wins=50, losses=50)

        order = draft._build_draft_order("s1")
        assert order[0]["team_name"] == "Boston Red Sox"

    def test_equal_records_stable(self, conn, draft):
        """Teams with identical records should all be included."""
        insert_season(conn, "s1")
        for i in range(4):
            insert_team(conn, f"t{i}", f"City{i}", "Team")
            insert_league_season_team(conn, "s1", f"t{i}")
            insert_game_result(conn, "s1", f"t{i}", wins=50, losses=50)

        order = draft._build_draft_order("s1")
        assert len(order) == 4


# ---------------------------------------------------------------------------
# _load_draft_pool
# ---------------------------------------------------------------------------


class TestLoadDraftPool:
    def test_returns_unattached_prospects(self, conn, draft):
        insert_prospect(conn, "p1")
        insert_prospect(conn, "p2")
        pool = draft._load_draft_pool()
        ids = {p.id for p in pool}
        assert {"p1", "p2"} == ids

    def test_excludes_rostered_prospects(self, conn, draft):
        insert_team(conn, "t1", "A", "B")
        insert_prospect(conn, "p1", team_id="t1")
        insert_prospect(conn, "p2")
        pool = draft._load_draft_pool()
        assert all(p.id != "p1" for p in pool)

    def test_excludes_non_prospects(self, conn, draft):
        conn.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws) VALUES ('fa1','A','B','R','R')"
        )
        conn.execute(
            "INSERT INTO player_skills (player_id, age, clutch, speed, power, eye, contact, base_running, bunting, catching, infield, outfield, arm, accuracy, stamina, recovery, ground_balls, strikes) VALUES ('fa1',30,50,50,50,50,50,50,50,50,50,50,50,50,50,50,50,50)"
        )
        conn.execute(
            "INSERT INTO player_status (player_id, status, since) VALUES ('fa1','free_agent','2025-01-01')"
        )
        conn.commit()
        pool = draft._load_draft_pool()
        assert all(p.id != "fa1" for p in pool)

    def test_empty_pool(self, conn, draft):
        pool = draft._load_draft_pool()
        assert pool == []


# ---------------------------------------------------------------------------
# _rate_pool
# ---------------------------------------------------------------------------


class TestRatePool:
    def test_sorted_best_first(self, conn, draft):
        insert_prospect(
            conn, "p-low", rating_skills={"strikes": 10, "stamina": 10, "recovery": 10}
        )
        insert_prospect(
            conn, "p-high", rating_skills={"strikes": 90, "stamina": 90, "recovery": 90}
        )

        pool = draft._load_draft_pool()
        rated = draft._rate_pool(pool)

        assert rated[0][0].id == "p-high"
        assert rated[-1][0].id == "p-low"

    def test_ratings_are_integers(self, conn, draft):
        insert_prospect(conn, "p1")
        pool = draft._load_draft_pool()
        rated = draft._rate_pool(pool)
        for _, rating in rated:
            assert isinstance(rating, int)

    def test_ratings_in_range(self, conn, draft):
        for i in range(10):
            insert_prospect(conn, f"p{i}")
        pool = draft._load_draft_pool()
        rated = draft._rate_pool(pool)
        for _, rating in rated:
            assert 0 <= rating <= 100


# ---------------------------------------------------------------------------
# _run_snake
# ---------------------------------------------------------------------------


class TestRunSnake:
    def test_snake_round_1_worst_to_best(self, conn, draft):
        """Round 1 picks should follow worst→best order."""
        insert_season(conn, "s1")
        setup_basic_draft(conn, n_teams=4, n_prospects=200, season_id="s1")

        order = draft._build_draft_order("s1")
        pool = draft._load_draft_pool()
        rated = draft._rate_pool(pool)

        picks = draft._run_snake(order, rated)

        round_1 = [p for p in picks if p.round == 1]
        assert [p.team_id for p in round_1] == [t["team_id"] for t in order]

    def test_snake_round_2_best_to_worst(self, conn, draft):
        """Round 2 picks should follow best→worst order."""
        setup_basic_draft(conn, n_teams=4, n_prospects=200, season_id="s1")

        order = draft._build_draft_order("s1")
        pool = draft._load_draft_pool()
        rated = draft._rate_pool(pool)

        picks = draft._run_snake(order, rated)

        round_2 = [p for p in picks if p.round == 2]
        assert [p.team_id for p in round_2] == [t["team_id"] for t in reversed(order)]

    def test_correct_total_picks(self, conn, draft):
        n_teams = 4
        setup_basic_draft(conn, n_teams=n_teams, n_prospects=500, season_id="s1")

        order = draft._build_draft_order("s1")
        pool = draft._load_draft_pool()
        rated = draft._rate_pool(pool)

        picks = draft._run_snake(order, rated)

        assert len(picks) == ROUNDS * n_teams

    def test_overall_pick_numbers_sequential(self, conn, draft):
        setup_basic_draft(conn, n_teams=4, n_prospects=200, season_id="s1")

        order = draft._build_draft_order("s1")
        pool = draft._load_draft_pool()
        rated = draft._rate_pool(pool)

        picks = draft._run_snake(order, rated)

        pick_numbers = [p.pick for p in picks]
        assert pick_numbers == list(range(1, len(picks) + 1))

    def test_no_player_drafted_twice(self, conn, draft):
        setup_basic_draft(conn, n_teams=4, n_prospects=200, season_id="s1")

        order = draft._build_draft_order("s1")
        pool = draft._load_draft_pool()
        rated = draft._rate_pool(pool)

        picks = draft._run_snake(order, rated)

        player_ids = [p.player_id for p in picks]
        assert len(player_ids) == len(set(player_ids))

    def test_drafted_players_added_to_team_players(self, conn, draft):
        setup_basic_draft(conn, n_teams=4, n_prospects=200, season_id="s1")

        order = draft._build_draft_order("s1")
        pool = draft._load_draft_pool()
        rated = draft._rate_pool(pool)

        picks = draft._run_snake(order, rated)

        for pick in picks:
            row = conn.execute(
                "SELECT 1 FROM team_players WHERE team_id = ? AND player_id = ?",
                (pick.team_id, pick.player_id),
            ).fetchone()
            assert row is not None, f"Player {pick.player_id} not in team_players"

    def test_drafted_players_status_minors(self, conn, draft):
        setup_basic_draft(conn, n_teams=4, n_prospects=200, season_id="s1")

        order = draft._build_draft_order("s1")
        pool = draft._load_draft_pool()
        rated = draft._rate_pool(pool)

        picks = draft._run_snake(order, rated)

        for pick in picks[:20]:  # spot check first 20
            row = conn.execute(
                "SELECT status FROM player_status WHERE player_id = ?",
                (pick.player_id,),
            ).fetchone()
            assert row["status"] == "minors"

    def test_best_prospect_goes_first_overall(self, conn, draft):
        """Pick 1 should be the highest rated prospect."""
        setup_basic_draft(conn, n_teams=4, n_prospects=200, season_id="s1")
        # Insert a standout prospect
        insert_prospect(
            conn,
            "superstar",
            rating_skills={
                "strikes": 99,
                "stamina": 99,
                "recovery": 99,
                "speed": 99,
                "power": 99,
            },
        )

        order = draft._build_draft_order("s1")
        pool = draft._load_draft_pool()
        rated = draft._rate_pool(pool)

        picks = draft._run_snake(order, rated)

        assert picks[0].player_id == "superstar"

    def test_pool_exhaustion_returns_early(self, conn, draft):
        """If pool runs out before all rounds complete, return gracefully."""
        setup_basic_draft(conn, n_teams=4, n_prospects=10, season_id="s1")

        order = draft._build_draft_order("s1")
        pool = draft._load_draft_pool()
        rated = draft._rate_pool(pool)

        picks = draft._run_snake(order, rated)

        assert len(picks) == len(pool)  # only as many picks as available players

    def test_empty_pool_returns_empty(self, conn, draft):
        setup_basic_draft(conn, n_teams=4, n_prospects=0, season_id="s1")

        order = draft._build_draft_order("s1")
        picks = draft._run_snake(order, [])

        assert picks == []


# ---------------------------------------------------------------------------
# run() — integration
# ---------------------------------------------------------------------------


class TestSnakeDraftRun:
    def test_run_returns_picks(self, conn, draft, tmp_path):
        setup_basic_draft(conn, n_teams=4, n_prospects=200, season_id="s1")
        with patch("src.league.offseason.snake_draft.TEAM_FILES_DIR", tmp_path):
            picks = draft.run_snake_draft("s1", 2027)
        assert len(picks) == ROUNDS * 4

    def test_run_writes_results_csv(self, conn, draft, tmp_path):
        setup_basic_draft(conn, n_teams=4, n_prospects=200)
        with patch("src.league.offseason.snake_draft.TEAM_FILES_DIR", tmp_path):
            draft.run_snake_draft("s1", 2027)
        assert (tmp_path / "2027" / "draft_results.csv").exists()

    def test_results_csv_has_correct_columns(self, conn, draft, tmp_path):
        setup_basic_draft(conn, n_teams=4, n_prospects=200)
        with patch("src.league.offseason.snake_draft.TEAM_FILES_DIR", tmp_path):
            draft.run_snake_draft("s1", 2027)

        with open(tmp_path / "2027" / "draft_results.csv", newline="") as f:
            headers = csv.DictReader(f).fieldnames

        for col in [
            "Round",
            "Pick",
            "Team",
            "Player",
            "Age",
            "Position",
            "Prospect Rating",
        ]:
            assert col in headers

    def test_results_csv_row_count(self, conn, draft, tmp_path):
        setup_basic_draft(conn, n_teams=4, n_prospects=200)
        with patch("src.league.offseason.snake_draft.TEAM_FILES_DIR", tmp_path):
            picks = draft.run_snake_draft("s1", 2027)

        with open(tmp_path / "2027" / "draft_results.csv", newline="") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == len(picks)

    def test_empty_pool_returns_empty(self, conn, draft, tmp_path):
        """Draft with no prospects should return empty and not crash."""
        insert_season(conn, "s1")
        insert_team(conn, "t1", "A", "B")
        insert_league_season_team(conn, "s1", "t1")
        insert_game_result(conn, "s1", "t1", 50, 50)

        with patch("src.league.offseason.snake_draft.TEAM_FILES_DIR", tmp_path):
            picks = draft.run_snake_draft("s1", 2027)

        assert picks == []

    def test_roster_assigner_called_for_each_team(self, conn, rng, tmp_path):
        setup_basic_draft(conn, n_teams=4, n_prospects=200, season_id="s1")

        with patch("src.league.offseason.snake_draft.RosterAssigner") as MockAssigner:
            mock_instance = MagicMock()
            mock_instance.assign.return_value = {}
            MockAssigner.return_value = mock_instance

            draft = SnakeDraft(conn, rng)
            with patch("src.league.offseason.snake_draft.TEAM_FILES_DIR", tmp_path):
                draft.run_snake_draft("s1", 2027)

        assert mock_instance.assign.call_count == 4
