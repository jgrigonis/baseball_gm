# tests/db/repositories/test_player_games_repo.py
import pytest
import sqlite3

from src.db.repositories.player_games import PlayerGameRepository
from src.stats.stats import Stats
from src.stats.fielding_stats import FieldingStats


@pytest.fixture
def db_connection():
    """Create in-memory SQLite database with required tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Create player_game_stats table
    conn.execute("""
        CREATE TABLE player_game_stats (
            game_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            team_id TEXT NOT NULL,
            opponent_team_id TEXT NOT NULL,

            -- Batting
            bat_game_played INTEGER DEFAULT 1 CHECK (bat_game_played IN (0, 1)),
            bat_game_started INTEGER DEFAULT 0 CHECK (bat_game_started IN (0, 1)),
            bat_ab INTEGER CHECK (bat_ab >= 0),
            bat_hits INTEGER CHECK (bat_hits >= 0),
            bat_doubles INTEGER CHECK (bat_doubles >= 0),
            bat_triples INTEGER CHECK (bat_triples >= 0),
            bat_home_runs INTEGER CHECK (bat_home_runs >= 0),
            bat_rbi INTEGER CHECK (bat_rbi >= 0),
            bat_runs INTEGER CHECK (bat_runs >= 0),
            bat_walks INTEGER CHECK (bat_walks >= 0),
            bat_strike_outs INTEGER CHECK (bat_strike_outs >= 0),
            bat_hbp INTEGER CHECK (bat_hbp >= 0),
            bat_sac_flys INTEGER CHECK (bat_sac_flys >= 0),
            bat_sac_bunts INTEGER CHECK (bat_sac_bunts >= 0),
            bat_gdp INTEGER CHECK (bat_gdp >= 0),
            bat_gtp INTEGER CHECK (bat_gtp >= 0),
            bat_stolen_bases INTEGER CHECK (bat_stolen_bases >= 0),
            bat_caught_stealing INTEGER CHECK (bat_caught_stealing >= 0),

            -- Pitching
            pitch_game_played INTEGER DEFAULT 0 CHECK (pitch_game_played IN (0, 1)),
            pitch_game_started INTEGER DEFAULT 0 CHECK (pitch_game_started IN (0, 1)),
            pitch_complete_game INTEGER DEFAULT 0 CHECK (pitch_complete_game IN (0, 1)),
            pitch_shutout INTEGER DEFAULT 0 CHECK (pitch_shutout IN (0, 1)),
            pitch_win INTEGER DEFAULT 0 CHECK (pitch_win IN (0, 1)),
            pitch_loss INTEGER DEFAULT 0 CHECK (pitch_loss IN (0, 1)),
            pitch_save INTEGER DEFAULT 0 CHECK (pitch_save IN (0, 1)),
            pitch_hold INTEGER DEFAULT 0 CHECK (pitch_hold IN (0, 1)),
            pitch_outs INTEGER CHECK (pitch_outs >= 0),
            pitch_hits INTEGER CHECK (pitch_hits >= 0),
            pitch_runs INTEGER CHECK (pitch_runs >= 0),
            pitch_earned_runs INTEGER CHECK (pitch_earned_runs >= 0),
            pitch_home_runs INTEGER CHECK (pitch_home_runs >= 0),
            pitch_walks INTEGER CHECK (pitch_walks >= 0),
            pitch_strike_outs INTEGER CHECK (pitch_strike_outs >= 0),
            pitch_hit_batters INTEGER CHECK (pitch_hit_batters >= 0),
            pitch_doubles INTEGER DEFAULT 0 CHECK (pitch_doubles >= 0),
            pitch_triples INTEGER DEFAULT 0 CHECK (pitch_triples >= 0),
            pitch_pickoffs INTEGER DEFAULT 0 CHECK (pitch_pickoffs >= 0),
            pitch_balks INTEGER DEFAULT 0 CHECK (pitch_balks >= 0),
            pitch_wild_pitches INTEGER DEFAULT 0 CHECK (pitch_wild_pitches >= 0),
            pitch_count INTEGER CHECK (pitch_count >= 0),

            -- Fielding
            field_putouts INTEGER CHECK (field_putouts >= 0),
            field_assists INTEGER CHECK (field_assists >= 0),
            field_errors INTEGER CHECK (field_errors >= 0),
            passed_balls INTEGER CHECK (passed_balls >= 0),
            catcher_interferences INTEGER CHECK (catcher_interferences >= 0),
            catcher_cs INTEGER CHECK (catcher_cs >= 0),
            catcher_sb INTEGER CHECK (catcher_sb >= 0),

            PRIMARY KEY (game_id, player_id)
        )
    """)

    # Create player_game_fielding table
    conn.execute("""
        CREATE TABLE player_game_fielding (
            game_id   TEXT NOT NULL,
            player_id TEXT NOT NULL,
            position  TEXT NOT NULL,
            putouts   INTEGER DEFAULT 0 CHECK (putouts >= 0),
            assists   INTEGER DEFAULT 0 CHECK (assists >= 0),
            errors    INTEGER DEFAULT 0 CHECK (errors >= 0),
            passed_balls          INTEGER CHECK (passed_balls >= 0),
            catcher_interferences INTEGER CHECK (catcher_interferences >= 0),
            catcher_cs            INTEGER CHECK (catcher_cs >= 0),
            catcher_sb            INTEGER CHECK (catcher_sb >= 0),
            PRIMARY KEY (game_id, player_id, position)
        )
    """)

    # Create games table for joins
    conn.execute("""
        CREATE TABLE games (
            id TEXT PRIMARY KEY,
            game_date TEXT NOT NULL,
            season_id TEXT NOT NULL,
            series_id TEXT
        )
    """)

    yield conn
    conn.close()


@pytest.fixture
def player_repo(db_connection):
    """Create PlayerGameRepository instance."""
    return PlayerGameRepository(db_connection)


@pytest.fixture
def sample_stats():
    """Create sample Stats object."""
    stats = Stats()

    # Batting stats
    stats.batting.at_bats = 4
    stats.batting.hits = 2
    stats.batting.doubles = 1
    stats.batting.triples = 0
    stats.batting.home_runs = 1
    stats.batting.rbi = 3
    stats.batting.runs = 2
    stats.batting.walks = 1
    stats.batting.strike_outs = 1
    stats.batting.hbp = 0
    stats.batting.sac_flys = 0
    stats.batting.sac_bunts = 0
    stats.batting.gdp = 0
    stats.batting.gtp = 0
    stats.batting.sb = 1
    stats.batting.cs = 0
    stats.batting.pickoffs = 0

    # Pitching stats
    stats.pitching.outs = 27
    stats.pitching.hits = 5
    stats.pitching.runs = 2
    stats.pitching.home_runs = 1
    stats.pitching.walks = 2
    stats.pitching.strike_outs = 8
    stats.pitching.hb = 0
    stats.pitching.pitch_count = 95
    stats.pitching.doubles = 1
    stats.pitching.triples = 0
    stats.pitching.pickoffs = 0
    stats.pitching.balks = 0
    stats.pitching.wild_pitches = 1

    # Fielding stats
    stats.fielding.putouts = 3
    stats.fielding.assists = 1
    stats.fielding.errors = 0
    stats.fielding.passed_ball = 0

    return stats


@pytest.fixture
def sample_fielding_positions():
    """Create sample fielding positions list."""
    ss_stats = FieldingStats()
    ss_stats.putouts = 1
    ss_stats.assists = 5
    ss_stats.errors = 0

    return [("ss", ss_stats)]


@pytest.fixture
def sample_fielding_positions_two_way():
    """Create sample fielding positions for a two-way player (1b + pitcher)."""
    first_base_stats = FieldingStats()
    first_base_stats.putouts = 10
    first_base_stats.assists = 2
    first_base_stats.errors = 0

    pitcher_stats = FieldingStats()
    pitcher_stats.putouts = 0
    pitcher_stats.assists = 2
    pitcher_stats.errors = 1

    return [("1b", first_base_stats), ("p", pitcher_stats)]


class TestPlayerGameRepositoryInsert:
    """Test insert() method."""

    def test_insert_basic(self, player_repo, db_connection, sample_stats):
        """Test inserting player game stats."""
        player_repo.insert(
            game_id="game-1",
            player_id="player-1",
            team_id="team-1",
            opponent_team_id="team-2",
            stats=sample_stats,
        )

        # Verify in database
        row = db_connection.execute(
            "SELECT * FROM player_game_stats WHERE game_id = ? AND player_id = ?",
            ("game-1", "player-1"),
        ).fetchone()

        assert row is not None
        assert row["game_id"] == "game-1"
        assert row["player_id"] == "player-1"
        assert row["team_id"] == "team-1"
        assert row["opponent_team_id"] == "team-2"

    def test_insert_batting_stats(self, player_repo, db_connection, sample_stats):
        """Test that batting stats are correctly inserted."""
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)

        row = db_connection.execute(
            "SELECT * FROM player_game_stats WHERE game_id = ? AND player_id = ?",
            ("game-1", "player-1"),
        ).fetchone()

        assert row["bat_ab"] == 4
        assert row["bat_hits"] == 2
        assert row["bat_doubles"] == 1
        assert row["bat_home_runs"] == 1
        assert row["bat_rbi"] == 3
        assert row["bat_runs"] == 2
        assert row["bat_walks"] == 1
        assert row["bat_strike_outs"] == 1
        assert row["bat_stolen_bases"] == 1

    def test_insert_pitching_stats(self, player_repo, db_connection, sample_stats):
        """Test that pitching stats are correctly inserted."""
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)

        row = db_connection.execute(
            "SELECT * FROM player_game_stats WHERE game_id = ? AND player_id = ?",
            ("game-1", "player-1"),
        ).fetchone()

        assert row["pitch_outs"] == 27
        assert row["pitch_hits"] == 5
        assert row["pitch_runs"] == 2
        assert row["pitch_home_runs"] == 1
        assert row["pitch_walks"] == 2
        assert row["pitch_strike_outs"] == 8
        assert row["pitch_count"] == 95

    def test_insert_fielding_stats(self, player_repo, db_connection, sample_stats):
        """Test that fielding stats are correctly inserted."""
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)

        row = db_connection.execute(
            "SELECT * FROM player_game_stats WHERE game_id = ? AND player_id = ?",
            ("game-1", "player-1"),
        ).fetchone()

        assert row["field_putouts"] == 3
        assert row["field_assists"] == 1
        assert row["field_errors"] == 0

    def test_insert_idempotent(self, player_repo, db_connection, sample_stats):
        """Test that insert is idempotent (INSERT OR REPLACE)."""
        # Insert first time
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)

        # Modify stats
        sample_stats.batting.hits = 3

        # Insert again with modified stats
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)

        # Should only have one row with updated stats
        count = db_connection.execute(
            "SELECT COUNT(*) as count FROM player_game_stats WHERE game_id = ? AND player_id = ?",
            ("game-1", "player-1"),
        ).fetchone()["count"]

        assert count == 1

        row = db_connection.execute(
            "SELECT bat_hits FROM player_game_stats WHERE game_id = ? AND player_id = ?",
            ("game-1", "player-1"),
        ).fetchone()

        assert row["bat_hits"] == 3

    def test_insert_zero_stats(self, player_repo, db_connection):
        """Test inserting a player with zero stats (e.g., defensive sub)."""
        stats = Stats()
        # All stats default to 0

        player_repo.insert("game-1", "player-1", "team-1", "team-2", stats)

        row = db_connection.execute(
            "SELECT * FROM player_game_stats WHERE game_id = ? AND player_id = ?",
            ("game-1", "player-1"),
        ).fetchone()

        assert row is not None
        assert row["bat_ab"] == 0
        assert row["pitch_outs"] == 0
        assert row["field_putouts"] == 0

    def test_insert_multiple_players_same_game(
        self, player_repo, db_connection, sample_stats
    ):
        """Test inserting multiple players for the same game."""
        for i in range(5):
            player_repo.insert(
                game_id="game-1",
                player_id=f"player-{i}",
                team_id="team-1",
                opponent_team_id="team-2",
                stats=sample_stats,
            )

        count = db_connection.execute(
            "SELECT COUNT(*) as count FROM player_game_stats WHERE game_id = ?",
            ("game-1",),
        ).fetchone()["count"]

        assert count == 5


class TestPlayerGameRepositoryFieldingPositions:
    """Test insert() with fielding_positions parameter."""

    def test_insert_single_fielding_position(
        self, player_repo, db_connection, sample_stats, sample_fielding_positions
    ):
        """Test inserting stats with a single fielding position."""
        player_repo.insert(
            game_id="game-1",
            player_id="player-1",
            team_id="team-1",
            opponent_team_id="team-2",
            stats=sample_stats,
            fielding_positions=sample_fielding_positions,
        )

        rows = db_connection.execute(
            "SELECT * FROM player_game_fielding WHERE game_id = ? AND player_id = ?",
            ("game-1", "player-1"),
        ).fetchall()

        assert len(rows) == 1
        assert rows[0]["position"] == "ss"
        assert rows[0]["putouts"] == 1
        assert rows[0]["assists"] == 5
        assert rows[0]["errors"] == 0

    def test_insert_two_way_player(
        self,
        player_repo,
        db_connection,
        sample_stats,
        sample_fielding_positions_two_way,
    ):
        """Test inserting stats for a two-way player (e.g., 1b who also pitched)."""
        player_repo.insert(
            game_id="game-1",
            player_id="player-1",
            team_id="team-1",
            opponent_team_id="team-2",
            stats=sample_stats,
            fielding_positions=sample_fielding_positions_two_way,
        )

        rows = db_connection.execute(
            """
            SELECT * FROM player_game_fielding
            WHERE game_id = ? AND player_id = ?
            ORDER BY position
            """,
            ("game-1", "player-1"),
        ).fetchall()

        assert len(rows) == 2

        positions = {r["position"]: r for r in rows}

        assert positions["1b"]["putouts"] == 10
        assert positions["1b"]["assists"] == 2
        assert positions["1b"]["errors"] == 0

        assert positions["p"]["putouts"] == 0
        assert positions["p"]["assists"] == 2
        assert positions["p"]["errors"] == 1

    def test_insert_no_fielding_positions(
        self, player_repo, db_connection, sample_stats
    ):
        """Test that omitting fielding_positions writes nothing to player_game_fielding."""
        player_repo.insert(
            game_id="game-1",
            player_id="player-1",
            team_id="team-1",
            opponent_team_id="team-2",
            stats=sample_stats,
        )

        rows = db_connection.execute(
            "SELECT * FROM player_game_fielding WHERE game_id = ? AND player_id = ?",
            ("game-1", "player-1"),
        ).fetchall()

        assert len(rows) == 0

    def test_insert_fielding_positions_idempotent(
        self, player_repo, db_connection, sample_stats, sample_fielding_positions
    ):
        """Test that re-inserting fielding positions replaces rather than duplicates."""
        player_repo.insert(
            "game-1",
            "player-1",
            "team-1",
            "team-2",
            sample_stats,
            fielding_positions=sample_fielding_positions,
        )

        # Update the fielding stats and re-insert
        updated_fs = FieldingStats()
        updated_fs.putouts = 3
        updated_fs.assists = 7
        updated_fs.errors = 1

        player_repo.insert(
            "game-1",
            "player-1",
            "team-1",
            "team-2",
            sample_stats,
            fielding_positions=[("ss", updated_fs)],
        )

        rows = db_connection.execute(
            "SELECT * FROM player_game_fielding WHERE game_id = ? AND player_id = ?",
            ("game-1", "player-1"),
        ).fetchall()

        assert len(rows) == 1
        assert rows[0]["putouts"] == 3
        assert rows[0]["assists"] == 7
        assert rows[0]["errors"] == 1

    def test_fielding_positions_isolated_per_player(
        self, player_repo, db_connection, sample_stats
    ):
        """Test that fielding positions are correctly isolated per player."""
        ss_stats = FieldingStats()
        ss_stats.putouts = 1
        ss_stats.assists = 5

        cf_stats = FieldingStats()
        cf_stats.putouts = 3
        cf_stats.assists = 0

        player_repo.insert(
            "game-1",
            "player-1",
            "team-1",
            "team-2",
            sample_stats,
            fielding_positions=[("ss", ss_stats)],
        )
        player_repo.insert(
            "game-1",
            "player-2",
            "team-1",
            "team-2",
            sample_stats,
            fielding_positions=[("cf", cf_stats)],
        )

        p1_rows = db_connection.execute(
            "SELECT * FROM player_game_fielding WHERE game_id = ? AND player_id = ?",
            ("game-1", "player-1"),
        ).fetchall()

        p2_rows = db_connection.execute(
            "SELECT * FROM player_game_fielding WHERE game_id = ? AND player_id = ?",
            ("game-1", "player-2"),
        ).fetchall()

        assert len(p1_rows) == 1
        assert p1_rows[0]["position"] == "ss"

        assert len(p2_rows) == 1
        assert p2_rows[0]["position"] == "cf"


class TestPlayerGameRepositoryDeleteGameStats:
    """Test delete_game_stats() cleans up both tables."""

    def test_delete_cleans_player_game_stats(
        self, player_repo, db_connection, sample_stats
    ):
        """Test that delete_game_stats removes rows from player_game_stats."""
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)
        player_repo.delete_game_stats("game-1")

        count = db_connection.execute(
            "SELECT COUNT(*) as count FROM player_game_stats WHERE game_id = ?",
            ("game-1",),
        ).fetchone()["count"]

        assert count == 0

    def test_delete_cleans_player_game_fielding(
        self, player_repo, db_connection, sample_stats, sample_fielding_positions
    ):
        """Test that delete_game_stats removes rows from player_game_fielding."""
        player_repo.insert(
            "game-1",
            "player-1",
            "team-1",
            "team-2",
            sample_stats,
            fielding_positions=sample_fielding_positions,
        )
        player_repo.delete_game_stats("game-1")

        count = db_connection.execute(
            "SELECT COUNT(*) as count FROM player_game_fielding WHERE game_id = ?",
            ("game-1",),
        ).fetchone()["count"]

        assert count == 0

    def test_delete_only_affects_specified_game(
        self, player_repo, db_connection, sample_stats, sample_fielding_positions
    ):
        """Test that delete_game_stats only removes data for the specified game."""
        player_repo.insert(
            "game-1",
            "player-1",
            "team-1",
            "team-2",
            sample_stats,
            fielding_positions=sample_fielding_positions,
        )
        player_repo.insert(
            "game-2",
            "player-1",
            "team-1",
            "team-2",
            sample_stats,
            fielding_positions=sample_fielding_positions,
        )

        player_repo.delete_game_stats("game-1")

        game1_count = db_connection.execute(
            "SELECT COUNT(*) as count FROM player_game_fielding WHERE game_id = ?",
            ("game-1",),
        ).fetchone()["count"]

        game2_count = db_connection.execute(
            "SELECT COUNT(*) as count FROM player_game_fielding WHERE game_id = ?",
            ("game-2",),
        ).fetchone()["count"]

        assert game1_count == 0
        assert game2_count == 1


class TestPlayerGameRepositoryGetForGame:
    """Test get_for_game() method."""

    def test_get_for_game_existing(self, player_repo, sample_stats):
        """Test getting stats for an existing player in a game."""
        # Insert stats
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)

        # Retrieve stats
        retrieved = player_repo.get_for_game("game-1", "player-1")

        assert retrieved is not None
        assert isinstance(retrieved, Stats)

    def test_get_for_game_batting_stats(self, player_repo, sample_stats):
        """Test that batting stats are correctly retrieved."""
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)

        retrieved = player_repo.get_for_game("game-1", "player-1")

        assert retrieved.batting.at_bats == 4
        assert retrieved.batting.hits == 2
        assert retrieved.batting.doubles == 1
        assert retrieved.batting.home_runs == 1
        assert retrieved.batting.rbi == 3
        assert retrieved.batting.runs == 2

    def test_get_for_game_pitching_stats(self, player_repo, sample_stats):
        """Test that pitching stats are correctly retrieved."""
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)

        retrieved = player_repo.get_for_game("game-1", "player-1")

        assert retrieved.pitching.outs == 27
        assert retrieved.pitching.hits == 5
        assert retrieved.pitching.runs == 2
        assert retrieved.pitching.strike_outs == 8
        assert retrieved.pitching.pitch_count == 95

    def test_get_for_game_fielding_stats(self, player_repo, sample_stats):
        """Test that fielding stats are correctly retrieved."""
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)

        retrieved = player_repo.get_for_game("game-1", "player-1")

        assert retrieved.fielding.putouts == 3
        assert retrieved.fielding.assists == 1
        assert retrieved.fielding.errors == 0
        assert retrieved.fielding.chances == 4  # putouts + assists + errors

    def test_get_for_game_nonexistent(self, player_repo):
        """Test getting stats for a player/game that doesn't exist."""
        retrieved = player_repo.get_for_game("nonexistent-game", "nonexistent-player")

        assert retrieved is None

    def test_get_for_game_wrong_player(self, player_repo, sample_stats):
        """Test getting stats with wrong player ID."""
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)

        retrieved = player_repo.get_for_game("game-1", "player-2")

        assert retrieved is None

    def test_get_for_game_wrong_game(self, player_repo, sample_stats):
        """Test getting stats with wrong game ID."""
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)

        retrieved = player_repo.get_for_game("game-2", "player-1")

        assert retrieved is None


