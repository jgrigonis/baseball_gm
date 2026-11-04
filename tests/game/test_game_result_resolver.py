# tests/game/test_game_result_resolver.py

from unittest.mock import MagicMock

from src.game.game_result_resolver import GameResultResolver
from src.game.pitcher_appearance import PitcherAppearance, LeadChange


def make_pitcher(name: str):
    """Create a mock PlayerInGame with a name."""
    p = MagicMock()
    p.name = name
    return p


def make_appearance(
    pitcher, team_id: str, entered_inning: int, finished_game: bool = False
):
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
            appearances,
            lead_changes,
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=3,
            losing_score=1,
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
            make_lead_change(3, "top", "away", home_starter),  # away leads
            make_lead_change(5, "bottom", "home", away_starter),  # home retakes
            make_lead_change(7, "top", "away", home_starter),  # away retakes for good
        ]

        decisions = GameResultResolver.resolve(
            appearances,
            lead_changes,
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=4,
            losing_score=3,
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
            appearances,
            lead_changes,
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=2,
            losing_score=1,
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
            appearances,
            lead_changes,
            winning_team_id=HOME,
            losing_team_id=AWAY,
            winning_score=4,
            losing_score=2,
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
            appearances,
            lead_changes,
            winning_team_id=HOME,
            losing_team_id=AWAY,
            winning_score=3,
            losing_score=2,
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
            appearances,
            lead_changes,
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=3,
            losing_score=1,
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
            appearances,
            lead_changes,
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=3,
            losing_score=2,
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
            appearances,
            lead_changes,
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=8,
            losing_score=1,
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
            appearances,
            lead_changes,
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=5,
            losing_score=2,
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
            appearances,
            [],
            winning_team_id=AWAY,
            losing_team_id=HOME,
            winning_score=1,
            losing_score=0,
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
            appearances,
            lead_changes,
            winning_team_id=HOME,
            losing_team_id=AWAY,
            winning_score=4,
            losing_score=3,
        )

        assert decisions.win is not None
        assert decisions.loss is not None
        assert decisions.loss.pitcher == away_starter
        # Home closer was active in inning 9 bottom — gets the win
        assert decisions.win.pitcher == home_closer
        # No save on a walk-off win (closer is the winner)
        assert decisions.save is None


class TestSaveRules:
    """A save needs the finisher to come in with a lead he could lose."""

    def _resolve(self, lead_at_entry, outs, winning_score=5, losing_score=4):
        starter = make_pitcher("Away Starter")
        closer = make_pitcher("Away Closer")
        closer.game_stats.pitching.outs = outs
        home = make_pitcher("Home Starter")
        appearances = [
            make_appearance(starter, AWAY, 1),
            make_appearance(home, HOME, 1, finished_game=True),
            PitcherAppearance(
                pitcher=closer,
                team_id=AWAY,
                entered_inning=7,
                finished_game=True,
                lead_at_entry=lead_at_entry,
            ),
        ]
        lead_changes = [make_lead_change(1, "top", AWAY, home)]
        return GameResultResolver.resolve(
            appearances, lead_changes, AWAY, HOME, winning_score, losing_score
        )

    def test_save_entering_with_lead_of_three(self):
        assert self._resolve(lead_at_entry=3, outs=3).save is not None

    def test_no_save_entering_tied(self):
        assert self._resolve(lead_at_entry=0, outs=3).save is None

    def test_no_save_entering_with_big_lead_that_shrank(self):
        # Up 6 when he came in, won by 1: not a save over one inning
        assert self._resolve(lead_at_entry=6, outs=3).save is None

    def test_save_for_three_innings_with_big_lead(self):
        assert self._resolve(6, 9, winning_score=9, losing_score=3).save is not None

    def test_no_save_without_recording_an_out(self):
        assert self._resolve(lead_at_entry=2, outs=0).save is None


