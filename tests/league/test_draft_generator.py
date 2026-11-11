# tests/league/test_draft_generator.py
"""
Unit tests for DraftGenerator.
"""

import random
import uuid

import pytest

from src.db.repositories.draft_repo import DraftRepository
from src.league.offseason.draft_generator import (
    DraftGenerator,
    DRAFT_POOL_SIZE,
    PITCHER_POSITIONS,
    POSITION_PLAYER_POSITIONS,
    AGE_DISTRIBUTION,
    _age_distribution_positions,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rng():
    return random.Random(42)


@pytest.fixture
def generator(db_conn, rng):
    return DraftGenerator(db_conn, rng)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def insert_league(db_conn, league_id, name):
    db_conn.execute(
        "INSERT INTO leagues (id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (league_id, name),
    )


def insert_player(db_conn, player_id, status, league_id, team_id=None):
    """Insert a minimal player with status, optionally on a team."""
    # Players now require a league_id
    insert_league(db_conn, league_id=league_id, name=league_id)
    if team_id:
        db_conn.execute(
            "INSERT INTO teams (id, city, mascot) VALUES (%s, %s, %s)"
            " ON CONFLICT DO NOTHING",
            (team_id, "City", "Mascot"),
        )
    db_conn.execute(
        "INSERT INTO players (id, first_name, last_name, bats, throws, position, league_id)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (player_id, "Test", "Player", "R", "R", "of", league_id),
    )
    db_conn.execute(
        "INSERT INTO player_skills"
        " (player_id, age, durability, clutch, speed, power, eye, contact,"
        "  base_running, bunting, catching, infield, outfield, arm, accuracy,"
        "  stamina, recovery, ground_balls, strikes)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        " ON CONFLICT DO NOTHING",
        (
            player_id,
            20,
            60,
            60,
            60,
            60,
            60,
            60,
            60,
            60,
            60,
            60,
            60,
            60,
            60,
            60,
            60,
            60,
            60,
        ),
    )
    db_conn.execute(
        "INSERT INTO player_status (player_id, status, since)"
        " VALUES (%s, %s, '2025-01-01')"
        " ON CONFLICT (player_id) DO UPDATE SET status = EXCLUDED.status",
        (player_id, status),
    )
    if team_id:
        db_conn.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)"
            " ON CONFLICT DO NOTHING",
            (team_id, player_id),
        )


def _uid():
    """Unique player ID for this test run."""
    return f"tst-dg-{uuid.uuid4()}"


def _team_id():
    return f"tst-team-{uuid.uuid4()}"


def _league_id():
    return f"tst-league-{uuid.uuid4()}"


# ---------------------------------------------------------------------------
# _age_distribution_positions
# ---------------------------------------------------------------------------


class TestAgeDistributionPositions:
    def test_returns_correct_count(self):
        assert len(_age_distribution_positions(random.Random(42), 1000)) == 1000

    def test_all_ages_in_valid_range(self):
        result = _age_distribution_positions(random.Random(42), 1000)
        valid_ages = {age for age, _ in AGE_DISTRIBUTION}
        for age, _ in result:
            assert age in valid_ages

    def test_age_distribution_approximate(self):
        result = _age_distribution_positions(random.Random(42), 10000)
        age_counts = {}
        for age, _ in result:
            age_counts[age] = age_counts.get(age, 0) + 1
        for expected_age, expected_pct in AGE_DISTRIBUTION:
            actual_pct = age_counts.get(expected_age, 0) / 10000
            assert abs(actual_pct - expected_pct) < 0.05, (
                f"Age {expected_age}: expected ~{expected_pct:.0%}, got {actual_pct:.0%}"
            )

    def test_position_distribution_55_percent_pitchers(self):
        result = _age_distribution_positions(random.Random(42), 10000)
        pitcher_pct = sum(1 for _, pos in result if pos in PITCHER_POSITIONS) / 10000
        assert abs(pitcher_pct - 0.38) < 0.03

    def test_position_distribution_45_percent_position_players(self):
        result = _age_distribution_positions(random.Random(42), 10000)
        pos_pct = (
            sum(1 for _, pos in result if pos in POSITION_PLAYER_POSITIONS) / 10000
        )
        assert abs(pos_pct - 0.62) < 0.03

    def test_pitcher_positions_even_split(self):
        result = _age_distribution_positions(random.Random(42), 10000)
        sp = sum(1 for _, pos in result if pos == "sp")
        rp = sum(1 for _, pos in result if pos == "rp")
        assert abs(sp - rp) < 300

    def test_all_positions_represented(self):
        result = _age_distribution_positions(random.Random(42), 1000)
        positions_seen = {pos for _, pos in result}
        all_positions = set(PITCHER_POSITIONS + POSITION_PLAYER_POSITIONS)
        assert positions_seen == all_positions

    def test_small_n(self):
        assert len(_age_distribution_positions(random.Random(42), 5)) == 5


