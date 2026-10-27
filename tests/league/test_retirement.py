# tests/league/test_retirement.py
"""
Unit tests for src/league/offseason/retirement.py.

Tests cover:
- retirement_chance: age, playing time, regular cap, form, performance, injuries
- playing_time_share: hitters, starters, relievers, cap
- season_performance and league_baselines
"""

import pytest

from src.league.offseason.retirement import (
    REGULAR_MAX_CHANCE,
    RetirementFactors,
    age_base,
    league_baselines,
    playing_time_share,
    retirement_chance,
    season_performance,
)

# ---------------------------------------------------------------------------
# retirement_chance
# ---------------------------------------------------------------------------


class TestAge:
    def test_never_before_30(self):
        for age in range(17, 30):
            assert retirement_chance(age, RetirementFactors()) == 0.0

    def test_age_base_curve(self):
        assert age_base(30) == pytest.approx(0.02)
        assert age_base(34) == pytest.approx(0.14)
        assert age_base(35) == pytest.approx(0.15)
        assert age_base(38) == pytest.approx(0.42)

    def test_rises_with_age(self):
        factors = RetirementFactors(playing_time=0.5)
        chances = [retirement_chance(age, factors) for age in range(30, 45)]
        assert chances == sorted(chances)

    def test_capped_at_95_percent(self):
        factors = RetirementFactors(ovr_drop=20, below_median=40, season_injuries=5)
        assert retirement_chance(60, factors) == pytest.approx(0.95)


class TestPlayingTime:
    def test_more_playing_time_lowers_the_chance(self):
        chances = [
            retirement_chance(36, RetirementFactors(playing_time=share))
            for share in (0.0, 0.25, 0.5, 0.75, 0.89)
        ]
        assert chances == sorted(chances, reverse=True)

    def test_no_games_raises_the_chance_above_the_age_base(self):
        assert retirement_chance(36, RetirementFactors()) == pytest.approx(
            age_base(36) * 1.4
        )

    def test_regular_is_capped_at_one_percent(self):
        # Old and declining, but played every game
        factors = RetirementFactors(playing_time=0.95, ovr_drop=6, below_median=10)
        assert retirement_chance(40, factors) == pytest.approx(REGULAR_MAX_CHANCE)

    def test_regular_below_the_cap_keeps_the_lower_chance(self):
        assert retirement_chance(31, RetirementFactors(playing_time=1.0)) < 0.01


class TestForm:
    def test_ovr_drop_raises_the_chance(self):
        steady = retirement_chance(35, RetirementFactors(playing_time=0.5))
        dropping = retirement_chance(
            35, RetirementFactors(playing_time=0.5, ovr_drop=5)
        )
        assert dropping == pytest.approx(steady * 1.5)

    def test_below_league_median_raises_the_chance(self):
        steady = retirement_chance(35, RetirementFactors(playing_time=0.5))
        weak = retirement_chance(
            35, RetirementFactors(playing_time=0.5, below_median=10)
        )
        assert weak == pytest.approx(steady * 1.3)

    def test_above_median_and_improving_does_not_lower_it(self):
        steady = retirement_chance(35, RetirementFactors(playing_time=0.5))
        strong = retirement_chance(
            35, RetirementFactors(playing_time=0.5, ovr_drop=-3, below_median=-10)
        )
        assert strong == pytest.approx(steady)

    def test_declining_with_no_games_is_most_likely(self):
        idle_and_declining = RetirementFactors(ovr_drop=4, below_median=8)
        assert retirement_chance(36, idle_and_declining) > 0.5


class TestPerformance:
    def test_great_season_cuts_the_chance(self):
        average = retirement_chance(
            37, RetirementFactors(playing_time=0.6, performance=1.0)
        )
        great = retirement_chance(
            37, RetirementFactors(playing_time=0.6, performance=1.3)
        )
        assert great == pytest.approx(average * 0.2)

    def test_better_seasons_protect_more(self):
        chances = [
            retirement_chance(
                37, RetirementFactors(playing_time=0.6, performance=performance)
            )
            for performance in (1.0, 1.1, 1.2, 1.3, 1.5)
        ]
        assert chances == sorted(chances, reverse=True)

    def test_poor_season_does_not_add(self):
        average = retirement_chance(
            37, RetirementFactors(playing_time=0.6, performance=1.0)
        )
        poor = retirement_chance(
            37, RetirementFactors(playing_time=0.6, performance=0.7)
        )
        assert poor == pytest.approx(average)

    def test_ignored_with_little_playing_time(self):
        without = retirement_chance(37, RetirementFactors(playing_time=0.1))
        with_hot_streak = retirement_chance(
            37, RetirementFactors(playing_time=0.1, performance=1.5)
        )
        assert with_hot_streak == pytest.approx(without)


