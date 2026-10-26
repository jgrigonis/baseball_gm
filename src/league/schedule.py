# src/league/schedule.py
import logging
from dataclasses import dataclass
from datetime import date, timedelta
import itertools
import random
import uuid

from src.db.repositories.games_repo import GameRepository

log = logging.getLogger(__name__)


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
                matchups.append((a, b))

        if home_and_away:
            return_rounds = self._circle_rounds(team_ids)
            self.rng.shuffle(return_rounds)
            for round_pairs in return_rounds:
                pairs = list(round_pairs)
                self.rng.shuffle(pairs)
                for a, b in pairs:
                    if "__bye__" in (a, b):
                        continue
                    matchups.append((b, a))

        return matchups

    def create_schedule(
        self,
        season_id: str,
        team_ids: list[str],
        start_date: date,
        games_per_series: int = 3,
        home_and_away: bool = True,
        target_games: int | None = None,
        all_star_break_after: int | None = None,
        all_star_break_days: int = 0,
    ) -> list[ScheduledGame]:
        """
        Create a full season schedule built around series with no gaps.

        The circle algorithm guarantees every team plays in every round, so
        series can be laid out round by round with no team ever sitting idle
        while others are playing.

        With ``target_games`` set, the season is built from whole round-robin
        cycles instead, and each round's series length (2, 3 or 4 games) is
        chosen so every team plays exactly ``target_games``. See
        ``_season_rounds``. ``all_star_break_after`` and
        ``all_star_break_days`` then leave that many off days after the round
        that ends nearest that game number.
        """
        if target_games is None:
            matchups = self.generate_series_matchups(team_ids, home_and_away)
            games_per_round = len(team_ids) // 2
            rounds = [
                (matchups[i : i + games_per_round], games_per_series)
                for i in range(0, len(matchups), games_per_round)
            ]
        else:
            rounds = self._season_rounds(team_ids, target_games)

        break_round = None
        if all_star_break_after is not None and all_star_break_days > 0:
            break_round = self._break_round(
                [length for _, length in rounds], all_star_break_after
            )

        schedule: list[ScheduledGame] = []
        series_start = start_date
        for round_index, (pairs, length) in enumerate(rounds):
            for home_id, away_id in pairs:
                for day_offset in range(length):
                    schedule.append(
                        ScheduledGame(
                            id=str(uuid.uuid4()),
                            season_id=season_id,
                            home_team_id=home_id,
                            away_team_id=away_id,
                            game_date=series_start + timedelta(days=day_offset),
                        )
                    )
            series_start += timedelta(days=length)
            if round_index == break_round:
                series_start += timedelta(days=all_star_break_days)

        schedule.sort(key=lambda g: g.game_date)
        return schedule

    @staticmethod
    def season_shape(num_teams: int, target_games: int) -> tuple[int, int, int]:
        """
        Pick how many round-robin cycles to play and how many rounds need a
        series length other than 3, so every team plays exactly
        ``target_games``.

        A cycle is num_teams - 1 rounds, and every team plays one series per
        round. Series are 3 games, except that some rounds are 2 or 4 games to
        land on the target. The cycle count that needs the fewest of those
        rounds wins, with ties going to fewer cycles.

        Returns (cycles, number of off-length rounds, their series length).
        """
        if num_teams < 2 or num_teams % 2:
            raise ValueError(f"Need an even number of teams, got {num_teams}")

        best = None
        for cycles in range(1, target_games + 1):
            num_rounds = cycles * (num_teams - 1)
            if 4 * num_rounds < target_games:
                continue
            if 2 * num_rounds > target_games:
                break
            off_rounds = abs(target_games - 3 * num_rounds)
            if best is None or off_rounds < best[1]:
                off_length = 4 if target_games > 3 * num_rounds else 2
                best = (cycles, off_rounds, off_length)
        if best is None:
            raise ValueError(
                f"Can't schedule {target_games} games for {num_teams} teams"
            )
        return best

    def _season_rounds(
        self, team_ids: list[str], target_games: int
    ) -> list[tuple[list[tuple[str, str]], int]]:
        """
        Build the season as (pairs, series length) rounds over whole cycles.

        Cycles come in home/away pairs: the second of each pair replays the
        first's rounds with every matchup flipped and the same series length,
        so each pair of teams splits those games evenly. A leftover odd cycle
        gives the home series in each matchup to whichever team has had fewer
        home games so far. Off-length rounds go to the paired cycles first,
        two at a time, and are spaced evenly through each cycle.
        """
        num_teams = len(team_ids)
        cycles, off_rounds, off_length = self.season_shape(num_teams, target_games)
        rounds_per_cycle = num_teams - 1
        cycle_pairs = cycles // 2

        # How many off-length rounds each cycle gets.
        paired_off = min(off_rounds // 2, cycle_pairs * rounds_per_cycle)
        off_per_cycle = []
        for i in range(cycle_pairs):
            share = paired_off // cycle_pairs + (i < paired_off % cycle_pairs)
            off_per_cycle += [share, share]
        if cycles % 2:
            off_per_cycle.append(off_rounds - 2 * paired_off)

        season: list[tuple[list[tuple[str, str]], int]] = []
        home_games = {t: 0 for t in team_ids}
        for cycle in range(cycles):
            if cycle % 2 == 0:
                shuffled = list(team_ids)
                self.rng.shuffle(shuffled)
                matchings = self._circle_rounds(shuffled)
                self.rng.shuffle(matchings)
                # The first off_per_cycle matchings are the off-length ones,
                # in both this cycle and its flipped partner.
                lengths = [
                    off_length if i < off_per_cycle[cycle] else 3
                    for i in range(rounds_per_cycle)
                ]
                cycle_rounds = list(zip(matchings, lengths))
            else:
                cycle_rounds = [
                    ([(b, a) for a, b in pairs], length)
                    for pairs, length in cycle_rounds
                ]

            balance = cycle == cycles - 1 and cycle % 2 == 0
            for pairs, length in self._spread(cycle_rounds, off_per_cycle[cycle]):
                if balance:
                    pairs = [self._balance_home(a, b, home_games) for a, b in pairs]
                pairs = list(pairs)
                self.rng.shuffle(pairs)
                for home, _ in pairs:
                    home_games[home] += length
                season.append((pairs, length))

        return season

    def _spread(
        self, cycle_rounds: list[tuple[list[tuple[str, str]], int]], off_count: int
    ) -> list[tuple[list[tuple[str, str]], int]]:
        """
        Order a cycle's rounds randomly, with its ``off_count`` off-length
        rounds (the first ones in ``cycle_rounds``) evenly spaced.
        """
        off = cycle_rounds[:off_count]
        regular = cycle_rounds[off_count:]
        self.rng.shuffle(off)
        self.rng.shuffle(regular)
        n = len(cycle_rounds)
        off_slots = {int((i + 0.5) * n / off_count) for i in range(off_count)}
        off_iter, regular_iter = iter(off), iter(regular)
        return [
            next(off_iter) if i in off_slots else next(regular_iter) for i in range(n)
        ]

    def _balance_home(
        self, a: str, b: str, home_games: dict[str, int]
    ) -> tuple[str, str]:
        """Give the home series to whichever team has fewer home games so far."""
        if home_games[a] != home_games[b]:
            return (a, b) if home_games[a] < home_games[b] else (b, a)
        return (a, b) if self.rng.random() < 0.5 else (b, a)

    @staticmethod
    def _break_round(lengths: list[int], after_games: int) -> int:
        """The index of the round that ends nearest game ``after_games``."""
        played = 0
        best_index, best_gap = 0, None
        for i, length in enumerate(lengths[:-1]):
            played += length
            gap = abs(played - after_games)
            if best_gap is None or gap < best_gap:
                best_index, best_gap = i, gap
        return best_index

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
    log.info("Saved %s games to schedule", len(schedule))
