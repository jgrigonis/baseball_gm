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
from unittest.mock import patch, MagicMock
import uuid

import pytest

from src.api.services.draft_execute import execute_blitz_draft, BlitzDraft
from src.league.offseason.snake_draft import ROUNDS
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
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


# Doesn't seem to be used
# def _seed_prospects(factory, n, prefix="prospect"):
#     """Insert n prospects via the factory, return their IDs."""
#     ids = []
#     for i in range(n):
#         p = factory.prospect(player_id=f"{prefix}-{i}")
#         ids.append(p.id)
#     return ids


# ─────────────────────────────────────────────────────────────────────────────
# Guard clauses
# ─────────────────────────────────────────────────────────────────────────────


class TestExecuteBlitzDraftGuards:
    def test_raises_if_draft_not_found(self, db_conn):
        with pytest.raises(ValueError, match="not found"):
            execute_blitz_draft("nonexistent-draft", db_conn)

    def test_raises_if_draft_not_pending(self, db_conn, factory):
        draft = factory.draft(state="complete")
        with pytest.raises(ValueError, match="already in state"):
            execute_blitz_draft(draft.id, db_conn)

    def test_raises_if_wrong_format(self, db_conn, factory):
        draft = factory.draft(fmt="interactive")
        with pytest.raises(ValueError, match="preference-format"):
            execute_blitz_draft(draft.id, db_conn)

    def test_raises_if_draft_open(self, db_conn, factory):
        draft = factory.draft(state="open")
        with pytest.raises(ValueError, match="already in state"):
            execute_blitz_draft(draft.id, db_conn)


# ─────────────────────────────────────────────────────────────────────────────
# State transitions
# ─────────────────────────────────────────────────────────────────────────────


class TestExecuteBlitzDraftStateTransitions:
    @pytest.fixture
    def setup(self, db_conn, factory):
        league = factory.league(state="draft")
        season = factory.season()
        factory.league_season(league, season)
        draft = factory.draft(league=league, season=season)
        team1 = factory.team()
        team2 = factory.team()
        factory.gm(team=team1, league=league, is_ai=True)
        factory.gm(team=team2, league=league, is_ai=True)
        factory.draft_order(draft, [team1, team2])
        for i in range(ROUNDS * 2 + 5):
            factory.prospect(league_id=league.id)
        return db_conn, draft, league, season

    def test_draft_state_becomes_complete(self, setup):
        db_conn, draft, _, _ = setup
        execute_blitz_draft(draft.id, db_conn)
        row = db_conn.execute(
            "SELECT state FROM drafts WHERE id = %s", (draft.id,)
        ).fetchone()
        assert row["state"] == "complete"

    def test_league_state_becomes_preseason(self, setup):
        db_conn, draft, league, _ = setup
        execute_blitz_draft(draft.id, db_conn)
        row = db_conn.execute(
            "SELECT state FROM leagues WHERE id = %s", (league.id,)
        ).fetchone()
        assert row["state"] == "preseason"

    def test_returns_correct_keys(self, setup):
        db_conn, draft, _, _ = setup
        result = execute_blitz_draft(draft.id, db_conn)
        assert set(result.keys()) == {
            "draft_id",
            "season_id",
            "picks_made",
            "auto_picks",
            "rounds",
            "league_state",
        }

    def test_returns_correct_draft_and_season_ids(self, setup):
        db_conn, draft, _, season = setup
        result = execute_blitz_draft(draft.id, db_conn)
        assert result["draft_id"] == draft.id
        assert result["season_id"] == season.id

    def test_league_state_is_preseason_in_return(self, setup):
        db_conn, draft, _, _ = setup
        result = execute_blitz_draft(draft.id, db_conn)
        assert result["league_state"] == "preseason"

    def test_picks_made_equals_rounds_times_teams(self, setup):
        db_conn, draft, _, _ = setup
        result = execute_blitz_draft(draft.id, db_conn)
        assert result["picks_made"] == ROUNDS * 2


# ─────────────────────────────────────────────────────────────────────────────
# draft_picks table
# ─────────────────────────────────────────────────────────────────────────────


