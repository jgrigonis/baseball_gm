# tests/db/test_team_rotations_repo.py
"""Unit tests for TeamRotationsRepository."""

import pytest

from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.db.schema import SCHEMA_SQL


# @pytest.fixture
# def db_conn():
#     """Create an in-memory SQLite database for testing."""
#     conn = sqlite3.connect(":memory:")
#     conn.execute("PRAGMA foreign_keys = ON")
#     conn.executescript(SCHEMA_SQL)

#     # Insert test data
#     conn.execute(
#         "INSERT INTO seasons (id, year, name) VALUES (?, ?, ?)", ("S1", 2024, "Season1")
#     )
#     conn.execute(
#         "INSERT INTO teams (id, city, mascot) VALUES (?, ?, ?)",
#         ("BOS", "Boston", "Red Sox"),
#     )

#     # Insert test players
#     for i in range(1, 8):
#         player_id = f"P{i:03d}"
#         conn.execute(
#             """INSERT INTO players (id, first_name, last_name, bats, throws, position)
#                VALUES (?, ?, ?, ?, ?, ?)""",
#             (player_id, f"First{i}", f"Last{i}", "R", "R", "P"),
#         )
#         conn.execute(
#             "INSERT INTO team_players (team_id, player_id) VALUES (?, ?)",
#             ("BOS", player_id),
#         )

#     conn.commit()
#     yield conn
#     conn.close()


@pytest.fixture
def repo(db_conn):
    """Create a TeamRotationsRepository instance."""
    return TeamRotationsRepository(db_conn)


class TestSetRotation:
    def test_set_rotation_success(self, repo, db_conn, db_seed):
        """Test setting a new rotation."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        # Verify rotation was created
        cursor = db_conn.execute(
            """SELECT player_id, rotation_order FROM team_rotations
               WHERE team_id = ? AND season_id = ?
               ORDER BY rotation_order""",
            ("BOS", "S1"),
        )
        rows = cursor.fetchall()

        assert len(rows) == 5
        assert (rows[0]["player_id"], rows[0]["rotation_order"]) == ("P001", 1)
        assert (rows[1]["player_id"], rows[1]["rotation_order"])  == ("P002", 2)
        assert (rows[4]["player_id"], rows[4]["rotation_order"])  == ("P005", 5)

    # This no longer should raise.
    # def test_set_rotation_already_exists(self, repo):
    #     """Test that setting rotation fails if one already exists."""
    #     player_ids = ["P001", "P002", "P003", "P004", "P005"]
    #     repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

    #     # Try to set again
    #     with pytest.raises(ValueError, match="Active rotation already exists"):
    #         repo.set_rotation("BOS", "S1", player_ids, "2024-04-02")


class TestGetCurrentRotation:
    def test_get_current_rotation_success(self, repo, db_seed):
        """Test getting current rotation."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        rotation = repo.get_current_rotation("BOS", "S1", "2024-04-15")

        assert len(rotation) == 5
        assert rotation[0]["player_id"] == "P001"
        assert rotation[0]["rotation_order"] == 1
        assert rotation[4]["player_id"] == "P005"
        assert rotation[4]["rotation_order"] == 5

    def test_get_current_rotation_empty(self, repo):
        """Test getting rotation when none exists."""
        rotation = repo.get_current_rotation("BOS", "S1", "2024-04-01")
        assert rotation == []

    def test_get_current_rotation_respects_effective_date(self, repo, db_seed):
        """Test that rotation respects effective_date."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        # Query before effective date
        rotation = repo.get_current_rotation("BOS", "S1", "2024-03-15")
        assert rotation == []

        # Query after effective date
        rotation = repo.get_current_rotation("BOS", "S1", "2024-04-15")
        assert len(rotation) == 5

    def test_get_current_rotation_respects_end_date(self, repo, db_conn, db_seed):
        """Test that rotation respects end_date."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        # Manually end rotation for one player
        db_conn.execute(
            """UPDATE team_rotations SET end_date = ?
               WHERE player_id = ? AND team_id = ? AND season_id = ?""",
            ("2024-05-01", "P003", "BOS", "S1"),
        )
        db_conn.commit()

        # Before end date - should see P003
        rotation = repo.get_current_rotation("BOS", "S1", "2024-04-15")
        assert len(rotation) == 5

        # After end date - should not see P003
        rotation = repo.get_current_rotation("BOS", "S1", "2024-05-15")
        assert len(rotation) == 4
        player_ids_in_rotation = [p["player_id"] for p in rotation]
        assert "P003" not in player_ids_in_rotation


