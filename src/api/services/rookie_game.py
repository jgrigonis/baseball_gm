# src/api/services/rookie_game.py
#
# The Rookie Game in a league (src/league/rookie_game.py has the rules). The
# rookies are picked by the stats when the All-Star votes are counted
# (all_star.count_votes), and the two captains draft them just as the
# All-Star captains do. It's played on the first day of the break, with the
# Home Run Derby and the All-Star Game, when the sim reaches the first day
# after it (sim_next.sim_next_day). The draft and the game are the All-Star
# Game's, with event="rookie".

from __future__ import annotations

import random

from src.api.services import all_star
from src.db.repositories.all_star_repo import AllStarRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.standings_repo import StandingsRepository
from src.league import all_star as all_star_rules
from src.league import rookie_game

EVENT = "rookie"


def candidates(conn, league_id: str, season_id: str) -> list[dict]:
    """Everyone with a rookie's share of the playing time, scored as on the
    All-Star ballot."""
    games = PlayerSeasonStatsRepository(conn).get_max_games_played(season_id)
    players = AllStarRepository(conn).candidates(league_id, season_id)
    return all_star_rules.add_features(
        all_star_rules.on_ballot(players, games, rookie_game.PLAYING_TIME_SHARE)
    )


def select(conn, league_id: str, season_id: str) -> list[dict]:
    """Pick the season's rookies and captains and start the draft, once the
    All-Stars are in. Returns the rookies, or [] when there's no game (it's
    picked already, or there aren't enough rookies or teams)."""
    repo = AllStarRepository(conn, EVENT)
    w = all_star.window(conn, season_id)
    if not w or repo.has_all_stars(season_id):
        return []
    cands = candidates(conn, league_id, season_id)
    rookie_ids = PlayerSeasonStatsRepository(conn).get_rookie_ids(league_id, season_id)
    hurt = all_star._hurt(
        conn, league_id, [c["player_id"] for c in cands if c["player_id"] in rookie_ids]
    )
    stars = AllStarRepository(conn).ids(season_id)
    rows = rookie_game.pool(cands, rookie_ids, stars | hurt)
    if not rows:
        return []
    standings = [r["team_id"] for r in StandingsRepository(conn).ranked(season_id)]
    asg = AllStarRepository(conn).game(season_id)
    taken = [asg["captain1_team_id"], asg["captain2_team_id"]] if asg else []
    captains = rookie_game.captains(rows, standings, taken)
    if not captains:
        return []
    repo.save_all_stars(season_id, rows)
    repo.create_game(season_id, *captains, rookie_game.game_date(w), [])
    all_star.draft(conn, league_id, season_id, event=EVENT)
    return rows


def play(conn, league_id: str, season_id: str, rng: random.Random | None = None):
    """Play the season's Rookie Game. Returns the result, or None if there's
    no game or it's played already."""
    g = AllStarRepository(conn, EVENT).game(season_id)
    if not g or g["state"] == "played":
        return None
    return all_star.play_game(conn, league_id, season_id, rng, event=EVENT)


def tab_context(conn, league_id: str, season_id: str, team_id) -> dict:
    """The Rookie Game on the All-Star tab, as `rookie`, the way the
    All-Star Game is `asg` (all_star.game_context)."""
    repo = AllStarRepository(conn, EVENT)
    g = repo.game(season_id)
    if not g:
        return {}
    stars = all_star.stars_with_injuries(conn, league_id, season_id, EVENT)
    ctx = all_star.game_context(conn, league_id, season_id, team_id, g, stars, EVENT)
    ctx["rookie_count"] = len(stars)
    ctx["my_rookies"] = sum(1 for r in stars if r["team_id"] == team_id)
    return {"rookie": ctx}


def career(conn, player_id: str) -> list[dict]:
    """A player's Rookie Game lines, for his career page."""
    return AllStarRepository(conn, EVENT).career_lines(player_id)
