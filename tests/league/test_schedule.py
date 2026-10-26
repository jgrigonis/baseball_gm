# tests/league/test_schedule.py
import logging

import pytest
from datetime import date, timedelta
from collections import Counter
import random

from src.league.schedule import ScheduleGenerator, ScheduledGame, save_schedule_to_db


class TestScheduledGame:
    """Test ScheduledGame dataclass."""

    def test_scheduled_game_creation(self):
        """Test creating a ScheduledGame."""
        game = ScheduledGame(
            id="game-1",
            season_id="season-1",
            home_team_id="team-a",
            away_team_id="team-b",
            game_date=date(2025, 4, 1),
            series_id=None,
        )

        assert game.id == "game-1"
        assert game.season_id == "season-1"
        assert game.home_team_id == "team-a"
        assert game.away_team_id == "team-b"
        assert game.game_date == date(2025, 4, 1)
        assert game.series_id is None

    def test_scheduled_game_with_series(self):
        """Test ScheduledGame with series_id."""
        game = ScheduledGame(
            id="game-1",
            season_id="season-1",
            home_team_id="team-a",
            away_team_id="team-b",
            game_date=date(2025, 4, 1),
            series_id="series-1",
        )

        assert game.series_id == "series-1"


class TestScheduleGenerator:
    """Test ScheduleGenerator class."""

    @pytest.fixture
    def generator(self):
        """Create a generator with seeded RNG for deterministic tests."""
        return ScheduleGenerator(rng=random.Random(42))

    @pytest.fixture
    def four_teams(self):
        """Four team IDs for testing."""
        return ["team-a", "team-b", "team-c", "team-d"]

    # -------------------------------------------------------------------
    # generate_round_robin tests
    # -------------------------------------------------------------------

    def test_round_robin_basic(self, generator, four_teams):
        """Test basic round-robin with 4 teams."""
        matchups = generator.generate_round_robin(
            four_teams, games_per_matchup=1, home_and_away=True
        )

        # 4 teams = 6 pairings (C(4,2))
        # With home_and_away = 2 games per pairing = 12 total games
        assert len(matchups) == 12

    def test_round_robin_correct_pairings(self, generator, four_teams):
        """Test that all team pairings are present."""
        matchups = generator.generate_round_robin(
            four_teams,
            games_per_matchup=1,
            home_and_away=False,  # Easier to verify
        )

        # Convert to set to ignore order
        matchup_set = set(matchups)

        # Should have exactly 6 unique pairings
        assert len(matchup_set) == 6

        # Each team should appear in 3 games (plays 3 other teams)
        all_teams = [team for matchup in matchups for team in matchup]
        team_counts = Counter(all_teams)

        for team in four_teams:
            assert team_counts[team] == 3

    def test_round_robin_home_and_away(self, generator, four_teams):
        """Test that home_and_away creates reciprocal matchups."""
        matchups = generator.generate_round_robin(
            four_teams, games_per_matchup=1, home_and_away=True
        )

        # For each (home, away), should also have (away, home)
        matchup_set = set(matchups)

        for home, away in matchups:
            assert (away, home) in matchup_set

    def test_round_robin_multiple_games_per_series(self, generator, four_teams):
        """Test games_per_series parameter."""
        matchups = generator.generate_round_robin(
            four_teams, games_per_matchup=3, home_and_away=True
        )

        # 6 pairings * 3 games * 2 (home/away) = 36 games
        assert len(matchups) == 36

        # Each specific matchup should appear 3 times
        matchup_counts = Counter(matchups)
        for count in matchup_counts.values():
            assert count == 3

    def test_round_robin_two_teams(self, generator):
        """Test with minimum number of teams."""
        teams = ["team-a", "team-b"]
        matchups = generator.generate_round_robin(
            teams, games_per_matchup=1, home_and_away=True
        )

        # 1 pairing * 2 (home/away) = 2 games
        assert len(matchups) == 2
        assert set(matchups) == {("team-a", "team-b"), ("team-b", "team-a")}

    def test_round_robin_shuffles(self):
        """Test that RNG affects shuffle."""
        teams = ["team-a", "team-b", "team-c"]

        gen1 = ScheduleGenerator(rng=random.Random(1))
        gen2 = ScheduleGenerator(rng=random.Random(2))

        matchups1 = gen1.generate_round_robin(
            teams, games_per_matchup=1, home_and_away=False
        )
        matchups2 = gen2.generate_round_robin(
            teams, games_per_matchup=1, home_and_away=False
        )

        # Same matchups, different order (probably)
        assert set(matchups1) == set(matchups2)
        # Likely different order (not guaranteed but very likely)
        # Just check they're both valid lists
        assert len(matchups1) == len(matchups2) == 3

    def test_round_robin_no_self_play(self, generator, four_teams):
        """Test that no team plays itself."""
        matchups = generator.generate_round_robin(
            four_teams, games_per_matchup=1, home_and_away=True
        )

        for home, away in matchups:
            assert home != away

    # -------------------------------------------------------------------
    # create_schedule tests
    # -------------------------------------------------------------------

    def test_create_schedule_basic(self, generator, four_teams):
        """Test basic schedule creation."""
        schedule = generator.create_schedule(
            season_id="season-1",
            team_ids=four_teams,
            start_date=date(2025, 4, 1),
            games_per_series=1,
            home_and_away=True,
        )

        # 4 teams = 12 games
        assert len(schedule) == 12

        # All games should be ScheduledGame instances
        assert all(isinstance(game, ScheduledGame) for game in schedule)

    def test_create_schedule_game_fields(self, generator, four_teams):
        """Test that all game fields are populated correctly."""
        schedule = generator.create_schedule(
            season_id="season-1",
            team_ids=four_teams,
            start_date=date(2025, 4, 1),
            games_per_series=1,
            home_and_away=True,
        )

        for game in schedule:
            assert game.id  # Has an ID
            assert game.season_id == "season-1"
            assert game.home_team_id in four_teams
            assert game.away_team_id in four_teams
            assert game.home_team_id != game.away_team_id
            assert isinstance(game.game_date, date)
            assert game.series_id is None

    def test_create_schedule_unique_ids(self, generator, four_teams):
        """Test that all game IDs are unique."""
        schedule = generator.create_schedule(
            season_id="season-1",
            team_ids=four_teams,
            start_date=date(2025, 4, 1),
            games_per_series=2,
            home_and_away=True,
        )

        game_ids = [game.id for game in schedule]
        assert len(game_ids) == len(set(game_ids))

    def test_create_schedule_date_progression(self, generator, four_teams):
        """Test that dates progress correctly."""
        start = date(2025, 4, 1)
        schedule = generator.create_schedule(
            season_id="season-1",
            team_ids=four_teams,
            start_date=start,
            games_per_series=1,
            home_and_away=True,
        )

        # Dates should be monotonically increasing or equal
        dates = [game.game_date for game in schedule]
        for i in range(len(dates) - 1):
            assert dates[i] <= dates[i + 1]

        # First game should be on start date
        assert schedule[0].game_date == start

    def test_create_schedule_date_advancement(self, generator, four_teams):
        """Test that dates advance after each round."""
        start = date(2025, 4, 1)
        schedule = generator.create_schedule(
            season_id="season-1",
            team_ids=four_teams,
            start_date=start,
            games_per_series=1,
            home_and_away=True,
        )

        # With 4 teams, 2 games per round (4 // 2)
        # After game 2, 4, 6, 8, 10, 12 should advance date
        # Collect unique dates
        unique_dates = sorted(set(game.game_date for game in schedule))

        # Should span multiple days
        assert len(unique_dates) > 1

        # Dates should be consecutive days
        for i in range(len(unique_dates) - 1):
            assert unique_dates[i + 1] - unique_dates[i] == timedelta(days=1)

    def test_create_schedule_matchup_coverage(self, generator, four_teams):
        """Test that all expected matchups are scheduled."""
        schedule = generator.create_schedule(
            season_id="season-1",
            team_ids=four_teams,
            start_date=date(2025, 4, 1),
            games_per_series=2,
            home_and_away=True,
        )

        # Extract matchups from schedule
        matchups = [(g.home_team_id, g.away_team_id) for g in schedule]
        matchup_counts = Counter(matchups)

        # Each specific ordered matchup (home, away) should appear exactly games_per_series times
        for count in matchup_counts.values():
            assert count == 2

        # Total should be 6 unique pairings * 2 games * 2 (home/away) = 24
        assert len(schedule) == 24