class TestHolds:
    """MLB's hold: a reliever who comes in with a save situation, gets an
    out, and leaves with the lead, without finishing the game."""

    def _reliever(self, name, team, lead, outs, runners=0, lead_lost=False):
        p = make_pitcher(name)
        p.game_stats.pitching.outs = outs
        return PitcherAppearance(
            pitcher=p,
            team_id=team,
            entered_inning=7,
            lead_at_entry=lead,
            runners_at_entry=runners,
            lead_lost=lead_lost,
        )

    def _resolve(self, *away_relievers, final=(5, 4), closer_lead=1):
        """Away starter, then the given relievers, then an away closer who
        finishes; the home starter goes the distance. Away wins."""
        starter = make_appearance(make_pitcher("Away Starter"), AWAY, 1)
        home = make_appearance(make_pitcher("Home Starter"), HOME, 1, True)
        closer = self._reliever("Closer", AWAY, closer_lead, 3)
        closer.finished_game = True
        appearances = [starter, home, *away_relievers, closer]
        lead_changes = [make_lead_change(1, "top", AWAY, home.pitcher)]
        return GameResultResolver.resolve(appearances, lead_changes, AWAY, HOME, *final)

    def test_setup_man_gets_hold(self):
        setup = self._reliever("Setup", AWAY, lead=2, outs=3)
        decisions = self._resolve(setup)
        assert decisions.holds == [setup]
        assert decisions.save is not None and decisions.save.pitcher.name == "Closer"

    def test_one_out_is_enough(self):
        setup = self._reliever("Setup", AWAY, lead=1, outs=1)
        assert self._resolve(setup).holds == [setup]

    def test_no_hold_without_an_out(self):
        assert self._resolve(self._reliever("Setup", AWAY, 1, 0)).holds == []

    def test_no_hold_entering_tied_or_behind(self):
        assert self._resolve(self._reliever("Setup", AWAY, 0, 3)).holds == []
        assert self._resolve(self._reliever("Setup", AWAY, -1, 3)).holds == []

    def test_no_hold_with_big_lead_and_bases_empty(self):
        assert self._resolve(self._reliever("Setup", AWAY, 4, 3)).holds == []

    def test_hold_with_big_lead_and_tying_run_on_deck(self):
        # Up 4 with two on: the tying run is on deck
        setup = self._reliever("Setup", AWAY, lead=4, outs=1, runners=2)
        assert self._resolve(setup).holds == [setup]

    def test_hold_for_three_innings_with_any_lead(self):
        long_man = self._reliever("Long", AWAY, lead=6, outs=9)
        assert self._resolve(long_man, final=(9, 3)).holds == [long_man]

    def test_no_hold_after_giving_up_the_lead(self):
        setup = self._reliever("Setup", AWAY, 2, 3, lead_lost=True)
        assert self._resolve(setup).holds == []

    def test_several_setup_men_can_each_get_a_hold(self):
        a = self._reliever("Seventh", AWAY, 2, 3)
        b = self._reliever("Eighth", AWAY, 2, 3)
        assert self._resolve(a, b).holds == [a, b]

    def test_finisher_gets_no_hold(self):
        # The closer's lead is too big for a save, and he finished: no hold
        decisions = self._resolve(final=(9, 3), closer_lead=6)
        assert decisions.save is None
        assert decisions.holds == []

    def test_starter_gets_no_hold(self):
        starter = make_pitcher("Away Starter")
        starter.game_stats.pitching.outs = 18
        home = make_appearance(make_pitcher("Home Starter"), HOME, 1, True)
        appearances = [
            PitcherAppearance(starter, AWAY, 1, lead_at_entry=2),
            home,
            self._reliever("Closer", AWAY, 2, 3),
        ]
        appearances[-1].finished_game = True
        decisions = GameResultResolver.resolve(
            appearances,
            [make_lead_change(1, "top", AWAY, home.pitcher)],
            AWAY,
            HOME,
            3,
            1,
        )
        assert decisions.holds == []

    def test_losing_team_setup_man_keeps_hold_when_closer_blows_it(self):
        """Away leads 3-2 in the 8th; the setup man hands it over and the
        closer gives up two in the 9th. Setup man: hold. Closer: no save."""
        away_starter = make_appearance(make_pitcher("Away Starter"), AWAY, 1)
        home_starter = make_appearance(make_pitcher("Home Starter"), HOME, 1)
        setup = self._reliever("Setup", AWAY, lead=1, outs=3)
        closer = self._reliever("Closer", AWAY, 1, 2, lead_lost=True)
        closer.finished_game = True
        home_closer = self._reliever("Home Closer", HOME, -1, 3)
        home_closer.finished_game = True
        appearances = [away_starter, home_starter, setup, home_closer, closer]
        lead_changes = [
            make_lead_change(4, "top", AWAY, home_starter.pitcher),
            make_lead_change(9, "bottom", HOME, closer.pitcher),
        ]
        decisions = GameResultResolver.resolve(
            appearances, lead_changes, HOME, AWAY, 4, 3
        )
        assert decisions.holds == [setup]
        assert decisions.save is None

    def test_no_save_after_blowing_the_lead(self):
        decisions = self._resolve(
            self._reliever("Setup", AWAY, 2, 3),
        )
        decisions.save.lead_lost = True
        assert GameResultResolver._is_save(decisions.save, 1) is False
