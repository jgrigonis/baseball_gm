# tests/db/repositories/test_talent_cap_repo.py
"""
Unit tests for TalentCapRepository.

Uses an in-memory SQLite database so tests are fast and self-contained.
"""
import pytest

from src.db.repositories.talent_cap_repo import TalentCapRepository
from src.db.repositories.talent_cap_repo import _SKILLS

# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────


# def _make_conn() -> sqlite3.Connection:
#     """Create an in-memory DB with the talent caps table."""
#     conn = sqlite3.connect(":memory:")
#     conn.row_factory = sqlite3.Row
#     conn.execute("PRAGMA foreign_keys = ON")
#     conn.execute("""
#         CREATE TABLE player_talent_caps (
#             player_id    TEXT PRIMARY KEY,
#             clutch       INTEGER NOT NULL DEFAULT 100,
#             speed        INTEGER NOT NULL DEFAULT 100,
#             durability   INTEGER NOT NULL DEFAULT 100,
#             power        INTEGER NOT NULL DEFAULT 100,
#             eye          INTEGER NOT NULL DEFAULT 100,
#             contact      INTEGER NOT NULL DEFAULT 100,
#             base_running INTEGER NOT NULL DEFAULT 100,
#             bunting      INTEGER NOT NULL DEFAULT 100,
#             catching     INTEGER NOT NULL DEFAULT 100,
#             infield      INTEGER NOT NULL DEFAULT 100,
#             outfield     INTEGER NOT NULL DEFAULT 100,
#             arm          INTEGER NOT NULL DEFAULT 100,
#             accuracy     INTEGER NOT NULL DEFAULT 100,
#             stamina      INTEGER NOT NULL DEFAULT 100,
#             recovery     INTEGER NOT NULL DEFAULT 100,
#             ground_balls INTEGER NOT NULL DEFAULT 100,
#             strikes      INTEGER NOT NULL DEFAULT 100
#         )
#     """)
#     conn.commit()
#     return conn


def _full_caps(base: int = 70) -> dict[str, int]:
    """Return a caps dict with all skills set to base."""
    return {sk: base for sk in _SKILLS}


def _varied_caps():
    return {sk: (i % 50) + 50 for i, sk in enumerate(_SKILLS)}

@pytest.fixture
def repo(db_conn):
    return TalentCapRepository(db_conn)

# ─────────────────────────────────────────────
#  Test classes
# ─────────────────────────────────────────────


class TestInsert():

    def test_insert_persists_all_skills(self, repo, db_seed):
        caps = _varied_caps()
        repo.insert("player-1", caps)
        result = repo.get("player-1")
        assert result is not None 
        for sk in _SKILLS:
            assert result[sk] == caps[sk], f"Mismatch on skill {sk}"

    def test_insert_is_idempotent(self, repo, db_seed):
        """INSERT OR IGNORE — second insert silently does nothing."""
        caps_a = _full_caps(70)
        caps_b = _full_caps(90)
        repo.insert("player-1", caps_a)
        repo.insert("player-1", caps_b)  # should be ignored
        result = repo.get("player-1")
        assert result["speed"] == 70  # original value preserved

    def test_insert_missing_skill_defaults_to_50(self, repo, db_seed):
        """Caps dict with a missing key defaults to 50."""
        partial = {sk: 65 for sk in _SKILLS if sk != "clutch"}
        repo.insert("player-1", partial)
        result = repo.get("player-1")
        assert result["clutch"] == 50

    def test_insert_multiple_players(self, repo, db_seed):
        repo.insert("player-1", _full_caps(60))
        repo.insert("player-2", _full_caps(80))
        assert repo.get("player-1")["speed"] == 60
        assert repo.get("player-2")["speed"] == 80


