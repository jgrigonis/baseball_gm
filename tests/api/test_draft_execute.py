# tests/api/test_draft_execute.py
"""
Tests for draft_execute.py.

Coverage:
- execute_blitz_draft guard clauses (not found, wrong state, wrong format)
- State transitions (draft open → complete, league → preseason)
- Preference list respected: human GM picks their top available player
- AI fallback: AI teams pick best available by rating
- Auto-pick flag correct: 0 for preference picks, 1 for AI/fallback picks
- draft_picks table populated correctly
- BlitzDraft._run_snake directly: preference order, fallback, pool exhaustion
"""

import random
import uuid
from unittest.mock import patch, MagicMock

import pytest

from src.api.services.draft_execute import execute_blitz_draft, BlitzDraft
from src.league.offseason.snake_draft import DraftPick, ROUNDS
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

LEAGUE_ID  = "league-1"
SEASON_ID  = "season-1"
DRAFT_ID   = "draft-1"


def _seed_base(db_conn):
    """Minimal rows needed for execute_blitz_draft to run."""
    db_conn.execute(
        "INSERT INTO leagues (id, name, state, mode) VALUES (?, ?, 'draft', 'blitz')",
        (LEAGUE_ID, "Test League"),
    )
    db_conn.execute(
        "INSERT INTO seasons (id, year, name) VALUES (?, ?, ?)",
        (SEASON_ID, 2025, "Season 2025"),
    )
    db_conn.execute(
        "INSERT INTO league_seasons (league_id, season_id) VALUES (?, ?)",
        (LEAGUE_ID, SEASON_ID),
    )
    db_conn.commit()


def _seed_draft(db_conn, state="pending", fmt="preference"):
    db_conn.execute(
        "INSERT INTO drafts (id, league_id, season_id, format, state) VALUES (?, ?, ?, ?, ?)",
        (DRAFT_ID, LEAGUE_ID, SEASON_ID, fmt, state),
    )
    db_conn.commit()


def _seed_team(db_conn, team_id, city="City", mascot="Team"):
    db_conn.execute(
        "INSERT OR IGNORE INTO teams (id, city, mascot) VALUES (?, ?, ?)",
        (team_id, city, mascot),
    )
    db_conn.commit()


def _seed_gm(db_conn, team_id, is_ai=1):
    gm_id = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO gms (id, league_id, team_id, display_name, is_ai) VALUES (?, ?, ?, ?, ?)",
        (gm_id, LEAGUE_ID, team_id, "GM", is_ai),
    )
    db_conn.execute("INSERT INTO gm_profiles (gm_id) VALUES (?)", (gm_id,))
    db_conn.commit()
    return gm_id


def _seed_draft_order(db_conn, team_ids):
    for i, tid in enumerate(team_ids, 1):
        db_conn.execute(
            "INSERT INTO draft_order (draft_id, team_id, pick_position) VALUES (?, ?, ?)",
            (DRAFT_ID, tid, i),
        )
    db_conn.commit()


def _seed_prospect(db_conn, player_id, stamina=50, strikes=50):
    db_conn.execute(
        "INSERT OR IGNORE INTO players (id, first_name, last_name, bats, throws, position)"
        " VALUES (?, 'Test', 'Player', 'R', 'R', 'of')",
        (player_id,),
    )
    db_conn.execute(
        """INSERT OR IGNORE INTO player_skills
           (player_id, age, durability, strikes, stamina, recovery, accuracy, clutch,
            speed, power, arm, eye, contact, base_running,
            bunting, catching, infield, outfield, ground_balls)
           VALUES (?,20,80,?,?,50,50,50,50,50,50,50,50,50,50,50,50,50,50)""",
        (player_id, strikes, stamina),
    )
    db_conn.execute(
        "INSERT OR IGNORE INTO player_status (player_id, status, since)"
        " VALUES (?, 'prospect', '2025-01-01')",
        (player_id,),
    )
    db_conn.commit()


