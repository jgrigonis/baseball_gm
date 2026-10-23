# tests/stats/test_formulas.py
from types import SimpleNamespace

import pytest

from src.stats import formulas
from src.stats.analyzer import StatsAnalyzer
from src.stats.batting_stats import BattingStats
from src.stats.pitching_stats import PitchingStats


class TestBatting:

    def test_total_bases(self):
        # 10 hits: 4 singles, 3 doubles, 1 triple, 2 homers
        assert formulas.total_bases(10, 3, 1, 2) == 4 + 6 + 3 + 8

    def test_batting_average(self):
        assert formulas.batting_average(30, 100) == pytest.approx(0.300)

    def test_on_base_pct(self):
        # (H + BB + HBP) / (AB + BB + HBP + SF)
        assert formulas.on_base_pct(30, 10, 2, 100, 3) == pytest.approx(42 / 115)

    def test_slugging_pct(self):
        assert formulas.slugging_pct(45, 100) == pytest.approx(0.450)

    @pytest.mark.parametrize(
        "value",
        [
            formulas.batting_average(0, 0),
            formulas.on_base_pct(0, 0, 0, 0, 0),
            formulas.slugging_pct(0, 0),
        ],
    )
    def test_zero_denominator_is_zero(self, value):
        assert value == 0.0


class TestPitching:

    @pytest.mark.parametrize(
        "outs, expected",
        [(0, "0.0"), (1, "0.1"), (2, "0.2"), (27, "9.0"), (61, "20.1")],
    )
    def test_ip_str(self, outs, expected):
        assert formulas.ip_str(outs) == expected

    def test_innings(self):
        assert formulas.innings(7) == pytest.approx(7 / 3)

    def test_era(self):
        # 3 earned runs in 9 innings
        assert formulas.era(3, 27) == pytest.approx(3.0)
        # 1 earned run in 2.1 innings
        assert formulas.era(1, 7) == pytest.approx(27 / 7)

    def test_per_nine(self):
        assert formulas.per_nine(10, 54) == pytest.approx(5.0)

    def test_whip(self):
        # 6 hits + 3 walks in 6 innings
        assert formulas.whip(6, 3, 18) == pytest.approx(1.5)

    @pytest.mark.parametrize(
        "value",
        [formulas.era(5, 0), formulas.per_nine(5, 0), formulas.whip(5, 5, 0)],
    )
    def test_zero_outs_is_zero(self, value):
        assert value == 0.0


class TestStatsClassesUseFormulas:

    def test_obp_excludes_sac_bunts(self):
        stats = BattingStats(
            at_bats=100, hits=30, walks=10, hbp=2, sac_flys=3, sac_bunts=5
        )
        assert stats.obp == pytest.approx(42 / 115)

    def test_pitching_era_and_whip(self):
        stats = PitchingStats(outs=27, earned_runs=3, hits=6, walks=3)
        assert stats.era == pytest.approx(3.0)
        assert stats.whip == pytest.approx(1.0)
        assert stats.ip_str == "9.0"


class TestAnalyzerEra:

    def test_era_leaderboard_uses_earned_runs(self):
        pitching = PitchingStats(outs=27, runs=5, earned_runs=2)
        player = SimpleNamespace(
            id="p1",
            name="Pitcher",
            game_stats=SimpleNamespace(pitching=pitching),
        )

        (row,) = StatsAnalyzer([player]).leaderboard_era(min_innings=1)

        assert row["era"] == pytest.approx(2.0)
        assert row["earned_runs"] == 2