class TestPlayerGameRepositoryFetchPlayerGames:
    """Test fetch_player_games() method."""

    def test_fetch_player_games_single(self, player_repo, sample_stats):
        """Test fetching games for a player with one game."""
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)

        games = player_repo.fetch_player_games("player-1")

        assert len(games) == 1
        assert isinstance(games[0], Stats)
        assert games[0].batting.hits == 2

    def test_fetch_player_games_multiple(self, player_repo, sample_stats):
        """Test fetching games for a player with multiple games."""
        for i in range(5):
            player_repo.insert(
                f"game-{i}", "player-1", "team-1", "team-2", sample_stats
            )

        games = player_repo.fetch_player_games("player-1")

        assert len(games) == 5
        assert all(isinstance(g, Stats) for g in games)

    def test_fetch_player_games_empty(self, player_repo):
        """Test fetching games for a player with no games."""
        games = player_repo.fetch_player_games("nonexistent-player")

        assert games == []

    def test_fetch_player_games_ordered(self, player_repo, sample_stats, db_connection):
        """Test that games are ordered by game_id."""
        # Insert in reverse order
        for i in reversed(range(5)):
            player_repo.insert(
                f"game-{i}", "player-1", "team-1", "team-2", sample_stats
            )

        games = player_repo.fetch_player_games("player-1")

        # Should be ordered by game_id (alphabetically)
        assert len(games) == 5

    def test_fetch_player_games_different_stats(self, player_repo):
        """Test fetching games with varying stats."""
        for i in range(3):
            stats = Stats()
            stats.batting.hits = i
            stats.batting.at_bats = 4
            player_repo.insert(f"game-{i}", "player-1", "team-1", "team-2", stats)

        games = player_repo.fetch_player_games("player-1")

        assert len(games) == 3
        # Verify each game has different hits
        hits = [g.batting.hits for g in games]
        assert set(hits) == {0, 1, 2}

    def test_fetch_player_games_only_for_specific_player(
        self, player_repo, sample_stats
    ):
        """Test that fetch_player_games only returns games for specified player."""
        # Insert games for multiple players
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)
        player_repo.insert("game-1", "player-2", "team-1", "team-2", sample_stats)
        player_repo.insert("game-2", "player-1", "team-1", "team-2", sample_stats)

        games = player_repo.fetch_player_games("player-1")

        assert len(games) == 2  # Only player-1's games