class TestDraftPicksTable:
    @pytest.fixture
    def setup(self, db_conn, factory):
        league = factory.league(state="draft")
        season = factory.season()
        factory.league_season(league, season)
        draft = factory.draft(league=league, season=season)
        team1 = factory.team()
        team2 = factory.team()
        factory.gm(team=team1, league=league, is_ai=True)
        factory.gm(team=team2, league=league, is_ai=True)
        factory.draft_order(draft, [team1, team2])
        for i in range(ROUNDS * 2 + 5):
            factory.prospect(league_id=league.id)
        return db_conn, draft

    def test_draft_picks_inserted(self, setup):
        db_conn, draft = setup
        execute_blitz_draft(draft.id, db_conn)
        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM draft_picks WHERE draft_id = %s", (draft.id,)
        ).fetchone()["n"]
        assert count == ROUNDS * 2

    def test_each_player_picked_once(self, setup):
        db_conn, draft = setup
        execute_blitz_draft(draft.id, db_conn)
        rows = db_conn.execute(
            "SELECT player_id, COUNT(*) as c FROM draft_picks"
            " WHERE draft_id = %s GROUP BY player_id HAVING COUNT(*) > 1",
            (draft.id,),
        ).fetchall()
        assert rows == []

    def test_pick_numbers_sequential(self, setup):
        db_conn, draft = setup
        execute_blitz_draft(draft.id, db_conn)
        pick_nums = [
            r["pick_number"]
            for r in db_conn.execute(
                "SELECT pick_number FROM draft_picks WHERE draft_id = %s ORDER BY pick_number",
                (draft.id,),
            ).fetchall()
        ]
        assert pick_nums == list(range(1, ROUNDS * 2 + 1))

    def test_all_picks_are_auto_for_ai_teams(self, setup):
        db_conn, draft = setup
        execute_blitz_draft(draft.id, db_conn)
        non_auto = db_conn.execute(
            "SELECT COUNT(*) as n FROM draft_picks WHERE draft_id = %s AND NOT auto_picked",
            (draft.id,),
        ).fetchone()["n"]
        assert non_auto == 0


# ─────────────────────────────────────────────────────────────────────────────
# Preference list behaviour
# ─────────────────────────────────────────────────────────────────────────────


class TestPreferenceList:
    @pytest.fixture
    def setup(self, db_conn, factory):
        league = factory.league(state="draft")
        season = factory.season()
        factory.league_season(league, season)
        draft = factory.draft(league=league, season=season)
        human_team = factory.team()
        ai_team = factory.team()
        human_gm = factory.gm(team=human_team, league=league, is_ai=False)
        factory.gm(team=ai_team, league=league, is_ai=True)
        factory.draft_order(draft, [human_team, ai_team])
        prospects = [
            factory.prospect(league_id=league.id) for _ in range(ROUNDS * 2 + 5)
        ]
        # Human GM prefers the first prospect
        preferred = prospects[0]
        db_conn.execute(
            "INSERT INTO draft_preferences (gm_id, draft_id, player_id, rank)"
            " VALUES (%s, %s, %s, %s)",
            (human_gm.id, draft.id, preferred.id, 1),
        )
        return db_conn, draft, human_team, preferred

    def test_human_gm_picks_preferred_player(self, setup):
        db_conn, draft, human_team, preferred = setup
        execute_blitz_draft(draft.id, db_conn)
        row = db_conn.execute(
            "SELECT team_id, pick_number FROM draft_picks"
            " WHERE draft_id = %s AND player_id = %s",
            (draft.id, preferred.id),
        ).fetchone()
        assert row["team_id"] == human_team.id
        assert row["pick_number"] == 1

    def test_human_gm_pick_is_not_auto(self, setup):
        db_conn, draft, _, preferred = setup
        execute_blitz_draft(draft.id, db_conn)
        row = db_conn.execute(
            "SELECT auto_picked FROM draft_picks"
            " WHERE draft_id = %s AND player_id = %s",
            (draft.id, preferred.id),
        ).fetchone()
        assert row["auto_picked"] == False

    def test_auto_picks_count_correct(self, setup):
        db_conn, draft, _, _ = setup
        result = execute_blitz_draft(draft.id, db_conn)
        # Human team: ROUNDS picks, none auto. AI team: ROUNDS picks, all auto.
        assert result["auto_picks"] == ROUNDS