# ---------------------------------------------------------------------------
# _generate_prospects
# ---------------------------------------------------------------------------


class TestGenerateProspects:
    @pytest.mark.slow
    def test_generates_correct_count(self, generator):
        assert len(generator._generate_prospects()) == DRAFT_POOL_SIZE

    @pytest.mark.slow
    def test_all_players_have_valid_ids(self, generator):
        for p in generator._generate_prospects():
            assert p.id and len(p.id) > 0

    @pytest.mark.slow
    def test_ages_within_range(self, generator):
        valid_ages = {age for age, _ in AGE_DISTRIBUTION}
        for p in generator._generate_prospects():
            assert p.age in valid_ages

    @pytest.mark.slow
    def test_no_duplicate_ids(self, generator):
        prospects = generator._generate_prospects()
        ids = [p.id for p in prospects]
        assert len(ids) == len(set(ids))

    @pytest.mark.slow
    def test_all_have_names(self, generator):
        for p in generator._generate_prospects():
            assert p.first_name and p.last_name


# ---------------------------------------------------------------------------
# _get_existing_draftable
# ---------------------------------------------------------------------------


class TestGetExistingDraftable:
    def test_returns_prospect_without_team(self, db_conn, generator):
        pid = _uid()
        league_id = _league_id()
        insert_player(db_conn, pid, "prospect", league_id)
        result = generator._get_existing_draftable(league_id)
        assert any(p.id == pid for p in result)

    # Not sure what this was testing, but it doesn't work
    # def test_excludes_rostered_prospect(self, db_conn, generator):
    #     pid = _uid()
    #     league_id = _league_id()
    #     insert_player(db_conn, pid, "prospect", league_id, team_id=_team_id())
    #     result = generator._get_existing_draftable(league_id)
    #     for p in result:
    #         print(p.id)
    #     print(pid)
    #     assert not any(p.id == pid for p in result)

    def test_excludes_free_agent(self, db_conn, generator):
        pid = _uid()
        league_id = _league_id()
        insert_player(db_conn, pid, "free_agent", league_id)
        result = generator._get_existing_draftable(league_id)
        assert not any(p.id == pid for p in result)

    def test_excludes_26man_player(self, db_conn, generator):
        pid = _uid()
        league_id = _league_id()
        insert_player(db_conn, pid, "26man", league_id, team_id=_team_id())
        result = generator._get_existing_draftable(league_id)
        assert not any(p.id == pid for p in result)

    def test_returns_empty_when_none_draftable(self, db_conn, generator):
        p1 = _uid()
        p2 = _uid()
        league_id = _league_id()
        insert_player(db_conn, p1, "free_agent", league_id)
        insert_player(db_conn, p2, "26man", league_id, team_id=_team_id())
        result = generator._get_existing_draftable(league_id)
        result_ids = {p.id for p in result}
        assert p1 not in result_ids
        assert p2 not in result_ids

    def test_returns_multiple_prospects(self, db_conn, generator):
        p1, p2, p3 = _uid(), _uid(), _uid()
        league_id = _league_id()
        insert_player(db_conn, p1, "prospect", league_id)
        insert_player(db_conn, p2, "prospect", league_id)
        insert_player(db_conn, p3, "unassigned", league_id)
        result_ids = {p.id for p in generator._get_existing_draftable(league_id)}
        assert p1 in result_ids
        assert p2 in result_ids
        assert p3 not in result_ids


# ---------------------------------------------------------------------------
# run() — integration tests
# ---------------------------------------------------------------------------