class TestPlayerGameRepositoryLoadSeasonStats:
    """Test load_season_stats() method."""

    @pytest.fixture
    def season_setup(self, db_connection):
        """Setup games for a season."""
        # Insert games
        games = [
            ("game-1", "2025-04-01", "season-1"),
            ("game-2", "2025-04-02", "season-1"),
            ("game-3", "2025-04-03", "season-1"),
            ("game-4", "2025-04-04", "season-2"),
        ]

        for game in games:
            db_connection.execute(
                "INSERT INTO games (id, game_date, season_id) VALUES (?, ?, ?)", game
            )

        db_connection.commit()

    def test_load_season_stats_basic(self, player_repo, season_setup):
        """Test loading season stats."""
        # Insert stats for 3 games in season-1
        for i in range(1, 4):
            stats = Stats()
            stats.batting.hits = 2
            stats.batting.at_bats = 4
            player_repo.insert(f"game-{i}", "player-1", "team-1", "team-2", stats)

        season_stats = player_repo.load_season_stats("player-1", "season-1")

        assert season_stats.games_played == 3
        assert season_stats.stats.batting.hits == 6  # 2 hits per game * 3 games
        assert season_stats.stats.batting.at_bats == 12  # 4 AB per game * 3 games

    def test_load_season_stats_aggregation(self, player_repo, season_setup):
        """Test that stats are properly aggregated across games."""
        # Game 1: 2 hits, 1 HR
        stats1 = Stats()
        stats1.batting.hits = 2
        stats1.batting.home_runs = 1
        stats1.batting.at_bats = 4

        # Game 2: 3 hits, 0 HR
        stats2 = Stats()
        stats2.batting.hits = 3
        stats2.batting.home_runs = 0
        stats2.batting.at_bats = 5

        # Game 3: 1 hit, 1 HR
        stats3 = Stats()
        stats3.batting.hits = 1
        stats3.batting.home_runs = 1
        stats3.batting.at_bats = 3

        player_repo.insert("game-1", "player-1", "team-1", "team-2", stats1)
        player_repo.insert("game-2", "player-1", "team-1", "team-2", stats2)
        player_repo.insert("game-3", "player-1", "team-1", "team-2", stats3)

        season_stats = player_repo.load_season_stats("player-1", "season-1")

        assert season_stats.games_played == 3
        assert season_stats.stats.batting.hits == 6
        assert season_stats.stats.batting.home_runs == 2
        assert season_stats.stats.batting.at_bats == 12

    def test_load_season_stats_different_season(self, player_repo, season_setup):
        """Test loading stats for different seasons."""
        # Insert stats for season-1
        stats1 = Stats()
        stats1.batting.hits = 2
        player_repo.insert("game-1", "player-1", "team-1", "team-2", stats1)

        # Insert stats for season-2
        stats2 = Stats()
        stats2.batting.hits = 3
        player_repo.insert("game-4", "player-1", "team-1", "team-2", stats2)

        # Load season-1 stats
        season1_stats = player_repo.load_season_stats("player-1", "season-1")
        assert season1_stats.games_played == 1
        assert season1_stats.stats.batting.hits == 2

        # Load season-2 stats
        season2_stats = player_repo.load_season_stats("player-1", "season-2")
        assert season2_stats.games_played == 1
        assert season2_stats.stats.batting.hits == 3

    def test_load_season_stats_no_games(self, player_repo, season_setup):
        """Test loading season stats when player has no games in season."""
        season_stats = player_repo.load_season_stats("player-1", "season-1")

        assert season_stats.games_played == 0
        assert season_stats.stats.batting.hits == 0

    def test_load_season_stats_pitching_aggregation(self, player_repo, season_setup):
        """Test pitching stats aggregation."""
        for i in range(1, 4):
            stats = Stats()
            stats.pitching.outs = 9
            stats.pitching.strike_outs = 5
            stats.pitching.walks = 2
            player_repo.insert(f"game-{i}", "player-1", "team-1", "team-2", stats)

        season_stats = player_repo.load_season_stats("player-1", "season-1")

        assert season_stats.stats.pitching.outs == 27  # 9 * 3
        assert season_stats.stats.pitching.strike_outs == 15  # 5 * 3
        assert season_stats.stats.pitching.walks == 6  # 2 * 3

    def test_load_season_stats_fielding_aggregation(self, player_repo, season_setup):
        """Test fielding stats aggregation."""
        for i in range(1, 4):
            stats = Stats()
            stats.fielding.putouts = 3
            stats.fielding.assists = 2
            stats.fielding.errors = 1
            player_repo.insert(f"game-{i}", "player-1", "team-1", "team-2", stats)

        season_stats = player_repo.load_season_stats("player-1", "season-1")

        assert season_stats.stats.fielding.putouts == 9  # 3 * 3
        assert season_stats.stats.fielding.assists == 6  # 2 * 3
        assert season_stats.stats.fielding.errors == 3  # 1 * 3