class TestSeasonSchedule:
    """Test target_games schedules: whole cycles with 2/3/4-game rounds."""

    @staticmethod
    def build(num_teams, target_games=162, break_after=None, break_days=0, seed=7):
        teams = [f"team-{i}" for i in range(num_teams)]
        schedule = ScheduleGenerator(rng=random.Random(seed)).create_schedule(
            season_id="season-1",
            team_ids=teams,
            start_date=date(2025, 4, 1),
            target_games=target_games,
            all_star_break_after=break_after,
            all_star_break_days=break_days,
        )
        return teams, schedule

    @pytest.mark.parametrize(
        "num_teams, expected",
        [
            (16, (4, 18, 2)),
            (18, (3, 9, 4)),
            (20, (3, 9, 2)),
            (22, (3, 27, 2)),
            (24, (2, 24, 4)),
            (26, (2, 12, 4)),
            (28, (2, 0, 3)),
            (30, (2, 12, 2)),
            (32, (2, 24, 2)),
        ],
    )
    def test_season_shape(self, num_teams, expected):
        cycles, off_rounds, off_length = ScheduleGenerator.season_shape(num_teams, 162)
        assert (cycles, off_rounds) == expected[:2]
        if off_rounds:
            assert off_length == expected[2]

    def test_odd_team_count_rejected(self):
        with pytest.raises(ValueError, match="even"):
            ScheduleGenerator.season_shape(17, 162)

    @pytest.mark.parametrize("num_teams", range(16, 34, 2))
    def test_every_team_plays_target_games_once_a_day(self, num_teams):
        teams, schedule = self.build(num_teams)

        games = Counter()
        playing_on = Counter()
        for g in schedule:
            games[g.home_team_id] += 1
            games[g.away_team_id] += 1
            playing_on[(g.game_date, g.home_team_id)] += 1
            playing_on[(g.game_date, g.away_team_id)] += 1

        assert set(games.values()) == {162}
        assert set(playing_on.values()) == {1}
        # No off days without a break: every team plays every day.
        assert len({g.game_date for g in schedule}) == 162

    def test_thirty_teams_split_home_and_away_evenly(self):
        teams, schedule = self.build(30)

        ordered = Counter((g.home_team_id, g.away_team_id) for g in schedule)
        home = Counter(g.home_team_id for g in schedule)

        assert set(home.values()) == {81}
        for (h, a), count in ordered.items():
            assert ordered[(a, h)] == count
        # Every pair meets home and away; 6 pairs per team play 2-game series.
        assert set(ordered.values()) == {2, 3}

    def test_all_star_break(self):
        teams, schedule = self.build(30, break_after=96, break_days=4)

        dates = sorted({g.game_date for g in schedule})
        gaps = [
            (before, (after - before).days - 1)
            for before, after in zip(dates, dates[1:])
            if (after - before).days > 1
        ]
        assert len(gaps) == 1
        last_before_break, days_off = gaps[0]
        assert days_off == 4
        assert dates[-1] - dates[0] == timedelta(days=162 + 4 - 1)

        games_before = sum(
            1
            for g in schedule
            if g.game_date <= last_before_break
            and "team-0" in (g.home_team_id, g.away_team_id)
        )
        assert abs(games_before - 96) <= 2