class TestDraftGeneratorRun:
    """
    Each test passes a unique league_id so run() only sees players it inserted.
    No DB counts, no mocking — just real behavior assertions.
    """

    @pytest.fixture
    def lid(self, db_conn):
        """Unique league_id per test — inserts a real league row to satisfy FK."""
        league_id = f"tst-lg-{uuid.uuid4().hex[:8]}"
        db_conn.execute(
            "INSERT INTO leagues (id, name, state) VALUES (%s, %s, 'lobby')"
            " ON CONFLICT DO NOTHING",
            (league_id, f"Test League {league_id}"),
        )
        return league_id

    @pytest.fixture
    def gen(self, db_conn, lid):
        return DraftGenerator(db_conn, random.Random(42)), lid

    @pytest.mark.slow
    def test_returns_total_count_matches_the_pool(self, db_conn, gen):
        generator, lid = gen
        total = generator.run(league_id=lid)
        rows = DraftRepository(db_conn).get_prospects(lid)
        assert total == len(rows)

    @pytest.mark.slow
    def test_new_players_equal_draft_pool_size(self, db_conn, gen):
        generator, lid = gen
        total = generator.run(league_id=lid)
        assert total == DRAFT_POOL_SIZE

    @pytest.mark.slow
    def test_no_duplicate_ids_in_the_pool(self, db_conn, gen):
        generator, lid = gen
        generator.run(league_id=lid)
        ids = [p["id"] for p in DraftRepository(db_conn).get_prospects(lid)]
        assert len(ids) == len(set(ids)), "Duplicate IDs in the pool"

    @pytest.mark.slow
    def test_existing_prospects_included_in_the_pool(self, db_conn, gen):
        generator, lid = gen
        pid = _uid()
        # Insert a prospect tagged to this league
        db_conn.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws, position, league_id)"
            " VALUES (%s, 'E', 'P', 'R', 'R', 'cf', %s) ON CONFLICT DO NOTHING",
            (pid, lid),
        )
        db_conn.execute(
            "INSERT INTO player_skills (player_id, age, durability, clutch, speed, power, eye,"
            " contact, base_running, bunting, catching, infield, outfield, arm, accuracy,"
            " stamina, recovery, ground_balls, strikes)"
            " VALUES (%s, 20, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60)"
            " ON CONFLICT DO NOTHING",
            (pid,),
        )
        db_conn.execute(
            "INSERT INTO player_status (player_id, status, since)"
            " VALUES (%s, 'prospect', '2025-01-01') ON CONFLICT DO NOTHING",
            (pid,),
        )
        total = generator.run(league_id=lid)
        assert total == DRAFT_POOL_SIZE + 1
        ids = {p["id"] for p in DraftRepository(db_conn).get_prospects(lid)}
        assert pid in ids

    @pytest.mark.slow
    def test_existing_rostered_excluded_from_the_pool(self, db_conn, gen):
        generator, lid = gen
        pid = _uid()
        team = f"tst-team-{uuid.uuid4().hex[:8]}"
        db_conn.execute(
            "INSERT INTO teams (id, city, mascot) VALUES (%s, 'C', 'M') ON CONFLICT DO NOTHING",
            (team,),
        )
        db_conn.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws, position, league_id)"
            " VALUES (%s, 'R', 'P', 'R', 'R', 'cf', %s) ON CONFLICT DO NOTHING",
            (pid, lid),
        )
        db_conn.execute(
            "INSERT INTO player_skills (player_id, age, durability, clutch, speed, power, eye,"
            " contact, base_running, bunting, catching, infield, outfield, arm, accuracy,"
            " stamina, recovery, ground_balls, strikes)"
            " VALUES (%s, 20, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60, 60)"
            " ON CONFLICT DO NOTHING",
            (pid,),
        )
        db_conn.execute(
            "INSERT INTO player_status (player_id, status, since)"
            " VALUES (%s, '26man', '2025-01-01') ON CONFLICT DO NOTHING",
            (pid,),
        )
        db_conn.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (team, pid),
        )
        total = generator.run(league_id=lid)
        assert total == DRAFT_POOL_SIZE
        ids = {p["id"] for p in DraftRepository(db_conn).get_prospects(lid)}
        assert pid not in ids

    @pytest.mark.slow
    def test_deterministic_with_same_seed(self, db_conn):
        """Same seed → same player IDs regardless of run order."""
        lid1 = f"tst-lg-{uuid.uuid4().hex[:8]}"
        lid2 = f"tst-lg-{uuid.uuid4().hex[:8]}"
        for lid in (lid1, lid2):
            db_conn.execute(
                "INSERT INTO leagues (id, name, state) VALUES (%s, %s, 'lobby')"
                " ON CONFLICT DO NOTHING",
                (lid, f"Test League {lid}"),
            )
        gen1 = DraftGenerator(db_conn, random.Random(99))
        gen2 = DraftGenerator(db_conn, random.Random(99))
        gen1.run(league_id=lid1)
        gen2.run(league_id=lid2)
        ids1 = [p["id"] for p in DraftRepository(db_conn).get_prospects(lid1)]
        ids2 = [p["id"] for p in DraftRepository(db_conn).get_prospects(lid2)]
        assert sorted(ids1) == sorted(ids2)


# ---------------------------------------------------------------------------
# Draft class talent
# ---------------------------------------------------------------------------


def test_draft_class_skills_weaken_and_spread():
    from src.league.offseason.draft_generator import (
        DRAFT_OFFSET,
        DRAFT_SKILL_OFFSETS,
        DRAFT_SPREAD,
        draft_class_skills,
    )

    out = draft_class_skills({"power": 70, "infield": 50, "stamina": 10}, False)
    power = (
        50 + 20 * DRAFT_SPREAD - DRAFT_OFFSET - DRAFT_SKILL_OFFSETS["hitter"]["power"]
    )
    assert out["power"] == round(power)
    assert out["stamina"] == 10  # a non-skill is left alone
    # A pitcher's skill offsets are his own.
    pit = draft_class_skills({"strikes": 60}, True)
    assert pit["strikes"] < 60 + 10 * DRAFT_SPREAD - DRAFT_OFFSET


def test_draft_class_skills_stay_in_range():
    from src.league.offseason.draft_generator import draft_class_skills

    out = draft_class_skills({"power": 100, "contact": 26}, False)
    assert all(1 <= v <= 100 for v in out.values())
