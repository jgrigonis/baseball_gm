# src/league/schedule.py
from dataclasses import dataclass
from datetime import date, timedelta
import itertools
import random
import uuid

from src.db.repositories.games_repo import GameRepository


@dataclass
class ScheduledGame:
    """A single scheduled game."""

    id: str
    season_id: str
    home_team_id: str
    away_team_id: str
    game_date: date
    series_id: str | None = None


class ScheduleGenerator:
    """Generate game schedules for a season."""

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def generate_round_robin(
        self,
        team_ids: list[str],
        games_per_matchup: int = 1,
        home_and_away: bool = True,
    ) -> list[tuple[str, str]]:
        """
        Generate round-robin matchups.
        Not currently used
        """
        matchups = []

        for home, away in itertools.combinations(team_ids, 2):
            for _ in range(games_per_matchup):
                matchups.append((home, away))
                if home_and_away:
                    matchups.append((away, home))

        self.rng.shuffle(matchups)
        return matchups

    def _circle_rounds(self, team_ids: list[str]) -> list[list[tuple[str, str]]]:
        """
        Generate round-robin rounds via the circle algorithm.

        Each round contains n/2 matchups covering every team exactly once.
        With n teams there are n-1 rounds total. If n is odd, a bye is
        inserted to make it even.
        """
        teams = list(team_ids)
        if len(teams) % 2 == 1:
            teams.append("__bye__")  # phantom team for odd counts

        n = len(teams)
        fixed = teams[0]
        rotating = teams[1:]
        rounds = []

        for _ in range(n - 1):
            round_pairs = [(fixed, rotating[0])]
            for i in range(1, n // 2):
                round_pairs.append((rotating[-(i)], rotating[i]))
            rounds.append(round_pairs)
            rotating = [rotating[-1]] + rotating[:-1]  # rotate right by 1

        return rounds

    def generate_series_matchups(
        self,
        team_ids: list[str],
        home_and_away: bool = True,
    ) -> list[tuple[str, str]]:
        """
        Generate series-level matchups using the circle algorithm so every
        team plays in every scheduling round with no gaps.

        Home/away is assigned randomly per matchup. If home_and_away, a
        return series with flipped sides is appended in a second shuffled
        pass of rounds.
        """
        rounds = self._circle_rounds(team_ids)
        self.rng.shuffle(rounds)

        matchups: list[tuple[str, str]] = []
        for round_pairs in rounds:
            pairs = list(round_pairs)
            self.rng.shuffle(pairs)
            for a, b in pairs:
                if "__bye__" in (a, b):
                    continue
                home, away = (a, b) if self.rng.random() < 0.5 else (b, a)
                matchups.append((home, away))

        if home_and_away:
            return_rounds = self._circle_rounds(team_ids)
            self.rng.shuffle(return_rounds)
            for round_pairs in return_rounds:
                pairs = list(round_pairs)
                self.rng.shuffle(pairs)
                for a, b in pairs:
                    if "__bye__" in (a, b):
                        continue
                    # Flip home/away for the return leg
                    away, home = (a, b) if self.rng.random() < 0.5 else (b, a)
                    matchups.append((home, away))

        return matchups

    def create_schedule(
        self,
        season_id: str,
        team_ids: list[str],
        start_date: date,
        games_per_series: int = 3,
        home_and_away: bool = True,
    ) -> list[ScheduledGame]:
        """
        Create a full season schedule built around 3-game series with no gaps.

        The circle algorithm guarantees every team plays in every round, so
        series can be laid out round by round with no team ever sitting idle
        while others are playing.
        """
        matchups = self.generate_series_matchups(team_ids, home_and_away)

        # matchups arrive in round order: n//2 matchups per round, each round
        # is games_per_series days wide.
        games_per_round = len(team_ids) // 2
        schedule: list[ScheduledGame] = []

        for i, (home_id, away_id) in enumerate(matchups):
            round_index = i // games_per_round
            series_start = start_date + timedelta(days=round_index * games_per_series)
            for day_offset in range(games_per_series):
                schedule.append(
                    ScheduledGame(
                        id=str(uuid.uuid4()),
                        season_id=season_id,
                        home_team_id=home_id,
                        away_team_id=away_id,
                        game_date=series_start + timedelta(days=day_offset),
                    )
                )

        schedule.sort(key=lambda g: g.game_date)
        return schedule


    # def generate_series_matchups(
    #     self,
    #     team_ids: list[str],
    #     home_and_away: bool = True,
    # ) -> list[tuple[str, str]]:
    #     """
    #     Generate series-level matchups (one entry = one full series).

    #     Each pair gets a home series and, if home_and_away, a return series at
    #     the other park. All series are shuffled together so neither leg is
    #     guaranteed to precede the other.
    #     """
    #     matchups: list[tuple[str, str]] = []
    #     for home, away in itertools.combinations(team_ids, 2):
    #         matchups.append((home, away))
    #         if home_and_away:
    #             matchups.append((away, home))

    #     self.rng.shuffle(matchups)
    #     return matchups
        
    # def generate_series_matchups(
    #     self,
    #     team_ids: list[str],
    #     home_and_away: bool = True,
    # ) -> list[tuple[str, str]]:
    #     """
    #     Generate series-level matchups (one entry = one full series).

    #     Each pair gets a home series and, if home_and_away, a return series at
    #     the other park. The list is shuffled so series are interleaved across
    #     the calendar rather than grouped by team.
    #     """
    #     pairs = list(itertools.combinations(team_ids, 2))
    #     self.rng.shuffle(pairs)

    #     matchups: list[tuple[str, str]] = []
    #     for home, away in pairs:
    #         # Randomly decide which leg comes first
    #         if self.rng.random() < 0.5:
    #             matchups.append((home, away))
    #             if home_and_away:
    #                 matchups.append((away, home))
    #         else:
    #             if home_and_away:
    #                 matchups.append((away, home))
    #             matchups.append((home, away))

    #     return matchups

    # def create_schedule(
    #     self,
    #     season_id: str,
    #     team_ids: list[str],
    #     start_date: date,
    #     games_per_matchup: int = 3,
    #     home_and_away: bool = True,
    # ) -> list[ScheduledGame]:
    #     """Create a full season schedule."""
    #     matchups = self.generate_round_robin(team_ids, games_per_matchup, home_and_away)

    #     schedule = []
    #     current_date = start_date
    #     remaining = list(matchups)

    #     while remaining:
    #         # Build today's slate: each team plays at most once
    #         todays_games = []
    #         used_teams = set()
    #         leftover = []

    #         for home_id, away_id in remaining:
    #             if home_id not in used_teams and away_id not in used_teams:
    #                 todays_games.append((home_id, away_id))
    #                 used_teams.add(home_id)
    #                 used_teams.add(away_id)
    #             else:
    #                 leftover.append((home_id, away_id))

    #         for home_id, away_id in todays_games:
    #             schedule.append(
    #                 ScheduledGame(
    #                     id=str(uuid.uuid4()),
    #                     season_id=season_id,
    #                     home_team_id=home_id,
    #                     away_team_id=away_id,
    #                     game_date=current_date,
    #                     series_id=None,
    #                 )
    #             )

    #         remaining = leftover
    #         current_date += timedelta(days=1)

    #     return schedule



    # def create_schedule(
    #     self,
    #     season_id: str,
    #     team_ids: list[str],
    #     start_date: date,
    #     games_per_series: int = 3,
    #     home_and_away: bool = True,
    # ) -> list[ScheduledGame]:
    #     """
    #     Create a full season schedule built around 3-game series.

    #     Each series occupies `games_per_series` consecutive days at the home
    #     park. On any given day a team can appear in at most one series. Series
    #     that cannot start because both teams are already committed are deferred
    #     to the next available window.
    #     """
    #     series_matchups = self.generate_series_matchups(team_ids, home_and_away)

    #     team_free_from: dict[str, date] = {t: start_date for t in team_ids}

    #     schedule: list[ScheduledGame] = []
    #     remaining = list(series_matchups)

    #     while remaining:
    #         placed_any = False
    #         still_remaining: list[tuple[str, str]] = []

    #         for home_id, away_id in remaining:
    #             series_start = max(team_free_from[home_id], team_free_from[away_id])

    #             if placed_any:
    #                 still_remaining.append((home_id, away_id))
    #                 continue

    #             for day_offset in range(games_per_series):
    #                 game_date = series_start + timedelta(days=day_offset)
    #                 schedule.append(
    #                     ScheduledGame(
    #                         id=str(uuid.uuid4()),
    #                         season_id=season_id,
    #                         home_team_id=home_id,
    #                         away_team_id=away_id,
    #                         game_date=game_date,
    #                     )
    #                 )

    #             series_end_exclusive = series_start + timedelta(days=games_per_series)
    #             team_free_from[home_id] = series_end_exclusive
    #             team_free_from[away_id] = series_end_exclusive
    #             placed_any = True

    #         if not placed_any and remaining:
    #             earliest_team = min(team_free_from, key=lambda t: team_free_from[t])
    #             team_free_from[earliest_team] += timedelta(days=1)
    #             still_remaining = remaining

    #         remaining = still_remaining

    #     schedule.sort(key=lambda g: g.game_date)
    #     return schedule


    # def create_schedule(
    #     self,
    #     season_id: str,
    #     team_ids: list[str],
    #     start_date: date,
    #     games_per_series: int = 3,
    #     home_and_away: bool = True,
    # ) -> list[ScheduledGame]:
    #     """
    #     Create a full season schedule built around 3-game series.

    #     Each series occupies `games_per_series` consecutive days at the home
    #     park. Series are packed greedily: each pass finds the earliest date any
    #     team is free, then schedules as many non-conflicting series as possible
    #     starting on that date before moving on.
    #     """
    #     series_matchups = self.generate_series_matchups(team_ids, home_and_away)

    #     team_free_from: dict[str, date] = {t: start_date for t in team_ids}

    #     schedule: list[ScheduledGame] = []
    #     remaining = list(series_matchups)

    #     while remaining:
    #         # Find the earliest date any team becomes free — that's our next slot.
    #         slot_date = min(team_free_from[t] for t in team_ids)

    #         placed_in_slot: set[str] = set()
    #         still_remaining: list[tuple[str, str]] = []

    #         for home_id, away_id in remaining:
    #             # Both teams must be free by the slot date and not already
    #             # committed to another series starting this slot.
    #             if (
    #                 home_id not in placed_in_slot
    #                 and away_id not in placed_in_slot
    #                 and team_free_from[home_id] <= slot_date
    #                 and team_free_from[away_id] <= slot_date
    #             ):
    #                 for day_offset in range(games_per_series):
    #                     schedule.append(
    #                         ScheduledGame(
    #                             id=str(uuid.uuid4()),
    #                             season_id=season_id,
    #                             home_team_id=home_id,
    #                             away_team_id=away_id,
    #                             game_date=slot_date + timedelta(days=day_offset),
    #                         )
    #                     )

    #                 series_end = slot_date + timedelta(days=games_per_series)
    #                 team_free_from[home_id] = series_end
    #                 team_free_from[away_id] = series_end
    #                 placed_in_slot.add(home_id)
    #                 placed_in_slot.add(away_id)
    #             else:
    #                 still_remaining.append((home_id, away_id))

    #         if not placed_in_slot:
    #             # No series fit this slot (e.g. all free teams have no valid
    #             # matchup remaining). Advance the earliest free team to unblock.
    #             earliest_team = min(team_free_from, key=lambda t: team_free_from[t])
    #             team_free_from[earliest_team] += timedelta(days=1)

    #         remaining = still_remaining

    #     schedule.sort(key=lambda g: g.game_date)
    #     return schedule
        
def save_schedule_to_db(conn, schedule: list[ScheduledGame]) -> None:
    """Save schedule to games table."""
    game_repo = GameRepository(conn)
    game_repo.insert_schedule(schedule)

    conn.commit()
    print(f"Saved {len(schedule)} games to schedule")