class TestSaveScheduleToDB:
    """Test save_schedule_to_db function."""

    # Fails due to DB pollution
    # def test_save_empty_schedule(self, db_conn, capsys):
    #     """Test saving empty schedule."""
    #     save_schedule_to_db(db_conn, [])

    #     count = db_conn.execute("SELECT COUNT(*) AS c FROM games").fetchone()["c"]
    #     assert count == 0

    #     captured = capsys.readouterr()
    #     assert "Saved 0 games" in captured.out

    def test_save_single_game(self, db_conn, factory, caplog):
        """Test saving a single game."""
        season = factory.season()
        team_a = factory.team()
        team_b = factory.team()

        import uuid

        game_id = str(uuid.uuid4())
        schedule = [
            ScheduledGame(
                id=game_id,
                season_id=season.id,
                home_team_id=team_a.id,
                away_team_id=team_b.id,
                game_date=date(2025, 4, 1),
                series_id=None,
            )
        ]

        with caplog.at_level(logging.INFO):
            save_schedule_to_db(db_conn, schedule)

        row = db_conn.execute(
            "SELECT * FROM games WHERE id = %s", (game_id,)
        ).fetchone()

        assert row is not None
        assert row["id"] == game_id
        assert row["season_id"] == season.id
        assert row["home_team_id"] == team_a.id
        assert row["away_team_id"] == team_b.id
        assert row["game_date"] == "2025-04-01"

        assert "Saved 1 games" in caplog.text

    def test_save_multiple_games(self, db_conn, factory):
        """Test saving multiple games."""
        import uuid

        season = factory.season()
        team_a = factory.team()
        team_b = factory.team()

        schedule = [
            ScheduledGame(
                id=str(uuid.uuid4()),
                season_id=season.id,
                home_team_id=team_a.id,
                away_team_id=team_b.id,
                game_date=date(2025, 4, i),
                series_id=None,
            )
            for i in range(1, 6)
        ]

        save_schedule_to_db(db_conn, schedule)

        count = db_conn.execute(
            "SELECT COUNT(*) AS c FROM games WHERE season_id = %s", (season.id,)
        ).fetchone()["c"]
        assert count == 5

    def test_save_full_schedule(self, db_conn, factory):
        """Test saving a complete generated schedule."""
        generator = ScheduleGenerator(rng=random.Random(42))
        season = factory.season()
        teams = [factory.team() for _ in range(4)]
        team_ids = [t.id for t in teams]

        schedule = generator.create_schedule(
            season_id=season.id,
            team_ids=team_ids,
            start_date=date(2025, 4, 1),
            games_per_series=3,
            home_and_away=True,
        )

        save_schedule_to_db(db_conn, schedule)

        # 4 teams, 6 pairings, 3 games, home/away = 36
        count = db_conn.execute(
            "SELECT COUNT(*) AS c FROM games WHERE season_id = %s", (season.id,)
        ).fetchone()["c"]
        assert count == 36

    def test_save_preserves_all_fields(self, db_conn, factory):
        """Test that all fields are correctly saved."""
        import uuid

        season = factory.season()
        home_team = factory.team()
        away_team = factory.team()

        game_id = str(uuid.uuid4())
        game = ScheduledGame(
            id=game_id,
            season_id=season.id,
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            game_date=date(2025, 12, 25),
            series_id=None,
        )

        save_schedule_to_db(db_conn, [game])

        row = db_conn.execute(
            "SELECT * FROM games WHERE id = %s", (game_id,)
        ).fetchone()

        assert row["id"] == game_id
        assert row["season_id"] == season.id
        assert row["home_team_id"] == home_team.id
        assert row["away_team_id"] == away_team.id
        assert row["game_date"] == "2025-12-25"
        assert row["series_id"] is None
