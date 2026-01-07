"""Unit Tests for the player_repo."""

import sqlite3
import unittest
import uuid

from src.db.init import init_db
from src.db.repositories.player_repo import PlayerRepository
from src.player.player import Player


class TestRepo(unittest.TestCase):
    """Test writing/reading in the database."""

    def setUp(self):
        """Simple setup."""
        conn = sqlite3.connect(":memory:")

        init_db(conn)  # creates tables
        self.player_id = uuid.uuid4().hex
        self.players_repo = PlayerRepository(conn)

    def test_write_player(self):
        self.players_repo.insert(self.player_id, "Joe", "Blow", "l", "l")

    def test_read_player(self):
        row = self.players_repo.look_up(self.player_id)
        #print(row)


if __name__ == "__main__":
    unittest.main()