class TestInjuries:
    def test_injuries_add_for_a_player_who_sat(self):
        healthy = retirement_chance(33, RetirementFactors())
        hurt = retirement_chance(33, RetirementFactors(season_injuries=2))
        assert hurt == pytest.approx(healthy + 0.08)

    def test_injuries_count_less_for_a_player_who_played(self):
        healthy = retirement_chance(33, RetirementFactors(playing_time=0.75))
        hurt = retirement_chance(
            33, RetirementFactors(playing_time=0.75, season_injuries=2)
        )
        assert hurt == pytest.approx(healthy + 0.02)

    def test_injury_bump_is_capped(self):
        some = retirement_chance(33, RetirementFactors(season_injuries=3))
        many = retirement_chance(33, RetirementFactors(season_injuries=10))
        assert many == pytest.approx(some)


# ---------------------------------------------------------------------------
# playing_time_share
# ---------------------------------------------------------------------------


class TestPlayingTimeShare:
    def test_no_stats(self):
        assert playing_time_share(None, 162) == 0.0
        assert playing_time_share({}, 162) == 0.0

    def test_hitter(self):
        assert playing_time_share({"bat_games_played": 81}, 162) == pytest.approx(0.5)

    def test_starter_uses_rotation_turns(self):
        stats = {
            "bat_games_played": 30,
            "pitch_games_played": 29,
            "pitch_games_started": 29,
        }
        # 162 / 5 = 32.4 turns
        assert playing_time_share(stats, 162) == pytest.approx(29 / 32.4)

    def test_reliever_uses_appearances(self):
        stats = {"pitch_games_played": 30, "pitch_games_started": 0}
        assert playing_time_share(stats, 162) == pytest.approx(0.5)

    def test_reliever_scales_with_season_length(self):
        stats = {"pitch_games_played": 30, "pitch_games_started": 0}
        assert playing_time_share(stats, 81) == pytest.approx(1.0)

    def test_capped_at_one(self):
        assert playing_time_share({"bat_games_played": 180}, 174) == 1.0


# ---------------------------------------------------------------------------
# season_performance / league_baselines
# ---------------------------------------------------------------------------


def hitter(ab=400, hits=100, walks=40, hr=10):
    return {
        "bat_ab": ab,
        "bat_hits": hits,
        "bat_doubles": 20,
        "bat_triples": 2,
        "bat_home_runs": hr,
        "bat_walks": walks,
        "bat_hbp": 0,
        "bat_sac_flys": 0,
    }


def pitcher(outs=450, er=60):
    return {"pitch_outs": outs, "pitch_earned_runs": er}


class TestLeagueBaselines:
    def test_league_ops_and_era(self):
        ops, era = league_baselines([hitter(), hitter()], [pitcher(), pitcher()])
        assert ops == pytest.approx(140 / 440 + 154 / 400)
        assert era == pytest.approx(60 * 27 / 450)

    def test_empty(self):
        assert league_baselines([], []) == (None, None)


class TestSeasonPerformance:
    def test_league_average_hitter_is_one(self):
        ops, era = league_baselines([hitter()], [pitcher()])
        assert season_performance(hitter(), False, ops, era) == pytest.approx(1.0)

    def test_better_hitter_is_above_one(self):
        ops, era = league_baselines([hitter()], [pitcher()])
        assert season_performance(hitter(hits=130, hr=25), False, ops, era) > 1.1

    def test_lower_era_is_above_one(self):
        ops, era = league_baselines([hitter()], [pitcher()])
        assert season_performance(pitcher(er=40), True, ops, era) == pytest.approx(1.5)

    def test_scoreless_pitcher_gets_the_top_mark(self):
        ops, era = league_baselines([hitter()], [pitcher()])
        assert season_performance(pitcher(er=0), True, ops, era) == pytest.approx(1.3)

    def test_small_samples_are_ignored(self):
        ops, era = league_baselines([hitter()], [pitcher()])
        assert (
            season_performance(hitter(ab=50, hits=20, walks=5), False, ops, era) is None
        )
        assert season_performance(pitcher(outs=30, er=0), True, ops, era) is None

    def test_no_stats(self):
        assert season_performance(None, False, 0.7, 4.0) is None
