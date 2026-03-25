# tests/db/repositories/test_talent_cap_repo.py
"""
Unit tests for TalentCapRepository.

Uses an in-memory SQLite database so tests are fast and self-contained.
"""

import sqlite3
import unittest

from src.db.repositories.talent_cap_repo import TalentCapRepository
from src.db.repositories.talent_cap_repo import _SKILLS

# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────


def _make_conn() -> sqlite3.Connection:
    """Create an in-memory DB with the talent caps table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE player_talent_caps (
            player_id    TEXT PRIMARY KEY,
            clutch       INTEGER NOT NULL DEFAULT 100,
            speed        INTEGER NOT NULL DEFAULT 100,
            durability   INTEGER NOT NULL DEFAULT 100,
            power        INTEGER NOT NULL DEFAULT 100,
            eye          INTEGER NOT NULL DEFAULT 100,
            contact      INTEGER NOT NULL DEFAULT 100,
            base_running INTEGER NOT NULL DEFAULT 100,
            bunting      INTEGER NOT NULL DEFAULT 100,
            catching     INTEGER NOT NULL DEFAULT 100,
            infield      INTEGER NOT NULL DEFAULT 100,
            outfield     INTEGER NOT NULL DEFAULT 100,
            arm          INTEGER NOT NULL DEFAULT 100,
            accuracy     INTEGER NOT NULL DEFAULT 100,
            stamina      INTEGER NOT NULL DEFAULT 100,
            recovery     INTEGER NOT NULL DEFAULT 100,
            ground_balls INTEGER NOT NULL DEFAULT 100,
            strikes      INTEGER NOT NULL DEFAULT 100
        )
    """)
    conn.commit()
    return conn


def _full_caps(base: int = 70) -> dict[str, int]:
    """Return a caps dict with all skills set to base."""
    return {sk: base for sk in _SKILLS}


def _varied_caps():
    return {sk: (i % 50) + 50 for i, sk in enumerate(_SKILLS)}


# ─────────────────────────────────────────────
#  Test classes
# ─────────────────────────────────────────────


class TestInsert(unittest.TestCase):
    def setUp(self):
        self.conn = _make_conn()
        self.repo = TalentCapRepository(self.conn)

    def test_insert_persists_all_skills(self):
        caps = _varied_caps()
        self.repo.insert("player-1", caps)
        result = self.repo.get("player-1")
        self.assertIsNotNone(result)
        for sk in _SKILLS:
            self.assertEqual(result[sk], caps[sk], f"Mismatch on skill {sk}")

    def test_insert_is_idempotent(self):
        """INSERT OR IGNORE — second insert silently does nothing."""
        caps_a = _full_caps(70)
        caps_b = _full_caps(90)
        self.repo.insert("player-1", caps_a)
        self.repo.insert("player-1", caps_b)  # should be ignored
        result = self.repo.get("player-1")
        self.assertEqual(result["speed"], 70)  # original value preserved

    def test_insert_missing_skill_defaults_to_50(self):
        """Caps dict with a missing key defaults to 50."""
        partial = {sk: 65 for sk in _SKILLS if sk != "clutch"}
        self.repo.insert("player-1", partial)
        result = self.repo.get("player-1")
        self.assertEqual(result["clutch"], 50)

    def test_insert_multiple_players(self):
        self.repo.insert("player-1", _full_caps(60))
        self.repo.insert("player-2", _full_caps(80))
        self.assertEqual(self.repo.get("player-1")["speed"], 60)
        self.assertEqual(self.repo.get("player-2")["speed"], 80)


class TestInsertMany(unittest.TestCase):
    def setUp(self):
        self.conn = _make_conn()
        self.repo = TalentCapRepository(self.conn)

    def test_insert_many_persists_all_records(self):
        records = [
            ("player-1", _full_caps(60)),
            ("player-2", _full_caps(75)),
            ("player-3", _full_caps(88)),
        ]
        self.repo.insert_many(records)
        for pid, caps in records:
            result = self.repo.get(pid)
            self.assertIsNotNone(result, f"Missing caps for {pid}")
            self.assertEqual(result["contact"], caps["contact"])

    def test_insert_many_empty_list(self):
        """Should not raise on empty input."""
        self.repo.insert_many([])

    def test_insert_many_ignores_duplicates(self):
        self.repo.insert("player-1", _full_caps(60))
        self.repo.insert_many([("player-1", _full_caps(99))])
        self.assertEqual(self.repo.get("player-1")["speed"], 60)

    def test_insert_many_partial_duplicates(self):
        """Only new players inserted; existing ones unchanged."""
        self.repo.insert("player-1", _full_caps(60))
        self.repo.insert_many(
            [
                ("player-1", _full_caps(99)),  # duplicate — ignored
                ("player-2", _full_caps(75)),  # new — inserted
            ]
        )
        self.assertEqual(self.repo.get("player-1")["speed"], 60)
        self.assertEqual(self.repo.get("player-2")["speed"], 75)