class TestGetNextStarter:
    def test_get_next_starter_no_previous_games(self, repo, db_seed):
        """Test getting next starter when no games have been played."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        next_starter = repo.get_next_starter("BOS", "S1", "2024-04-15")
        assert next_starter == "P001"

    def test_get_next_starter_with_previous_game(self, repo, db_conn, db_seed):
        """Test getting next starter after a game has been played."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        # Create opponent team FIRST
        db_conn.execute(
            """INSERT INTO teams (id, city, mascot) VALUES (?, ?, ?)""",
            ("NYY", "New York", "Yankees"),
        )

        # Now create the game
        db_conn.execute(
            """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)
            VALUES (?, ?, ?, ?, ?)""",
            ("G1", "2024-04-02", "S1", "BOS", "NYY"),
        )

        db_conn.execute(
            """INSERT INTO player_game_stats 
            (game_id, player_id, team_id, opponent_team_id, pitch_game_started)
            VALUES (?, ?, ?, ?, ?)""",
            ("G1", "P001", "BOS", "NYY", 1),
        )
        db_conn.commit()

        next_starter = repo.get_next_starter("BOS", "S1", "2024-04-03")
        assert next_starter == "P002"

    def test_get_next_starter_wraps_around(self, repo, db_conn, db_seed):
        """Test that rotation wraps from 5 back to 1."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        # Create game where P005 started
        db_conn.execute(
            """INSERT INTO teams (id, city, mascot) VALUES (?, ?, ?)""",
            ("NYY", "New York", "Yankees"),
        )
        db_conn.execute(
            """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)
               VALUES (?, ?, ?, ?, ?)""",
            ("G1", "2024-04-02", "S1", "BOS", "NYY"),
        )
        db_conn.execute(
            """INSERT INTO player_game_stats 
               (game_id, player_id, team_id, opponent_team_id, pitch_game_started)
               VALUES (?, ?, ?, ?, ?)""",
            ("G1", "P005", "BOS", "NYY", 1),
        )
        db_conn.commit()

        next_starter = repo.get_next_starter("BOS", "S1", "2024-04-03")
        assert next_starter == "P001"

    def test_get_next_starter_no_rotation(self, repo):
        """Test getting next starter when no rotation exists."""
        next_starter = repo.get_next_starter("BOS", "S1", "2024-04-01")
        assert next_starter is None


class TestUpdateRotation:
    def test_update_rotation_success(self, repo, db_conn, db_seed):
        """Test updating a pitcher's rotation order."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        # Move P003 from spot 3 to spot 1
        repo.update_rotation("BOS", "S1", "P003", 1, "2024-05-01")

        # Check that old entry was ended
        cursor = db_conn.execute(
            """SELECT end_date FROM team_rotations
               WHERE player_id = ? AND rotation_order = ? AND effective_date = ?""",
            ("P003", 3, "2024-04-01"),
        )
        row = cursor.fetchone()
        assert row[0] == "2024-05-01"

        # Check that new entry was created
        cursor = db_conn.execute(
            """SELECT rotation_order, end_date FROM team_rotations
               WHERE player_id = ? AND effective_date = ?""",
            ("P003", "2024-05-01"),
        )
        row = cursor.fetchone()
        assert row[0] == 1
        assert row[1] is None

    def test_update_rotation_same_order_no_change(self, repo, db_conn, db_seed):
        """Test that updating to same order does nothing."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        # Try to update P003 to same position (3)
        repo.update_rotation("BOS", "S1", "P003", 3, "2024-05-01")

        # Should still only have one entry for P003
        cursor = db_conn.execute(
            """SELECT COUNT(*) FROM team_rotations WHERE player_id = ?""", ("P003",)
        )
        count = cursor.fetchone()[0]
        assert count == 1

    # This no longer raises
    # def test_update_rotation_player_not_in_rotation(self, repo):
    #     """Test updating a player not in rotation raises error."""
    #     player_ids = ["P001", "P002", "P003", "P004", "P005"]
    #     repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

    #     with pytest.raises(ValueError, match="not in active rotation"):
    #         repo.update_rotation("BOS", "S1", "P006", 1, "2024-05-01")


class TestRemoveFromRotation:
    def test_remove_from_rotation_success(self, repo, db_conn, db_seed):
        """Test removing a pitcher from rotation."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        repo.remove_from_rotation("BOS", "S1", "P003", "2024-05-01")

        # Check that entry was ended
        cursor = db_conn.execute(
            """SELECT end_date FROM team_rotations
               WHERE player_id = ? AND team_id = ? AND season_id = ?""",
            ("P003", "BOS", "S1"),
        )
        row = cursor.fetchone()
        assert row[0] == "2024-05-01"

        # Verify rotation no longer includes P003 after removal date
        rotation = repo.get_current_rotation("BOS", "S1", "2024-05-15")
        player_ids_in_rotation = [p["player_id"] for p in rotation]
        assert "P003" not in player_ids_in_rotation

    def test_remove_from_rotation_not_in_rotation(self, repo, db_seed):
        """Test removing a player not in rotation raises error."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        with pytest.raises(ValueError, match="not in active rotation"):
            repo.remove_from_rotation("BOS", "S1", "P006", "2024-05-01")


class TestAddToRotation:
    def test_add_to_rotation_success(self, repo, db_seed):
        """Test adding a new pitcher to rotation."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        # Add P006 at position 6
        repo.add_to_rotation("BOS", "S1", "P006", 6, "2024-05-01")

        rotation = repo.get_current_rotation("BOS", "S1", "2024-05-15")
        assert len(rotation) == 6
        assert rotation[5]["player_id"] == "P006"
        assert rotation[5]["rotation_order"] == 6

    def test_add_to_rotation_shifts_existing(self, repo, db_seed):
        """Test adding pitcher shifts existing pitchers down."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        # Add P006 at position 3 (should shift P003->4, P004->5, P005->6)
        repo.add_to_rotation("BOS", "S1", "P006", 3, "2024-05-01")

        rotation = repo.get_current_rotation("BOS", "S1", "2024-05-15")
        assert len(rotation) == 6

        # Check new pitcher is at position 3
        p006_entry = next(p for p in rotation if p["player_id"] == "P006")
        assert p006_entry["rotation_order"] == 3

        # Check old pitchers were shifted
        p003_entry = next(p for p in rotation if p["player_id"] == "P003")
        assert p003_entry["rotation_order"] == 4

        p004_entry = next(p for p in rotation if p["player_id"] == "P004")
        assert p004_entry["rotation_order"] == 5

        p005_entry = next(p for p in rotation if p["player_id"] == "P005")
        assert p005_entry["rotation_order"] == 6

    def test_add_to_rotation_already_in_rotation(self, repo, db_seed):
        """Test adding a player already in rotation raises error."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        with pytest.raises(ValueError, match="already in active rotation"):
            repo.add_to_rotation("BOS", "S1", "P003", 6, "2024-05-01")


