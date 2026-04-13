# tests/db/repositories/test_talent_cap_repo.py
"""Unit tests for TalentCapRepository."""
import pytest

from src.db.repositories.talent_cap_repo import TalentCapRepository
from src.db.repositories.talent_cap_repo import _SKILLS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _full_caps(base: int = 70) -> dict[str, int]:
    return {sk: base for sk in _SKILLS}


def _varied_caps():
    return {sk: (i % 50) + 50 for i, sk in enumerate(_SKILLS)}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(db_conn):
    return TalentCapRepository(db_conn)


@pytest.fixture
def ctx(factory):
    """Three unique players per test — no cross-run ID collisions."""
    from types import SimpleNamespace
    p1 = factory.player_row()
    p2 = factory.player_row()
    p3 = factory.player_row()
    return SimpleNamespace(p1=p1, p2=p2, p3=p3)


# ---------------------------------------------------------------------------
# TestInsert
# ---------------------------------------------------------------------------


class TestInsert:

    def test_insert_persists_all_skills(self, repo, ctx):
        caps = _varied_caps()
        repo.insert(ctx.p1.id, caps)
        result = repo.get(ctx.p1.id)
        assert result is not None
        for sk in _SKILLS:
            assert result[sk] == caps[sk], f"Mismatch on skill {sk}"

    def test_insert_is_idempotent(self, repo, ctx):
        """INSERT OR IGNORE — second insert silently does nothing."""
        repo.insert(ctx.p1.id, _full_caps(70))
        repo.insert(ctx.p1.id, _full_caps(90))  # should be ignored
        assert repo.get(ctx.p1.id)["speed"] == 70

    def test_insert_missing_skill_defaults_to_50(self, repo, ctx):
        """Caps dict with a missing key defaults to 50."""
        partial = {sk: 65 for sk in _SKILLS if sk != "clutch"}
        repo.insert(ctx.p1.id, partial)
        assert repo.get(ctx.p1.id)["clutch"] == 50

    def test_insert_multiple_players(self, repo, ctx):
        repo.insert(ctx.p1.id, _full_caps(60))
        repo.insert(ctx.p2.id, _full_caps(80))
        assert repo.get(ctx.p1.id)["speed"] == 60
        assert repo.get(ctx.p2.id)["speed"] == 80


# ---------------------------------------------------------------------------
# TestInsertMany
# ---------------------------------------------------------------------------


class TestInsertMany:

    def test_insert_many_persists_all_records(self, repo, ctx):
        records = [
            (ctx.p1.id, _full_caps(60)),
            (ctx.p2.id, _full_caps(75)),
            (ctx.p3.id, _full_caps(88)),
        ]
        repo.insert_many(records)
        for pid, caps in records:
            result = repo.get(pid)
            assert result is not None, f"Missing caps for {pid}"
            assert result["contact"] == caps["contact"]

    def test_insert_many_empty_list(self, repo):
        repo.insert_many([])  # should not raise

    def test_insert_many_ignores_duplicates(self, repo, ctx):
        repo.insert(ctx.p1.id, _full_caps(60))
        repo.insert_many([(ctx.p1.id, _full_caps(99))])
        assert repo.get(ctx.p1.id)["speed"] == 60

    def test_insert_many_partial_duplicates(self, repo, ctx):
        """Only new players inserted; existing ones unchanged."""
        repo.insert(ctx.p1.id, _full_caps(60))
        repo.insert_many([
            (ctx.p1.id, _full_caps(99)),  # duplicate — ignored
            (ctx.p2.id, _full_caps(75)),  # new — inserted
        ])
        assert repo.get(ctx.p1.id)["speed"] == 60
        assert repo.get(ctx.p2.id)["speed"] == 75


# ---------------------------------------------------------------------------
# TestGet
# ---------------------------------------------------------------------------