def _make_fake_pick(team_id, pick_num, player_id):
    return DraftPick(
        round=1, pick=pick_num, team_id=team_id, team_name="Test",
        player_id=player_id, player_name="P", age=20,
        position="of", prospect_rating=50,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Guard clauses
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteBlitzDraftGuards:

    def test_raises_if_draft_not_found(self, db_conn):
        with pytest.raises(ValueError, match="not found"):
            execute_blitz_draft("nonexistent-draft", db_conn)

    def test_raises_if_draft_not_pending(self, db_conn):
        _seed_base(db_conn)
        _seed_draft(db_conn, state="complete")
        with pytest.raises(ValueError, match="already in state"):
            execute_blitz_draft(DRAFT_ID, db_conn)

    def test_raises_if_wrong_format(self, db_conn):
        _seed_base(db_conn)
        _seed_draft(db_conn, state="pending", fmt="interactive")
        with pytest.raises(ValueError, match="preference-format"):
            execute_blitz_draft(DRAFT_ID, db_conn)

    def test_raises_if_draft_open(self, db_conn):
        _seed_base(db_conn)
        _seed_draft(db_conn, state="open")
        with pytest.raises(ValueError, match="already in state"):
            execute_blitz_draft(DRAFT_ID, db_conn)


# ─────────────────────────────────────────────────────────────────────────────
# State transitions
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteBlitzDraftStateTransitions:

    @pytest.fixture
    def setup(self, db_conn):
        _seed_base(db_conn)
        _seed_draft(db_conn)
        for tid in ["team-1", "team-2"]:
            _seed_team(db_conn, tid)
            _seed_gm(db_conn, tid, is_ai=1)
        _seed_draft_order(db_conn, ["team-1", "team-2"])
        for i in range(ROUNDS * 2 + 5):
            _seed_prospect(db_conn, f"prospect-{i}")
        return db_conn

    def test_draft_state_becomes_complete(self, setup):
        execute_blitz_draft(DRAFT_ID, setup)
        row = setup.execute(
            "SELECT state FROM drafts WHERE id = ?", (DRAFT_ID,)
        ).fetchone()
        assert row["state"] == "complete"

    def test_league_state_becomes_preseason(self, setup):
        execute_blitz_draft(DRAFT_ID, setup)
        row = setup.execute(
            "SELECT state FROM leagues WHERE id = ?", (LEAGUE_ID,)
        ).fetchone()
        assert row["state"] == "preseason"

    def test_returns_correct_keys(self, setup):
        result = execute_blitz_draft(DRAFT_ID, setup)
        assert set(result.keys()) == {
            "draft_id", "season_id", "picks_made",
            "auto_picks", "rounds", "league_state",
        }

    def test_returns_correct_draft_and_season_ids(self, setup):
        result = execute_blitz_draft(DRAFT_ID, setup)
        assert result["draft_id"] == DRAFT_ID
        assert result["season_id"] == SEASON_ID

    def test_league_state_is_preseason_in_return(self, setup):
        result = execute_blitz_draft(DRAFT_ID, setup)
        assert result["league_state"] == "preseason"

    def test_picks_made_equals_rounds_times_teams(self, setup):
        result = execute_blitz_draft(DRAFT_ID, setup)
        assert result["picks_made"] == ROUNDS * 2


# ─────────────────────────────────────────────────────────────────────────────
# draft_picks table
# ─────────────────────────────────────────────────────────────────────────────

class TestDraftPicksTable:

    @pytest.fixture
    def setup(self, db_conn):
        _seed_base(db_conn)
        _seed_draft(db_conn)
        for tid in ["team-1", "team-2"]:
            _seed_team(db_conn, tid)
            _seed_gm(db_conn, tid, is_ai=1)
        _seed_draft_order(db_conn, ["team-1", "team-2"])
        for i in range(ROUNDS * 2 + 5):
            _seed_prospect(db_conn, f"prospect-{i}")
        return db_conn

    def test_draft_picks_inserted(self, setup):
        execute_blitz_draft(DRAFT_ID, setup)
        count = setup.execute(
            "SELECT COUNT(*) FROM draft_picks WHERE draft_id = ?", (DRAFT_ID,)
        ).fetchone()[0]
        assert count == ROUNDS * 2

    def test_each_player_picked_once(self, setup):
        execute_blitz_draft(DRAFT_ID, setup)
        rows = setup.execute(
            "SELECT player_id, COUNT(*) as c FROM draft_picks"
            " WHERE draft_id = ? GROUP BY player_id HAVING c > 1",
            (DRAFT_ID,),
        ).fetchall()
        assert rows == []

    def test_pick_numbers_sequential(self, setup):
        execute_blitz_draft(DRAFT_ID, setup)
        pick_nums = [
            r[0] for r in setup.execute(
                "SELECT pick_number FROM draft_picks WHERE draft_id = ? ORDER BY pick_number",
                (DRAFT_ID,),
            ).fetchall()
        ]
        assert pick_nums == list(range(1, ROUNDS * 2 + 1))

    def test_all_picks_are_auto_for_ai_teams(self, setup):
        execute_blitz_draft(DRAFT_ID, setup)
        non_auto = setup.execute(
            "SELECT COUNT(*) FROM draft_picks WHERE draft_id = ? AND auto_picked = 0",
            (DRAFT_ID,),
        ).fetchone()[0]
        assert non_auto == 0


# ─────────────────────────────────────────────────────────────────────────────
# Preference list behaviour
# ─────────────────────────────────────────────────────────────────────────────

class TestPreferenceList:

    @pytest.fixture
    def setup(self, db_conn):
        _seed_base(db_conn)
        _seed_draft(db_conn)
        _seed_team(db_conn, "human-team")
        _seed_team(db_conn, "ai-team")
        human_gm_id = _seed_gm(db_conn, "human-team", is_ai=0)
        _seed_gm(db_conn, "ai-team", is_ai=1)
        _seed_draft_order(db_conn, ["human-team", "ai-team"])
        for i in range(ROUNDS * 2 + 5):
            _seed_prospect(db_conn, f"prospect-{i}")
        # Human GM prefers prospect-5 first
        db_conn.execute(
            "INSERT INTO draft_preferences (gm_id, draft_id, player_id, rank)"
            " VALUES (?, ?, ?, ?)",
            (human_gm_id, DRAFT_ID, "prospect-5", 1),
        )
        db_conn.commit()
        return db_conn, human_gm_id

    def test_human_gm_picks_preferred_player(self, setup):
        db_conn, _ = setup
        execute_blitz_draft(DRAFT_ID, db_conn)
        # prospect-5 should be picked by human-team in pick 1
        row = db_conn.execute(
            "SELECT team_id, pick_number FROM draft_picks"
            " WHERE draft_id = ? AND player_id = ?",
            (DRAFT_ID, "prospect-5"),
        ).fetchone()
        assert row["team_id"] == "human-team"
        assert row["pick_number"] == 1

    def test_human_gm_pick_is_not_auto(self, setup):
        db_conn, _ = setup
        execute_blitz_draft(DRAFT_ID, db_conn)
        row = db_conn.execute(
            "SELECT auto_picked FROM draft_picks"
            " WHERE draft_id = ? AND player_id = ?",
            (DRAFT_ID, "prospect-5"),
        ).fetchone()
        assert row["auto_picked"] == 0

    def test_auto_picks_count_correct(self, setup):
        db_conn, _ = setup
        result = execute_blitz_draft(DRAFT_ID, db_conn)
        # auto_picks counts picks where team_id not in gm_preferences.
        # AI team makes ROUNDS picks, all auto. Human team makes ROUNDS picks, none auto.
        assert result["auto_picks"] == ROUNDS


# ─────────────────────────────────────────────────────────────────────────────
# BlitzDraft._run_snake directly
# ─────────────────────────────────────────────────────────────────────────────

def _make_player(pid: str, rating: int = 50) -> PlayerRecord:
    """Create a minimal PlayerRecord for testing."""
    skills = MagicMock(spec=PlayerSkills)
    skills.as_dict.return_value = {}
    p = MagicMock(spec=PlayerRecord)
    p.id = pid
    p.name = pid
    p.age = 20
    p.position = "of"
    p.skills = skills
    return p


def _seed_player_row(db_conn, player_id):
    """Insert a bare player row so team_players FK is satisfied."""
    db_conn.execute(
        "INSERT OR IGNORE INTO players (id, first_name, last_name, bats, throws, position)"
        " VALUES (?, 'Test', 'Player', 'R', 'R', 'of')",
        (player_id,),
    )
    db_conn.commit()


class TestBlitzDraftRunSnake:

    @pytest.fixture
    def blitz(self, db_conn):
        _seed_base(db_conn)
        return BlitzDraft(db_conn, gm_preferences={}, rng=random.Random(42))

    def test_empty_pool_returns_empty(self, blitz):
        order = [{"team_id": "t1", "team_name": "T1"}]
        with patch.object(type(blitz), 'status_repo', create=True):
            picks = blitz._run_snake(order, [])
        assert picks == []

    def test_picks_best_available_when_no_prefs(self, db_conn):
        _seed_base(db_conn)
        _seed_team(db_conn, "t1")
        _seed_gm(db_conn, "t1", is_ai=1)

        blitz = BlitzDraft(db_conn, gm_preferences={}, rng=random.Random(42))
        order = [{"team_id": "t1", "team_name": "T1"}]

        _seed_player_row(db_conn, "p-high")
        _seed_player_row(db_conn, "p-low")
        p_high = _make_player("p-high", rating=90)
        p_low  = _make_player("p-low",  rating=10)
        rated  = [(p_high, 90), (p_low, 10)]

        with patch("src.api.services.draft_execute.PlayerEvaluator") as MockEval:
            MockEval.prospect_rating.return_value = 50
            picks = blitz._run_snake(order, rated)

        assert picks[0].player_id == "p-high"

    def test_human_gm_picks_from_pref_list(self, db_conn):
        _seed_base(db_conn)
        _seed_team(db_conn, "human-team")
        _seed_team(db_conn, "ai-team")
        _seed_gm(db_conn, "human-team", is_ai=0)
        _seed_gm(db_conn, "ai-team", is_ai=1)

        blitz = BlitzDraft(
            db_conn,
            gm_preferences={"human-team": ["p-preferred", "p-other"]},
            rng=random.Random(42),
        )
        order = [{"team_id": "human-team", "team_name": "Humans"}]

        _seed_player_row(db_conn, "p-preferred")
        _seed_player_row(db_conn, "p-other")
        p_pref  = _make_player("p-preferred")
        p_other = _make_player("p-other")
        rated   = [(p_pref, 50), (p_other, 50)]

        with patch("src.api.services.draft_execute.PlayerEvaluator") as MockEval:
            MockEval.prospect_rating.return_value = 50
            picks = blitz._run_snake(order, rated)

        assert picks[0].player_id == "p-preferred"

    def test_falls_back_when_pref_unavailable(self, db_conn):
        _seed_base(db_conn)
        _seed_team(db_conn, "human-team")
        _seed_gm(db_conn, "human-team", is_ai=0)

        # Human prefers p-gone but it's not in the pool
        blitz = BlitzDraft(
            db_conn,
            gm_preferences={"human-team": ["p-gone"]},
            rng=random.Random(42),
        )
        order = [{"team_id": "human-team", "team_name": "Humans"}]

        _seed_player_row(db_conn, "p-available")
        p_available = _make_player("p-available")
        rated = [(p_available, 50)]

        with patch("src.api.services.draft_execute.PlayerEvaluator") as MockEval:
            MockEval.prospect_rating.return_value = 50
            picks = blitz._run_snake(order, rated)

        assert picks[0].player_id == "p-available"

    def test_pool_exhaustion_stops_early(self, db_conn):
        _seed_base(db_conn)
        _seed_team(db_conn, "t1")
        _seed_team(db_conn, "t2")
        _seed_gm(db_conn, "t1", is_ai=1)
        _seed_gm(db_conn, "t2", is_ai=1)

        blitz = BlitzDraft(db_conn, gm_preferences={}, rng=random.Random(42))
        order = [
            {"team_id": "t1", "team_name": "T1"},
            {"team_id": "t2", "team_name": "T2"},
        ]
        # Only 1 player for 2 teams × ROUNDS rounds
        _seed_player_row(db_conn, "only-player")
        rated = [(_make_player("only-player"), 50)]

        with patch("src.api.services.draft_execute.PlayerEvaluator") as MockEval:
            MockEval.prospect_rating.return_value = 50
            picks = blitz._run_snake(order, rated)

        assert len(picks) == 1