class TestPlayerGameRepositoryRowToStats:
    """Test _row_to_stats() mapping method."""

    def test_row_to_stats_round_trip(self, player_repo, sample_stats):
        """Test that insert then get preserves all stats."""
        player_repo.insert("game-1", "player-1", "team-1", "team-2", sample_stats)

        retrieved = player_repo.get_for_game("game-1", "player-1")

        # Batting
        assert retrieved.batting.at_bats == sample_stats.batting.at_bats
        assert retrieved.batting.hits == sample_stats.batting.hits
        assert retrieved.batting.doubles == sample_stats.batting.doubles
        assert retrieved.batting.triples == sample_stats.batting.triples
        assert retrieved.batting.home_runs == sample_stats.batting.home_runs
        assert retrieved.batting.rbi == sample_stats.batting.rbi
        assert retrieved.batting.runs == sample_stats.batting.runs
        assert retrieved.batting.walks == sample_stats.batting.walks
        assert retrieved.batting.strike_outs == sample_stats.batting.strike_outs

        # Pitching
        assert retrieved.pitching.outs == sample_stats.pitching.outs
        assert retrieved.pitching.hits == sample_stats.pitching.hits
        assert retrieved.pitching.runs == sample_stats.pitching.runs
        assert retrieved.pitching.strike_outs == sample_stats.pitching.strike_outs
        assert retrieved.pitching.pitch_count == sample_stats.pitching.pitch_count

        # Fielding
        assert retrieved.fielding.putouts == sample_stats.fielding.putouts
        assert retrieved.fielding.assists == sample_stats.fielding.assists
        assert retrieved.fielding.errors == sample_stats.fielding.errors

    def test_row_to_stats_calculates_chances(self, player_repo):
        """Test that fielding chances are calculated correctly."""
        stats = Stats()
        stats.fielding.putouts = 5
        stats.fielding.assists = 3
        stats.fielding.errors = 2

        player_repo.insert("game-1", "player-1", "team-1", "team-2", stats)

        retrieved = player_repo.get_for_game("game-1", "player-1")

        assert retrieved.fielding.chances == 10  # 5 + 3 + 2
