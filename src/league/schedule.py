# src/league/schedule.py
from dataclasses import dataclass
from datetime import date, timedelta
import itertools
import random
import uuid


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
        """Generate round-robin matchups."""
        matchups = []

        for home, away in itertools.combinations(team_ids, 2):
            for _ in range(games_per_matchup):
                matchups.append((home, away))
                if home_and_away:
                    matchups.append((away, home))

        self.rng.shuffle(matchups)
        return matchups


    def create_schedule(
        self,
        season_id: str,
        team_ids: list[str],
        start_date: date,
        games_per_matchup: int = 3,
        home_and_away: bool = True,
    ) -> list[ScheduledGame]:
        """Create a full season schedule."""
        matchups = self.generate_round_robin(team_ids, games_per_matchup, home_and_away)

        schedule = []
        current_date = start_date
        remaining = list(matchups)

        while remaining:
            # Build today's slate: each team plays at most once
            todays_games = []
            used_teams = set()
            leftover = []

            for home_id, away_id in remaining:
                if home_id not in used_teams and away_id not in used_teams:
                    todays_games.append((home_id, away_id))
                    used_teams.add(home_id)
                    used_teams.add(away_id)
                else:
                    leftover.append((home_id, away_id))

            for home_id, away_id in todays_games:
                schedule.append(
                    ScheduledGame(
                        id=str(uuid.uuid4()),
                        season_id=season_id,
                        home_team_id=home_id,
                        away_team_id=away_id,
                        game_date=current_date,
                        series_id=None,
                    )
                )

            remaining = leftover
            current_date += timedelta(days=1)

        return schedule


def save_schedule_to_db(conn, schedule: list[ScheduledGame]) -> None:
    """Save schedule to games table."""
    cursor = conn.cursor()

    for game in schedule:
        cursor.execute(
            """
            INSERT INTO games (id, date, season_id, home_team_id, away_team_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                game.id,
                game.game_date.isoformat(),
                game.season_id,
                game.home_team_id,
                game.away_team_id,
            ),
        )

    conn.commit()
    print(f"Saved {len(schedule)} games to schedule")
