# tests/game/test_game_result_resolver.py

import pytest
from unittest.mock import MagicMock

from src.game.game_result_resolver import GameResultResolver, PitchingDecisions
from src.game.pitcher_appearance import PitcherAppearance, LeadChange


def make_pitcher(name: str):
    """Create a mock PlayerInGame with a name."""
    p = MagicMock()
    p.name = name
    return p


def make_appearance(pitcher, team_id: str, entered_inning: int, finished_game: bool = False):
    return PitcherAppearance(
        pitcher=pitcher,
        team_id=team_id,
        entered_inning=entered_inning,
        finished_game=finished_game,
    )


def make_lead_change(inning: int, half: str, new_leader: str, responsible_pitcher):
    return LeadChange(
        inning=inning,
        half=half,
        new_leader=new_leader,
        responsible_pitcher=responsible_pitcher,
    )


HOME = "home-team"
AWAY = "away-team"


class TestWin:
    def test_starter_gets_win_when_no_changes(self):
        away_starter = make_pitcher("Away Starter")
        home_starter = make_pitcher("Home Starter")

        appearances = [
            make_appearance(away_starter, AWAY, 1, finished_game=False),
            make_appearance(home_starter, HOME, 1, finished_game=True),
        ]
        # Away takes lead in top 1, never relinquished
        lead_changes = [
            make_lead_change(1, "top", "away", home_starter),
        ]

        decisions = GameResultResolver.resolve(
            appearances, lead_changes,
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=3, losing_score=1,
        )

        assert decisions.win is not None
        assert decisions.win.pitcher == away_starter

    def test_reliever_gets_win_when_active_at_go_ahead(self):
        away_starter = make_pitcher("Away Starter")
        away_reliever = make_pitcher("Away Reliever")
        home_starter = make_pitcher("Home Starter")

        appearances = [
            make_appearance(away_starter, AWAY, 1),
            make_appearance(home_starter, HOME, 1),
            make_appearance(away_reliever, AWAY, 6, finished_game=True),
        ]
        # Go-ahead run scored in top 7, away reliever was pitching for away (defense),
        # but we want the away team's pitcher who was on mound when away took the lead.
        # Away takes lead in top 7 — away_reliever entered inning 6, so active in 7.
        lead_changes = [
            make_lead_change(3, "top", "away", home_starter),   # away leads
            make_lead_change(5, "bottom", "home", away_starter), # home retakes
            make_lead_change(7, "top", "away", home_starter),   # away retakes for good
        ]

        decisions = GameResultResolver.resolve(
            appearances, lead_changes,
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=4, losing_score=3,
        )

        assert decisions.win is not None
        assert decisions.win.pitcher == away_reliever

    def test_starter_gets_win_when_reliever_entered_after_go_ahead(self):
        away_starter = make_pitcher("Away Starter")
        away_closer = make_pitcher("Away Closer")
        home_starter = make_pitcher("Home Starter")

        appearances = [
            make_appearance(away_starter, AWAY, 1),
            make_appearance(home_starter, HOME, 1),
            make_appearance(away_closer, AWAY, 9, finished_game=True),
        ]
        # Away starter pitching when go-ahead scored in top 5
        lead_changes = [
            make_lead_change(5, "top", "away", home_starter),
        ]

        decisions = GameResultResolver.resolve(
            appearances, lead_changes,
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=2, losing_score=1,
        )

        assert decisions.win is not None
        assert decisions.win.pitcher == away_starter


class TestLoss:
    def test_starter_gets_loss_for_go_ahead(self):
        away_starter = make_pitcher("Away Starter")
        home_starter = make_pitcher("Home Starter")

        appearances = [
            make_appearance(away_starter, AWAY, 1, finished_game=True),
            make_appearance(home_starter, HOME, 1, finished_game=False),
        ]
        # Home takes go-ahead lead in bottom 6 off away starter
        lead_changes = [
            make_lead_change(6, "bottom", "home", away_starter),
        ]

        decisions = GameResultResolver.resolve(
            appearances, lead_changes,
            winning_team_id=HOME,
            losing_team_id=AWAY,
            winning_score=4, losing_score=2,
        )

        assert decisions.loss is not None
        assert decisions.loss.pitcher == away_starter

    def test_reliever_gets_loss_for_go_ahead(self):
        away_starter = make_pitcher("Away Starter")
        away_reliever = make_pitcher("Away Reliever")
        home_starter = make_pitcher("Home Starter")

        appearances = [
            make_appearance(away_starter, AWAY, 1),
            make_appearance(away_reliever, AWAY, 7, finished_game=True),
            make_appearance(home_starter, HOME, 1, finished_game=False),
        ]
        # Home takes go-ahead off away reliever in bottom 8
        lead_changes = [
            make_lead_change(8, "bottom", "home", away_reliever),
        ]

        decisions = GameResultResolver.resolve(
            appearances, lead_changes,
            winning_team_id=HOME,
            losing_team_id=AWAY,
            winning_score=3, losing_score=2,
        )

        assert decisions.loss is not None
        assert decisions.loss.pitcher == away_reliever