class TestGet(unittest.TestCase):
    def setUp(self):
        self.conn = _make_conn()
        self.repo = TalentCapRepository(self.conn)

    def test_get_returns_none_for_missing_player(self):
        self.assertIsNone(self.repo.get("nonexistent"))

    def test_get_returns_all_skill_keys(self):
        self.repo.insert("player-1", _full_caps(70))
        result = self.repo.get("player-1")
        self.assertEqual(set(result.keys()), set(_SKILLS))

    def test_get_values_are_integers(self):
        self.repo.insert("player-1", _varied_caps())
        result = self.repo.get("player-1")
        for sk, val in result.items():
            self.assertIsInstance(val, int, f"{sk} should be int, got {type(val)}")

    def test_get_roundtrips_varied_caps(self):
        caps = _varied_caps()
        self.repo.insert("player-1", caps)
        result = self.repo.get("player-1")
        self.assertEqual(result, caps)


class TestGetMany(unittest.TestCase):
    def setUp(self):
        self.conn = _make_conn()
        self.repo = TalentCapRepository(self.conn)
        self.repo.insert("player-1", _full_caps(60))
        self.repo.insert("player-2", _full_caps(75))
        self.repo.insert("player-3", _full_caps(88))

    def test_get_many_returns_all_requested(self):
        result = self.repo.get_many(["player-1", "player-2", "player-3"])
        self.assertEqual(set(result.keys()), {"player-1", "player-2", "player-3"})

    def test_get_many_values_correct(self):
        result = self.repo.get_many(["player-1", "player-2"])
        self.assertEqual(result["player-1"]["speed"], 60)
        self.assertEqual(result["player-2"]["speed"], 75)

    def test_get_many_omits_missing_players(self):
        result = self.repo.get_many(["player-1", "nonexistent"])
        self.assertIn("player-1", result)
        self.assertNotIn("nonexistent", result)

    def test_get_many_empty_list(self):
        result = self.repo.get_many([])
        self.assertEqual(result, {})

    def test_get_many_all_missing(self):
        result = self.repo.get_many(["ghost-1", "ghost-2"])
        self.assertEqual(result, {})

    def test_get_many_each_result_has_all_skills(self):
        result = self.repo.get_many(["player-1", "player-2"])
        for pid, caps in result.items():
            self.assertEqual(set(caps.keys()), set(_SKILLS), f"{pid} missing skills")

    def test_get_many_single_player(self):
        result = self.repo.get_many(["player-2"])
        self.assertEqual(len(result), 1)
        self.assertIn("player-2", result)


class TestExists(unittest.TestCase):
    def setUp(self):
        self.conn = _make_conn()
        self.repo = TalentCapRepository(self.conn)

    def test_exists_false_for_missing(self):
        self.assertFalse(self.repo.exists("nobody"))

    def test_exists_true_after_insert(self):
        self.repo.insert("player-1", _full_caps(70))
        self.assertTrue(self.repo.exists("player-1"))

    def test_exists_does_not_affect_other_players(self):
        self.repo.insert("player-1", _full_caps(70))
        self.assertFalse(self.repo.exists("player-2"))


class TestEdgeCases(unittest.TestCase):
    def setUp(self):
        self.conn = _make_conn()
        self.repo = TalentCapRepository(self.conn)

    def test_cap_value_at_minimum(self):
        caps = _full_caps(1)
        self.repo.insert("player-1", caps)
        result = self.repo.get("player-1")
        for sk in _SKILLS:
            self.assertEqual(result[sk], 1)

    def test_cap_value_at_maximum(self):
        caps = _full_caps(100)
        self.repo.insert("player-1", caps)
        result = self.repo.get("player-1")
        for sk in _SKILLS:
            self.assertEqual(result[sk], 100)

    def test_insert_then_get_many_consistent(self):
        """Single insert and get_many should return identical data."""
        caps = _varied_caps()
        self.repo.insert("player-1", caps)
        single = self.repo.get("player-1")
        many = self.repo.get_many(["player-1"])
        self.assertEqual(single, many["player-1"])


if __name__ == "__main__":
    unittest.main()
