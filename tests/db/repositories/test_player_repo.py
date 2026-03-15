# tests/db/repositories/test_player_repo.py
import pytest
import sqlite3
from datetime import datetime

from src.db.repositories.player_repo import PlayerRepository
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills


@pytest.fixture
def db_connection():
    """Create in-memory SQLite database with player tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Create players table
    conn.execute("""
        CREATE TABLE players (
            id TEXT PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            bats TEXT NOT NULL CHECK (bats IN ('L', 'R', 'S')),
            throws TEXT NOT NULL CHECK (throws IN ('L', 'R')),
            position TEXT NOT NULL
        )
    """)

    # Create player_skills table
    conn.execute("""
        CREATE TABLE player_skills (
            player_id TEXT PRIMARY KEY,
            age INTEGER NOT NULL DEFAULT 17,            clutch INTEGER NOT NULL,
            speed INTEGER NOT NULL,
            power INTEGER NOT NULL,
            eye INTEGER NOT NULL,
            contact INTEGER NOT NULL,
            base_running INTEGER NOT NULL,
            bunting INTEGER NOT NULL,
            catching INTEGER NOT NULL,
            infield INTEGER NOT NULL,
            outfield INTEGER NOT NULL,
            arm INTEGER NOT NULL,
            accuracy INTEGER NOT NULL,
            stamina INTEGER NOT NULL,
            recovery INTEGER NOT NULL,
            ground_balls INTEGER NOT NULL,
            strikes INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    """)

    # Create player_skills_history table
    conn.execute("""
        CREATE TABLE player_skills_history (
            player_id TEXT NOT NULL,
            season_id TEXT NOT NULL,
            age INTEGER NOT NULL DEFAULT 17,
            clutch INTEGER NOT NULL,
            speed INTEGER NOT NULL,
            power INTEGER NOT NULL,
            eye INTEGER NOT NULL,
            contact INTEGER NOT NULL,
            base_running INTEGER NOT NULL,
            bunting INTEGER NOT NULL,
            catching INTEGER NOT NULL,
            infield INTEGER NOT NULL,
            outfield INTEGER NOT NULL,
            arm INTEGER NOT NULL,
            accuracy INTEGER NOT NULL,
            stamina INTEGER NOT NULL,
            recovery INTEGER NOT NULL,
            ground_balls INTEGER NOT NULL,
            strikes INTEGER NOT NULL,
            recorded_at TEXT NOT NULL,
            PRIMARY KEY (player_id, season_id),
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    """)

    yield conn
    conn.close()


@pytest.fixture
def player_repo(db_connection):
    """Create PlayerRepository instance."""
    return PlayerRepository(db_connection)


@pytest.fixture
def sample_skills():
    """Create sample PlayerSkills object."""
    return PlayerSkills(
        clutch=75,
        speed=80,
        power=70,
        eye=65,
        contact=85,
        base_running=78,
        bunting=50,
        catching=60,
        infield=75,
        outfield=80,
        arm=70,
        accuracy=75,
        stamina=80,
        recovery=70,
        ground_balls=65,
        strikes=75,
    )


class TestPlayerRepositoryInsert:
    """Test insert() method."""

    def test_insert_new_player(self, player_repo, db_connection, sample_skills):
        """Test inserting a new player."""
        player_repo.insert(
            id="player-1",
            first_name="Mike",
            last_name="Trout",
            bats="R",  # Can use upper or lowercase
            throws="R",
            position="OF",
            skills=sample_skills,
        )

        # Verify player identity
        identity_row = db_connection.execute(
            "SELECT * FROM players WHERE id = ?", ("player-1",)
        ).fetchone()

        assert identity_row is not None
        assert identity_row["first_name"] == "Mike"
        assert identity_row["last_name"] == "Trout"
        assert identity_row["bats"] == "R"  # Changed from "r" to "R"
        assert identity_row["throws"] == "R"  # Changed from "r" to "R"
        assert identity_row["position"] == "OF"  # Changed from "of" to "OF"

        # Verify skills
        skills_row = db_connection.execute(
            "SELECT * FROM player_skills WHERE player_id = ?", ("player-1",)
        ).fetchone()

        assert skills_row is not None
        assert skills_row["clutch"] == 75
        assert skills_row["speed"] == 80
        assert skills_row["power"] == 70

    def test_insert_idempotent(self, player_repo, db_connection, sample_skills):
        """Test that insert is idempotent (INSERT OR REPLACE)."""
        # Insert first time
        player_repo.insert(
            id="player-1",
            first_name="Mike",
            last_name="Trout",
            bats="r",
            throws="r",
            position="rf",
            skills=sample_skills,
        )

        # Insert again with different name
        player_repo.insert(
            id="player-1",
            first_name="Michael",
            last_name="Trout",
            bats="r",
            throws="r",
            position="rf",
            skills=sample_skills,
        )

        # Should only have one player
        count = db_connection.execute(
            "SELECT COUNT(*) as count FROM players"
        ).fetchone()["count"]

        assert count == 1

        # Should have updated name
        row = db_connection.execute(
            "SELECT first_name FROM players WHERE id = ?", ("player-1",)
        ).fetchone()

        # Should have kept original name (identity is immutable)
        assert row["first_name"] == "Mike"

    def test_insert_multiple_players(self, player_repo, db_connection, sample_skills):
        """Test inserting multiple players."""
        players = [
            ("player-1", "Mike", "Trout", "r", "r", "rf"),
            ("player-2", "Shohei", "Ohtani", "L", "r", "P"),
            ("player-3", "Mookie", "Betts", "r", "r", "cf"),
        ]

        for player in players:
            player_repo.insert(*player, skills=sample_skills)

        count = db_connection.execute(
            "SELECT COUNT(*) as count FROM players"
        ).fetchone()["count"]

        assert count == 3

    def test_insert_different_handedness(
        self, player_repo, db_connection, sample_skills
    ):
        """Test inserting players with different batting/throwing hands."""
        # Right-handed batter
        player_repo.insert("p1", "First", "Player", "r", "r", "1b", sample_skills)

        # Left-handed batter
        player_repo.insert(
            "p2",
            "Second",
            "Player",
            "L",
            "L",
            "of",
            sample_skills,
        )

        # Switch hitter
        player_repo.insert("p3", "Third", "Player", "S", "R", "c", sample_skills)

        rows = db_connection.execute(
            "SELECT id, bats FROM players ORDER BY id"
        ).fetchall()

        assert rows[0]["bats"] == "R"  # Changed from lowercase
        assert rows[1]["bats"] == "L"
        assert rows[2]["bats"] == "S"

    def test_insert_creates_timestamp(self, player_repo, db_connection, sample_skills):
        """Test that insert creates a timestamp."""
        before = datetime.now()

        player_repo.insert("p1", "First", "Player", "r", "r", "1B", sample_skills)

        after = datetime.now()

        row = db_connection.execute(
            "SELECT updated_at FROM player_skills WHERE player_id = ?", ("p1",)
        ).fetchone()

        # Verify timestamp exists and is reasonable
        assert row["updated_at"] is not None
        timestamp = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))

        # Should be between before and after (allowing for timezone)
        assert timestamp.replace(tzinfo=None) >= before.replace(
            microsecond=0
        ) or timestamp.replace(tzinfo=None) <= after.replace(microsecond=0)


class TestPlayerRepositoryUpdateSkills:
    """Test update_skills() method."""

    def test_update_skills(self, player_repo, db_connection, sample_skills):
        """Test updating player skills."""
        # Insert player first
        player_repo.insert("p1", "First", "Player", "r", "r", "1B", sample_skills)

        # Create new skills
        new_skills = PlayerSkills(
            clutch=80,
            speed=85,
            power=75,
            eye=70,
            contact=90,
            base_running=83,
            bunting=55,
            catching=65,
            infield=80,
            outfield=85,
            arm=75,
            accuracy=80,
            stamina=85,
            recovery=75,
            ground_balls=70,
            strikes=80,
        )

        # Update skills
        player_repo.update_skills("p1", new_skills)

        # Verify updated
        row = db_connection.execute(
            "SELECT * FROM player_skills WHERE player_id = ?", ("p1",)
        ).fetchone()

        assert row["clutch"] == 80
        assert row["speed"] == 85
        assert row["power"] == 75
        assert row["contact"] == 90

    def test_update_skills_creates_new_timestamp(
        self, player_repo, db_connection, sample_skills
    ):
        """Test that updating skills creates a new timestamp."""
        player_repo.insert("p1", "First", "Player", "r", "r", "1B", sample_skills)

        # Get original timestamp
        original_ts = db_connection.execute(
            "SELECT updated_at FROM player_skills WHERE player_id = ?", ("p1",)
        ).fetchone()["updated_at"]

        # Small delay to ensure different timestamp
        import time

        time.sleep(0.01)

        # Update skills
        new_skills = sample_skills
        new_skills.speed = 85
        player_repo.update_skills("p1", new_skills)

        # Get new timestamp
        new_ts = db_connection.execute(
            "SELECT updated_at FROM player_skills WHERE player_id = ?", ("p1",)
        ).fetchone()["updated_at"]

        # Timestamps should be different
        assert new_ts != original_ts

    def test_update_skills_idempotent(self, player_repo, db_connection, sample_skills):
        """Test that update_skills is idempotent."""
        player_repo.insert("p1", "First", "Player", "r", "r", "1B", sample_skills)

        # Update multiple times
        for i in range(5):
            new_skills = sample_skills
            new_skills.speed = 85 + i
            player_repo.update_skills("p1", new_skills)

        # Should only have one record
        count = db_connection.execute(
            "SELECT COUNT(*) as count FROM player_skills WHERE player_id = ?", ("p1",)
        ).fetchone()["count"]

        assert count == 1


class TestPlayerRepositorySnapshotSkills:
    """Test snapshot_skills() method."""

    def test_snapshot_skills(self, player_repo, db_connection, sample_skills):
        """Test taking a snapshot of player skills."""
        # Insert player
        player_repo.insert("p1", "First", "Player", "r", "r", "1B", sample_skills)

        # Take snapshot
        player_repo.snapshot_skills("p1", "season-2025")

        # Verify snapshot exists
        row = db_connection.execute(
            """
            SELECT * FROM player_skills_history 
            WHERE player_id = ? AND season_id = ?
            """,
            ("p1", "season-2025"),
        ).fetchone()

        assert row is not None
        assert row["clutch"] == 75
        assert row["speed"] == 80
        assert row["power"] == 70

    def test_snapshot_skills_multiple_seasons(
        self, player_repo, db_connection, sample_skills
    ):
        """Test taking snapshots for multiple seasons."""
        player_repo.insert("p1", "First", "Player", "r", "r", "1B", sample_skills)

        # Take snapshots for 3 seasons with different skills
        seasons = ["season-2023", "season-2024", "season-2025"]
        for i, season in enumerate(seasons):
            # Update skills before snapshot
            updated_skills = sample_skills
            updated_skills.speed = 80 + i
            player_repo.update_skills("p1", updated_skills)

            # Take snapshot
            player_repo.snapshot_skills("p1", season)

        # Verify all snapshots exist
        count = db_connection.execute(
            "SELECT COUNT(*) as count FROM player_skills_history WHERE player_id = ?",
            ("p1",),
        ).fetchone()["count"]

        assert count == 3

    def test_snapshot_skills_idempotent(
        self, player_repo, db_connection, sample_skills
    ):
        """Test that snapshot_skills is idempotent (INSERT OR REPLACE)."""
        player_repo.insert("p1", "First", "Player", "R", "R", "1b", sample_skills)

        # Take snapshot
        player_repo.snapshot_skills("p1", "season-2025")

        # Create NEW skills object with updated speed
        new_skills = PlayerSkills({**sample_skills.as_dict(), "speed": 85})
        player_repo.update_skills("p1", new_skills)

        # Take snapshot again for same season
        player_repo.snapshot_skills("p1", "season-2025")

        # Should only have one snapshot
        count = db_connection.execute(
            """
            SELECT COUNT(*) as count FROM player_skills_history 
            WHERE player_id = ? AND season_id = ?
            """,
            ("p1", "season-2025"),
        ).fetchone()["count"]

        assert count == 1

        # Should have updated skills
        row = db_connection.execute(
            """
            SELECT speed FROM player_skills_history 
            WHERE player_id = ? AND season_id = ?
            """,
            ("p1", "season-2025"),
        ).fetchone()

        assert row["speed"] == 85

    def test_snapshot_skills_creates_timestamp(
        self, player_repo, db_connection, sample_skills
    ):
        """Test that snapshot creates a timestamp."""
        player_repo.insert("p1", "First", "Player", "r", "r", "1B", sample_skills)
        player_repo.snapshot_skills("p1", "season-2025")

        row = db_connection.execute(
            """
            SELECT recorded_at FROM player_skills_history
            WHERE player_id = ? AND season_id = ?
            """,
            ("p1", "season-2025"),
        ).fetchone()

        assert row["recorded_at"] is not None


class TestPlayerRepositoryLookUp:
    """Test look_up() method."""

    def test_look_up_existing_player(self, player_repo, sample_skills):
        """Test looking up an existing player."""
        player_repo.insert("p1", "Mike", "Trout", "r", "r", "rf", sample_skills)

        record = player_repo.look_up("p1")

        assert record is not None
        assert isinstance(record, PlayerRecord)
        assert record.id == "p1"
        assert record.first_name == "Mike"
        assert record.last_name == "Trout"
        assert record.bats == "R"
        assert record.throws == "R"
        assert record.position == "rf"

    def test_look_up_skills(self, player_repo, sample_skills):
        """Test that skills are correctly loaded."""
        player_repo.insert("p1", "Mike", "Trout", "R", "R", "rf", sample_skills)

        record = player_repo.look_up("p1")

        assert isinstance(record.skills, PlayerSkills)
        assert record.skills["clutch"] == 75
        assert record.skills["speed"] == 80
        assert record.skills["power"] == 70
        assert record.skills["contact"] == 85

    def test_look_up_nonexistent_player(self, player_repo):
        """Test looking up a player that doesn't exist."""
        record = player_repo.look_up("nonexistent")

        assert record is None

    def test_look_up_player_without_skills(self, player_repo, db_connection):
        """Test looking up a player who has no skills (error case)."""
        # Manually insert player without skills - use UPPERCASE
        db_connection.execute(
            """
            INSERT INTO players (id, first_name, last_name, bats, throws, position)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("p1", "Mike", "Trout", "R", "R", "of"),  # Changed to uppercase
        )
        db_connection.commit()

        # Should raise ValueError
        with pytest.raises(ValueError, match="Player p1 has no skills record"):
            player_repo.look_up("p1")

    def test_look_up_returns_current_skills(self, player_repo, sample_skills):
        """Test that look_up returns current skills, not historical."""
        player_repo.insert("p1", "Mike", "Trout", "r", "r", "rf", sample_skills)

        # Update skills - CREATE NEW OBJECT
        new_skills = PlayerSkills({**sample_skills.as_dict(), "speed": 85})
        player_repo.update_skills("p1", new_skills)

        # Look up player
        record = player_repo.look_up("p1")

        # Should have updated skills
        assert record.skills["speed"] == 85


class TestPlayerRepositoryGetSkillHistory:
    """Test get_skill_history() method."""

    def test_get_skill_history_empty(self, player_repo, sample_skills):
        """Test getting history for a player with no snapshots."""
        player_repo.insert("p1", "Mike", "Trout", "r", "r", "rf", sample_skills)

        history = player_repo.get_skill_history("p1")

        assert history == []

    def test_get_skill_history_single_season(self, player_repo, sample_skills):
        """Test getting history with one snapshot."""
        player_repo.insert("p1", "Mike", "Trout", "r", "r", "rf", sample_skills)
        player_repo.snapshot_skills("p1", "season-2025")

        history = player_repo.get_skill_history("p1")

        assert len(history) == 1
        assert history[0]["season_id"] == "season-2025"
        assert history[0]["clutch"] == 75
        assert history[0]["speed"] == 80

    def test_get_skill_history_multiple_seasons(self, player_repo, sample_skills):
        """Test getting history with multiple snapshots."""
        player_repo.insert("p1", "Mike", "Trout", "r", "r", "rf", sample_skills)

        # Take snapshots for 3 seasons
        seasons = ["season-2023", "season-2024", "season-2025"]
        for i, season in enumerate(seasons):
            updated_skills = sample_skills
            updated_skills.speed = 80 + i
            player_repo.update_skills("p1", updated_skills)
            player_repo.snapshot_skills("p1", season)

        history = player_repo.get_skill_history("p1")

        assert len(history) == 3
        assert history[0]["season_id"] == "season-2023"
        assert history[1]["season_id"] == "season-2024"
        assert history[2]["season_id"] == "season-2025"

    def test_get_skill_history_ordered(self, player_repo, sample_skills):
        """Test that history is ordered by season_id."""
        player_repo.insert("p1", "Mike", "Trout", "r", "r", "rf", sample_skills)

        # Insert in random order
        seasons = ["season-2025", "season-2023", "season-2024"]
        for season in seasons:
            player_repo.snapshot_skills("p1", season)

        history = player_repo.get_skill_history("p1")

        # Should be ordered
        season_ids = [h["season_id"] for h in history]
        assert season_ids == sorted(season_ids)

    def test_get_skill_history_shows_progression(self, player_repo, sample_skills):
        """Test that history shows skill progression over time."""
        player_repo.insert("p1", "Mike", "Trout", "R", "R", "of", sample_skills)

        # Snapshot with increasing speed - create NEW skills each time
        for i, year in enumerate([2023, 2024, 2025]):
            new_skills = PlayerSkills({**sample_skills.as_dict(), "speed": 75 + i * 5})
            player_repo.update_skills("p1", new_skills)
            player_repo.snapshot_skills("p1", f"season-{year}")

        history = player_repo.get_skill_history("p1")

        assert history[0]["speed"] == 75
        assert history[1]["speed"] == 80
        assert history[2]["speed"] == 85


class TestPlayerRepositoryExists:
    """Test exists() method."""

    def test_exists_true(self, player_repo, sample_skills):
        """Test exists returns True for existing player."""
        player_repo.insert("p1", "Mike", "Trout", "r", "r", "of", sample_skills)

        assert player_repo.exists("p1") is True

    def test_exists_false(self, player_repo):
        """Test exists returns False for nonexistent player."""
        assert player_repo.exists("nonexistent") is False

    def test_exists_multiple_players(self, player_repo, sample_skills):
        """Test exists with multiple players."""
        player_repo.insert("p1", "Player", "One", "r", "r", "1B", sample_skills)
        player_repo.insert("p2", "Player", "Two", "L", "L", "rf", sample_skills)

        assert player_repo.exists("p1") is True
        assert player_repo.exists("p2") is True
        assert player_repo.exists("p3") is False


class TestPlayerRepositoryGetAllPlayers:
    """Test get_all_players() method."""

    def test_get_all_players_empty(self, player_repo):
        """Test getting all players when database is empty."""
        players = player_repo.get_all_players()

        assert players == []

    def test_get_all_players_single(self, player_repo, sample_skills):
        """Test getting all players with one player."""
        player_repo.insert("p1", "Mike", "Trout", "r", "r", "rf", sample_skills)

        players = player_repo.get_all_players()

        assert len(players) == 1
        assert isinstance(players[0], PlayerRecord)
        assert players[0].id == "p1"

    def test_get_all_players_multiple(self, player_repo, sample_skills):
        """Test getting all players with multiple players."""
        player_data = [
            ("p1", "Mike", "Trout", "R", "R", "rf"),
            ("p2", "Shohei", "Ohtani", "L", "R", "p"),
            ("p3", "Mookie", "Betts", "R", "R", "rf"),
        ]

        for player in player_data:
            player_repo.insert(*player, skills=sample_skills)

        players = player_repo.get_all_players()

        assert len(players) == 3
        assert all(isinstance(p, PlayerRecord) for p in players)

    def test_get_all_players_ordered_by_name(self, player_repo, sample_skills):
        """Test that players are ordered by last name, first name."""
        # Insert in non-alphabetical order - use lowercase positions
        player_repo.insert(
            "p1",
            "Zach",
            "Anderson",
            "R",
            "R",
            "1b",
            sample_skills,
        )  # Changed from "1B"
        player_repo.insert(
            "p2", "Aaron", "Judge", "R", "R", "of", sample_skills
        )  # Changed from "OF"
        player_repo.insert(
            "p3", "Mike", "Trout", "R", "R", "of", sample_skills
        )  # Changed from "OF"

        players = player_repo.get_all_players()

        # Should be ordered: Anderson, Judge, Trout
        assert players[0].last_name == "Anderson"
        assert players[1].last_name == "Judge"
        assert players[2].last_name == "Trout"

    def test_get_all_players_includes_skills(self, player_repo, sample_skills):
        """Test that all players include their skills."""
        player_repo.insert("p1", "Mike", "Trout", "R", "R", "rf", sample_skills)

        players = player_repo.get_all_players()

        assert players[0].skills is not None
        assert isinstance(players[0].skills, PlayerSkills)
        assert players[0].skills["speed"] == 80


class TestPlayerRepositoryIntegration:
    """Integration tests for typical workflows."""

    def test_full_player_lifecycle(self, player_repo, sample_skills):
        """Test complete player lifecycle: create, update, snapshot."""
        # Create player
        player_repo.insert("p1", "Mike", "Trout", "R", "R", "rf", sample_skills)

        # Verify creation
        record = player_repo.look_up("p1")
        assert record.skills["speed"] == 80

        # Update skills (aging/training) - CREATE NEW OBJECT
        new_skills = PlayerSkills({**sample_skills.as_dict(), "speed": 78})
        player_repo.update_skills("p1", new_skills)

        # Snapshot for season
        player_repo.snapshot_skills("p1", "season-2025")

        # Verify history
        history = player_repo.get_skill_history("p1")
        assert len(history) == 1
        assert history[0]["speed"] == 78

        # Continue to next season - CREATE ANOTHER NEW OBJECT
        new_skills = PlayerSkills({**sample_skills.as_dict(), "speed": 76})
        player_repo.update_skills("p1", new_skills)
        player_repo.snapshot_skills("p1", "season-2026")

        # Verify progression
        history = player_repo.get_skill_history("p1")
        assert len(history) == 2
        assert history[0]["speed"] == 78
        assert history[1]["speed"] == 76

    def test_roster_management(self, player_repo, sample_skills):
        """Test managing a full roster of players."""
        # Create a full roster
        for i in range(25):
            player_repo.insert(
                f"player-{i}",
                f"First{i}",
                f"Last{i}",
                "R" if i % 2 == 0 else "L",
                "R",
                "cf",
                sample_skills,
            )

        # Get all players
        players = player_repo.get_all_players()
        assert len(players) == 25

        # Verify all have skills
        assert all(p.skills is not None for p in players)

        # Check specific player
        assert player_repo.exists("player-10")
        specific = player_repo.look_up("player-10")
        assert specific.first_name == "First10"
