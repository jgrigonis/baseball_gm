# src/api/services/lineup_autofill.py
#
# The Lineup tab's Auto-fill and Rebuild buttons. Both run the same lineup
# optimizer the AI uses (src/team/lineup_optimizer.py), with the GM's lineup
# style from the Strategy tab:
#   - Auto-fill keeps every healthy, eligible player already in the lineup in
#     his slot and position, and fills the rest.
#   - Rebuild starts over from the whole eligible roster.
# Both use the platoon setting against the hand the lineup is for (the Lineup
# tab's vs RHP / vs LHP toggle), and weigh each hitter's season stats against
# his ratings by the Strategy tab's stats-vs-scouting setting. A hitter
# still rusty from an injury is rated with the rust taken off his skills.
# Eligible is who can play in a game: the 26-man, plus the 40-man in Blitz
# leagues, minus the injured and pitchers. With the Strategy tab's Rest rusty
# players on, hitters still rusty from an injury are left out too, unless
# that would leave fewer than nine.
# Rebuild with the Strategy tab's own style keeps the lineup on screen
# steady: a player only moves or loses his spot for a clearly better one
# (LineupOptimizer KEEP_BONUS), so a rebuild a day later doesn't reshuffle
# near ties. Rebuild All with a style picked from its menu starts clean.

from __future__ import annotations

from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.league import performance
from src.league.league_modes import is_blitz_style
from src.player.player_in_game import PlayerInGame
from src.team.lineup_optimizer import LineupOptimizer
from src.team.manager_profile import ManagerProfile


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
    db,
    league_id: str,
    team_id: str,
    current: list[dict | None],
    rebuild: bool,
    vs_hand: str = "R",
    style: str | None = None,
) -> list[dict]:
    """The filled lineup as [{player_id, position}], one per batting slot.
    current is the lineup on screen, one entry (or None) per slot. style
    overrides the Strategy tab's lineup style (the Rebuild All menu). Raises
    ValueError if there aren't enough healthy hitters."""
    hitters = eligible_hitters(db, league_id, team_id)
    profile = ManagerProfile.from_row(
        GMRepository(db).get_team_profile(team_id, league_id)
    )
    # Rusty hitters are rated with their rust taken off, the way the sim
    # plays them today, or left out with Rest rusty players on.
    rusty = InjuryRepository(db, league_id).get_rust([p.id for p in hitters])
    for p in hitters:
        if p.id in rusty:
            p.apply_rust(rusty[p.id]["skills"])
    if profile.rest_rusty:
        fresh = [p for p in hitters if p.id not in rusty]
        if len(fresh) >= 9:
            hitters = fresh
    by_id = {p.id: p for p in hitters}

    locked = [None] * 9
    keep = None
    if not rebuild:
        for i, slot in enumerate(current[:9]):
            player = by_id.get(slot["player_id"]) if slot else None
            if player:
                locked[i] = (player, slot.get("position"))
    elif not style or style == profile.lineup_style:
        keep = current_keep(current, by_id)

    lineup = LineupOptimizer.fill(
        locked,
        hitters,
        style=style or profile.lineup_style,
        dh=True,
        vs_hand=vs_hand,
        platoon=profile.platoon_usage,
        form=_form(db, league_id, hitters, profile.stats_weight),
        keep=keep,
    )
    return [{"player_id": s.player.id, "position": s.position} for s in lineup]


def current_keep(current: list[dict | None], available) -> dict[str, tuple[int, str]]:
    """{player_id: (batting slot, position)} for the lineup being played,
    leaving out anyone who can't play (not in available)."""
    return {
        slot["player_id"]: (i, slot.get("position") or "")
        for i, slot in enumerate(current[:9])
        if slot and slot.get("player_id") in available
    }


def _form(db, league_id: str, hitters: list[PlayerInGame], weight: float) -> dict:
    """Each hitter's form this season, as a GM with this stats weight sees
    it, in offense points."""
    season_id = SeasonRepository(db).get_current_id_for_league(league_id)
    if not weight or not season_id:
        return {}
    totals = PlayerSeasonStatsRepository(db).get_form_totals(
        season_id, [p.id for p in hitters]
    )
    out = {}
    for p in hitters:
        t = totals.get(p.id)
        hit = performance.hitter_form(p.ratings["overall_offense"], t) if t else 0.0
        if hit:
            out[p.id] = weight * hit
    return out
