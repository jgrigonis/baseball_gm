# src/api/services/front_office.py
#
# Each AI team's outlook: its team state and its GM's persona, and the youth
# tilt they add up to (src/league/front_office.py). The draft, roster
# replans, offseason trimming and the sim's lineups read it. People's teams
# have none: they run their own roster.

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from src.api.services import personas, team_states
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.league import front_office
from src.league.personas import Leanings
from src.league.rotation_seeder import seed_ai_rotations
from src.team.roster_assigner import RosterAssigner


@dataclass(frozen=True)
class Outlook:
    state: str | None
    lean: Leanings
    tilt: float  # -1 veterans … 1 kids

    def age_bonus(self, players) -> dict[str, float]:
        """Rating points each of these players (anything with id and age)
        gets for his age."""
        out = {}
        for p in players:
            points = front_office.age_points(p.age, self.tilt)
            if points:
                out[p.id] = points
        return out


def outlooks(
    conn, league_id: str, season_id: str | None = None, today: str | None = None
) -> dict[str, Outlook]:
    """Every AI team's outlook, by team id."""
    season_id = season_id or SeasonRepository(conn).get_current_id_for_league(league_id)
    if not season_id:
        return {}
    humans = GMRepository(conn).get_human_team_ids(league_id)
    teams = [
        t["id"]
        for t in TeamRepository(conn).get_teams_in_league_season(league_id, season_id)
        if t["id"] not in humans
    ]
    if not teams:
        return {}
    states = team_states.states(
        conn, league_id, season_id, today or date.today().isoformat()
    )
    leanings = personas.leanings(conn, league_id)
    out = {}
    for t in teams:
        lean = leanings.get(t, Leanings())
        state = states.get(t)
        out[t] = Outlook(state, lean, front_office.youth_tilt(state, lean))
    return out


def replan_roster(
    conn,
    league_id: str,
    season_id: str,
    team_id: str,
    outlook: Outlook | None,
    effective_date: str,
) -> None:
    """An AI team re-picks its 26-man and 40-man, leaning young or veteran as
    its outlook says, then its rotation and bullpen."""
    players = PlayerRepository(conn).get_players_by_team(team_id)
    if not players:
        return
    bonus = outlook.age_bonus(players) if outlook else None
    PlayerStatusRepository(conn).bulk_set(RosterAssigner().assign(players, bonus))
    seed_ai_rotations(
        conn,
        season_id,
        {team_id},
        statuses=["26man", "40man"],
        effective_date=effective_date,
        league_id=league_id,
    )


def call_ups(conn, league_id: str, changed: dict[str, str], game_date: str) -> int:
    """AI teams whose state just changed re-pick their rosters: a team that
    starts rebuilding calls up its prospects, one that goes all-in its
    veterans. Returns how many teams did."""
    if not changed:
        return 0
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    if not season_id:
        return 0
    ai = outlooks(conn, league_id, season_id, game_date)
    effective = (date.fromisoformat(game_date) + timedelta(days=1)).isoformat()
    n = 0
    for team_id in changed:
        if team_id in ai:
            replan_roster(conn, league_id, season_id, team_id, ai[team_id], effective)
            n += 1
    return n