class TestSave:
    def test_no_save_when_finisher_is_winner(self):
        away_starter = make_pitcher("Away Starter")
        home_starter = make_pitcher("Home Starter")

        appearances = [
            make_appearance(away_starter, AWAY, 1, finished_game=True),
            make_appearance(home_starter, HOME, 1, finished_game=False),
        ]
        lead_changes = [
            make_lead_change(1, "top", "away", home_starter),
        ]

        decisions = GameResultResolver.resolve(
            appearances, lead_changes,
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=3, losing_score=1,
        )

        assert decisions.save is None

    def test_save_when_closer_finishes_close_game(self):
        away_starter = make_pitcher("Away Starter")
        away_closer = make_pitcher("Away Closer")
        home_starter = make_pitcher("Home Starter")

        appearances = [
            make_appearance(away_starter, AWAY, 1),
            make_appearance(home_starter, HOME, 1, finished_game=True),
            make_appearance(away_closer, AWAY, 9, finished_game=True),
        ]
        lead_changes = [
            make_lead_change(1, "top", "away", home_starter),
        ]

        decisions = GameResultResolver.resolve(
            appearances, lead_changes,
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=3, losing_score=2,
        )

        assert decisions.save is not None
        assert decisions.save.pitcher == away_closer

    def test_no_save_when_margin_too_large(self):
        away_starter = make_pitcher("Away Starter")
        away_closer = make_pitcher("Away Closer")
        home_starter = make_pitcher("Home Starter")

        appearances = [
            make_appearance(away_starter, AWAY, 1),
            make_appearance(home_starter, HOME, 1, finished_game=True),
            make_appearance(away_closer, AWAY, 9, finished_game=True),
        ]
        lead_changes = [
            make_lead_change(1, "top", "away", home_starter),
        ]

        decisions = GameResultResolver.resolve(
            appearances, lead_changes,
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=8, losing_score=1,
        )

        assert decisions.save is None

    def test_save_with_margin_exactly_3(self):
        away_starter = make_pitcher("Away Starter")
        away_closer = make_pitcher("Away Closer")
        home_starter = make_pitcher("Home Starter")

        appearances = [
            make_appearance(away_starter, AWAY, 1),
            make_appearance(home_starter, HOME, 1, finished_game=True),
            make_appearance(away_closer, AWAY, 9, finished_game=True),
        ]
        lead_changes = [
            make_lead_change(1, "top", "away", home_starter),
        ]

        decisions = GameResultResolver.resolve(
            appearances, lead_changes,
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=5, losing_score=2,
        )

        assert decisions.save is not None
        assert decisions.save.pitcher == away_closer


class TestEdgeCases:
    def test_no_lead_changes_means_no_decisions(self):
        """Shouldn't happen in a real game but resolver should not crash."""
        away_starter = make_pitcher("Away Starter")
        home_starter = make_pitcher("Home Starter")

        appearances = [
            make_appearance(away_starter, AWAY, 1, finished_game=True),
            make_appearance(home_starter, HOME, 1, finished_game=False),
        ]

        decisions = GameResultResolver.resolve(
            appearances, [],
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=1, losing_score=0,
        )

        assert decisions.win is None
        assert decisions.loss is None
        assert decisions.save is None

    def test_walkoff_home_win(self):
        """Home team wins in bottom 9 — final lead change is bottom half."""
        away_starter = make_pitcher("Away Starter")
        home_starter = make_pitcher("Home Starter")
        home_closer = make_pitcher("Home Closer")

        appearances = [
            make_appearance(away_starter, AWAY, 1, finished_game=True),
            make_appearance(home_starter, HOME, 1),
            make_appearance(home_closer, HOME, 9, finished_game=True),
        ]
        lead_changes = [
            make_lead_change(1, "top", "away", home_starter),
            make_lead_change(9, "bottom", "home", away_starter),  # walk-off
        ]

        decisions = GameResultResolver.resolve(
            appearances, lead_changes,
            winning_team_id=HOME,
            losing_team_id=AWAY,
            winning_score=4, losing_score=3,
        )

        assert decisions.win is not None
        assert decisions.loss is not None
        assert decisions.loss.pitcher == away_starter
        # Home closer was active in inning 9 bottom — gets the win
        assert decisions.win.pitcher == home_closer
        # No save on a walk-off win (closer is the winner)
        assert decisions.save is None