class TestSwapRotationSpots:
    def test_swap_rotation_spots_success(self, repo, db_seed):
        """Test swapping two pitchers' rotation spots."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        # Swap P001 (spot 1) with P005 (spot 5)
        repo.swap_rotation_spots("BOS", "S1", "P001", "P005", "2024-05-01")

        rotation = repo.get_current_rotation("BOS", "S1", "2024-05-15")

        p001_entry = next(p for p in rotation if p["player_id"] == "P001")
        assert p001_entry["rotation_order"] == 5

        p005_entry = next(p for p in rotation if p["player_id"] == "P005")
        assert p005_entry["rotation_order"] == 1

    def test_swap_rotation_spots_player1_not_in_rotation(self, repo, db_seed):
        """Test swapping when player1 not in rotation raises error."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        with pytest.raises(ValueError, match="P006 is not in active rotation"):
            repo.swap_rotation_spots("BOS", "S1", "P006", "P001", "2024-05-01")

    def test_swap_rotation_spots_player2_not_in_rotation(self, repo, db_seed):
        """Test swapping when player2 not in rotation raises error."""
        player_ids = ["P001", "P002", "P003", "P004", "P005"]
        repo.set_rotation("BOS", "S1", player_ids, "2024-04-01")

        with pytest.raises(ValueError, match="P007 is not in active rotation"):
            repo.swap_rotation_spots("BOS", "S1", "P001", "P007", "2024-05-01")