class TestGet:

    def test_get_returns_none_for_missing_player(self, repo):
        assert repo.get("nonexistent") is None

    def test_get_returns_all_skill_keys(self, repo, ctx):
        repo.insert(ctx.p1.id, _full_caps(70))
        assert set(repo.get(ctx.p1.id).keys()) == set(_SKILLS)

    def test_get_values_are_integers(self, repo, ctx):
        repo.insert(ctx.p1.id, _varied_caps())
        result = repo.get(ctx.p1.id)
        for sk, val in result.items():
            assert isinstance(val, int), f"{sk} should be int, got {type(val)}"

    def test_get_roundtrips_varied_caps(self, repo, ctx):
        caps = _varied_caps()
        repo.insert(ctx.p1.id, caps)
        assert repo.get(ctx.p1.id) == caps


# ---------------------------------------------------------------------------
# TestGetMany
# ---------------------------------------------------------------------------


class TestGetMany:

    @pytest.fixture
    def setup_players(self, repo, ctx):
        repo.insert(ctx.p1.id, _full_caps(60))
        repo.insert(ctx.p2.id, _full_caps(75))
        repo.insert(ctx.p3.id, _full_caps(88))

    def test_get_many_returns_all_requested(self, repo, ctx, setup_players):
        result = repo.get_many([ctx.p1.id, ctx.p2.id, ctx.p3.id])
        assert set(result.keys()) == {ctx.p1.id, ctx.p2.id, ctx.p3.id}

    def test_get_many_values_correct(self, repo, ctx, setup_players):
        result = repo.get_many([ctx.p1.id, ctx.p2.id])
        assert result[ctx.p1.id]["speed"] == 60
        assert result[ctx.p2.id]["speed"] == 75

    def test_get_many_omits_missing_players(self, repo, ctx, setup_players):
        result = repo.get_many([ctx.p1.id, "nonexistent"])
        assert ctx.p1.id in result
        assert "nonexistent" not in result

    def test_get_many_empty_list(self, repo):
        assert repo.get_many([]) == {}

    def test_get_many_all_missing(self, repo):
        assert repo.get_many(["ghost-1", "ghost-2"]) == {}

    def test_get_many_each_result_has_all_skills(self, repo, ctx, setup_players):
        result = repo.get_many([ctx.p1.id, ctx.p2.id])
        for pid, caps in result.items():
            assert set(caps.keys()) == set(_SKILLS), f"{pid} missing skills"

    def test_get_many_single_player(self, repo, ctx, setup_players):
        result = repo.get_many([ctx.p2.id])
        assert len(result) == 1
        assert ctx.p2.id in result


# ---------------------------------------------------------------------------
# TestExists
# ---------------------------------------------------------------------------


class TestExists:

    def test_exists_false_for_missing(self, repo):
        assert repo.exists("nobody") is False

    def test_exists_true_after_insert(self, repo, ctx):
        repo.insert(ctx.p1.id, _full_caps(70))
        assert repo.exists(ctx.p1.id) is True

    def test_exists_does_not_affect_other_players(self, repo, ctx):
        repo.insert(ctx.p1.id, _full_caps(70))
        assert repo.exists(ctx.p2.id) is False


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:

    def test_cap_value_at_minimum(self, repo, ctx):
        repo.insert(ctx.p1.id, _full_caps(1))
        result = repo.get(ctx.p1.id)
        for sk in _SKILLS:
            assert result[sk] == 1

    def test_cap_value_at_maximum(self, repo, ctx):
        repo.insert(ctx.p1.id, _full_caps(100))
        result = repo.get(ctx.p1.id)
        for sk in _SKILLS:
            assert result[sk] == 100

    def test_insert_then_get_many_consistent(self, repo, ctx):
        caps = _varied_caps()
        repo.insert(ctx.p1.id, caps)
        single = repo.get(ctx.p1.id)
        many = repo.get_many([ctx.p1.id])
        assert single == many[ctx.p1.id]