# ─────────────────────────────────────────────────────────────────────────────
# BlitzDraft._run_snake directly
# ─────────────────────────────────────────────────────────────────────────────


class TestBlitzDraftRunSnake:
    @pytest.fixture
    def blitz(self, db_conn, factory):
        factory.draft()
        return BlitzDraft(
            db_conn,
            league_id=str(uuid.uuid4()),
            gm_preferences={},
            rng=random.Random(42),
        )

    def test_empty_pool_returns_empty(self, blitz):
        order = [{"team_id": "t1", "team_name": "T1"}]
        picks = blitz._run_snake(order, [])
        assert picks == []

    def test_picks_best_available_when_no_prefs(self, db_conn, factory):
        factory.draft()
        team = factory.team()
        factory.gm(team=team)

        blitz = BlitzDraft(
            db_conn,
            league_id=str(uuid.uuid4()),
            gm_preferences={},
            rng=random.Random(42),
        )
        order = [{"team_id": team.id, "team_name": "T1"}]

        hi = factory.player_row()
        lo = factory.player_row()
        p_high = _make_player(hi.id, rating=90)
        p_low = _make_player(lo.id, rating=10)
        rated = [(p_high, 90), (p_low, 10)]

        with patch("src.api.services.draft_execute.PlayerEvaluator") as MockEval:
            MockEval.prospect_rating.return_value = 50
            picks = blitz._run_snake(order, rated)

        assert picks[0].player_id == hi.id

    def test_human_gm_picks_from_pref_list(self, db_conn, factory):
        factory.draft()
        human_team = factory.team()
        ai_team = factory.team()
        factory.gm(team=human_team, is_ai=False)
        factory.gm(team=ai_team, is_ai=True)

        p_pref_row = factory.player_row()
        p_other_row = factory.player_row()

        blitz = BlitzDraft(
            db_conn,
            league_id=str(uuid.uuid4()),
            gm_preferences={human_team.id: [p_pref_row.id, p_other_row.id]},
            rng=random.Random(42),
        )
        order = [{"team_id": human_team.id, "team_name": "Humans"}]

        p_pref = _make_player(p_pref_row.id)
        p_other = _make_player(p_other_row.id)
        rated = [(p_pref, 50), (p_other, 50)]

        with patch("src.api.services.draft_execute.PlayerEvaluator") as MockEval:
            MockEval.prospect_rating.return_value = 50
            picks = blitz._run_snake(order, rated)

        assert picks[0].player_id == p_pref_row.id

    def test_falls_back_when_pref_unavailable(self, db_conn, factory):
        factory.draft()
        human_team = factory.team()
        factory.gm(team=human_team, is_ai=False)

        available_row = factory.player_row()
        league_id = str(uuid.uuid4())
        blitz = BlitzDraft(
            db_conn,
            league_id=league_id,
            gm_preferences={human_team.id: ["p-gone-does-not-exist"]},
            rng=random.Random(42),
        )
        order = [{"team_id": human_team.id, "team_name": "Humans"}]

        rated = [(_make_player(available_row.id), 50)]

        with patch("src.api.services.draft_execute.PlayerEvaluator") as MockEval:
            MockEval.prospect_rating.return_value = 50
            picks = blitz._run_snake(order, rated)

        assert picks[0].player_id == available_row.id

    def test_pool_exhaustion_stops_early(self, db_conn, factory):
        factory.draft()
        team1 = factory.team()
        team2 = factory.team()
        factory.gm(team=team1, is_ai=True)
        factory.gm(team=team2, is_ai=True)

        only = factory.player_row()

        league_id = str(uuid.uuid4())
        blitz = BlitzDraft(
            db_conn, league_id=league_id, gm_preferences={}, rng=random.Random(42)
        )
        order = [
            {"team_id": team1.id, "team_name": "T1"},
            {"team_id": team2.id, "team_name": "T2"},
        ]
        rated = [(_make_player(only.id), 50)]

        with patch("src.api.services.draft_execute.PlayerEvaluator") as MockEval:
            MockEval.prospect_rating.return_value = 50
            picks = blitz._run_snake(order, rated)

        assert len(picks) == 1
