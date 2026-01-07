"""Unit Tests for the team_repo."""

import sqlite3
import unittest

from src.db.init import init_db
from src.db.repositories.team_repo import TeamRepository


class TestRepo(unittest.TestCase):
    """Test writing/reading in the database."""

    def setUp(self):
        """Simple setup."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)  # creates tables
        self.team_repo = TeamRepository(conn)
        self.city1 = "Houston"
        self.mascot1 = "Cowboys"
        self.city2 = "Dallas"
        self.mascot2 = "Cheerleaders"

    def test_create_team(self):
        id = self.team_repo.get_or_create(self.city1, self.mascot1)
        assert id is not None

    def test_return_team(self):
        id = self.team_repo.get_or_create(self.city1, self.mascot1)
        id2 = self.team_repo.get_or_create(self.city1, self.mascot1)
        assert id == id2

    def test_lookup(self):
        id = self.team_repo.get_or_create(self.city1, self.mascot1)
        id2 = self.team_repo.get_or_create(self.city1, self.mascot1)
        row = self.team_repo.look_up(id)
        row2 = self.team_repo.look_up(id2)
        assert row == row2
        assert row is not None

    def test_get_team(self):
        id = self.team_repo.get_or_create(self.city1, self.mascot1)
        id2 = self.team_repo.get_or_create(self.city2, self.mascot2)
        assert id != id2

    def test_add_player(self):
        id = self.team_repo.get_or_create(self.city1, self.mascot1)
        self.team_repo.add_player(id, 1)
        # Add the same player to another team, that is fine.
        id2 = self.team_repo.get_or_create(self.city2, self.mascot2)
        self.team_repo.add_player(id2, 1)


if __name__ == "__main__":
    unittest.main()
