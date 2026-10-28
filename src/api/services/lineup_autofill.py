# src/api/services/lineup_autofill.py
#
# The Lineup tab's Auto-fill and Rebuild buttons. Both run the same lineup
# optimizer the AI uses (src/team/lineup_optimizer.py), with the GM's lineup
# style from the Strategy tab:
#   - Auto-fill keeps every healthy, eligible player already in the lineup in
#     his slot and position, and fills the rest.
#   - Rebuild starts over from the whole eligible roster.
# Eligible is who can play in a game: the 26-man, plus the 40-man in Blitz
# leagues, minus the injured and pitchers.

from __future__ import annotations

from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.lineup_preference_repo import LineupPreferenceRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.league.league_modes import is_blitz_style
from src.player.player_in_game import PlayerInGame
from src.team.lineup_optimizer import DEFAULT_STYLE, LineupOptimizer


def eligible_hitters(db, league_id: str, team_id: str) -> list[PlayerInGame]:
    blitz = is_blitz_style(LeagueRepository(db).get_league_mode(league_id))
    statuses = ["26man", "40man"] if blitz else ["26man"]
    status_repo = PlayerStatusRepository(db)
    eligible = {
        pid for s in statuses for pid in status_repo.get_by_team_and_status(team_id, s)
    }
    injured = InjuryRepository(db, league_id).get_team_injuries(team_id)
    hitters = []
    for record in PlayerRepository(db).get_players_by_team(team_id):
        if record.id in eligible and record.id not in injured:
            if not record.is_pitcher():
                player = PlayerInGame(record)
                player.rate_player()
                hitters.append(player)
    return hitters


def autofill(
    db, league_id: str, team_id: str, current: list[dict | None], rebuild: bool
) -> list[dict]:
    """The filled lineup as [{player_id, position}], one per batting slot.
    current is the lineup on screen, one entry (or None) per slot. Raises
    ValueError if there aren't enough healthy hitters."""
    hitters = eligible_hitters(db, league_id, team_id)
    by_id = {p.id: p for p in hitters}

    locked = [None] * 9
    if not rebuild:
        for i, slot in enumerate(current[:9]):
            player = by_id.get(slot["player_id"]) if slot else None
            if player:
                locked[i] = (player, slot.get("position"))

    style = (
        LineupPreferenceRepository(db).get_lineup_style(team_id, league_id)
        or DEFAULT_STYLE
    )
    lineup = LineupOptimizer.fill(locked, hitters, style=style, dh=True)
    return [{"player_id": s.player.id, "position": s.position} for s in lineup]