class TestInsertMany():
    def test_insert_many_persists_all_records(self, repo, db_seed):
        records = [
            ("player-1", _full_caps(60)),
            ("player-2", _full_caps(75)),
            ("player-3", _full_caps(88)),
        ]
        repo.insert_many(records)
        for pid, caps in records:
            result = repo.get(pid)
            assert result is not None, f"Missing caps for {pid}"
            assert result["contact"] == caps["contact"]

    def test_insert_many_empty_list(self, repo):
        """Should not raise on empty input."""
        repo.insert_many([])

    def test_insert_many_ignores_duplicates(self, repo, db_seed):
        repo.insert("player-1", _full_caps(60))
        repo.insert_many([("player-1", _full_caps(99))])
        assert repo.get("player-1")["speed"] == 60

    def test_insert_many_partial_duplicates(self, repo, db_seed):
        """Only new players inserted; existing ones unchanged."""
        repo.insert("player-1", _full_caps(60))
        repo.insert_many(
            [
                ("player-1", _full_caps(99)),  # duplicate — ignored
                ("player-2", _full_caps(75)),  # new — inserted
            ]
        )
        assert repo.get("player-1")["speed"] == 60
        assert repo.get("player-2")["speed"] == 75


class TestGet():

    def test_get_returns_none_for_missing_player(self, repo):
        assert repo.get("nonexistent") is None

    def test_get_returns_all_skill_keys(self, repo, db_seed):
        repo.insert("player-1", _full_caps(70))
        result = repo.get("player-1")
        assert set(result.keys()) == set(_SKILLS)

    def test_get_values_are_integers(self, repo, db_seed):
        repo.insert("player-1", _varied_caps())
        result = repo.get("player-1")
        for sk, val in result.items():
            assert isinstance(val, int), f"{sk} should be int, got {type(val)}"

    def test_get_roundtrips_varied_caps(self, repo, db_seed):
        caps = _varied_caps()
        repo.insert("player-1", caps)
        result = repo.get("player-1")
        assert result == caps


class TestGetMany():
    
    @pytest.fixture
    def setup_players(self, repo, db_seed):
        repo.insert("player-1", _full_caps(60))
        repo.insert("player-2", _full_caps(75))
        repo.insert("player-3", _full_caps(88))

    def test_get_many_returns_all_requested(self, repo, setup_players):

        result = repo.get_many(["player-1", "player-2", "player-3"])
        assert set(result.keys()) == {"player-1", "player-2", "player-3"}

    def test_get_many_values_correct(self, repo, setup_players):
        result = repo.get_many(["player-1", "player-2"])
        assert result["player-1"]["speed"] == 60
        assert result["player-2"]["speed"] == 75

    def test_get_many_omits_missing_players(self, repo, setup_players):
        result = repo.get_many(["player-1", "nonexistent"])
        assert "player-1" in result
        assert "nonexistent" not in result

    def test_get_many_empty_list(self, repo):
        result = repo.get_many([])
        assert result == {}

    def test_get_many_all_missing(self, repo):
        result = repo.get_many(["ghost-1", "ghost-2"])
        assert result == {}

    def test_get_many_each_result_has_all_skills(self, repo, db_seed):
        result = repo.get_many(["player-1", "player-2"])
        for pid, caps in result.items():
            assert set(caps.keys()) == set(_SKILLS) == f"{pid} missing skills"

    def test_get_many_single_player(self, repo, db_seed, setup_players):
        result = repo.get_many(["player-2"])
        assert len(result) == 1
        assert "player-2" in result


class TestExists():


    def test_exists_false_for_missing(self, repo):
        assert repo.exists("nobody") is False

    def test_exists_true_after_insert(self, repo, db_seed):
        repo.insert("player-1", _full_caps(70))
        assert repo.exists("player-1")

    def test_exists_does_not_affect_other_players(self, repo, db_seed):
        repo.insert("player-1", _full_caps(70))
        assert repo.exists("player-2") is False


class TestEdgeCases():
    def test_cap_value_at_minimum(self, repo, db_seed):
        caps = _full_caps(1)
        repo.insert("player-1", caps)
        result = repo.get("player-1")
        for sk in _SKILLS:
            assert result[sk] == 1

    def test_cap_value_at_maximum(self, repo, db_seed):
        caps = _full_caps(100)
        repo.insert("player-1", caps)
        result = repo.get("player-1")
        for sk in _SKILLS:
            assert result[sk] == 100

    def test_insert_then_get_many_consistent(self, repo, db_seed):
        """Single insert and get_many should return identical data."""
        caps = _varied_caps()
        repo.insert("player-1", caps)
        single = repo.get("player-1")
        many = repo.get_many(["player-1"])
        assert single == many["player-1"]
