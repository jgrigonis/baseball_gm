# src/stats/qualifiers.py
"""
How much a player has to play to qualify for a rate stat (AVG, ERA, FPCT and
the like), after MLB's rules:
https://www.mlb.com/glossary/standard-stats/rate-stats-qualifiers

Every threshold is per team game, so it scales with the league's schedule
and with how far into the season it is. ``team_games`` is the number of games
the busiest team has played.

  batting            3.1 plate appearances a team game
  pitching           1 inning a team game
  relief pitching    0.5 innings a team game, for reliever-only reports. A
                     reliever is a pitcher who started fewer than half his
                     games
  rookies            1.55 plate appearances, or 0.5 innings, a team game
  fielding           games at the position: 0.5 a team game for catchers,
                     0.67 for everyone else; pitchers 1 inning a team game,
                     unless one with fewer innings has a better FPCT in more
                     total chances
"""

from __future__ import annotations

from src.stats.formulas import OUTS_PER_INNING

BAT_PA_PER_GAME = 3.1
PITCH_IP_PER_GAME = 1.0
RELIEF_IP_PER_GAME = 0.5
ROOKIE_PA_PER_GAME = 1.55
ROOKIE_IP_PER_GAME = 0.5
CATCHER_G_PER_GAME = 0.5
FIELDER_G_PER_GAME = 0.67
PITCHER_FIELD_IP_PER_GAME = 1.0


def plate_appearances(row: dict) -> int:
    """At bats, walks, hit by pitches and sacrifice flies, from a season
    stats row."""
    return sum(
        int(row.get(k) or 0) for k in ("bat_ab", "bat_walks", "bat_hbp", "bat_sac_flys")
    )


def is_reliever(games: int, games_started: int) -> bool:
    """Pitched mostly in relief: started fewer than half his games."""
    return games > 0 and 2 * games_started < games


def min_pa(team_games: int, rookie: bool = False) -> int:
    per = ROOKIE_PA_PER_GAME if rookie else BAT_PA_PER_GAME
    return int(per * team_games)


def min_outs(team_games: int, reliever: bool = False, rookie: bool = False) -> int:
    """Outs pitched to qualify. ``reliever`` is for reliever-only reports;
    the ordinary leaderboards hold relievers to the full inning a game."""
    if rookie:
        per = ROOKIE_IP_PER_GAME
    elif reliever:
        per = RELIEF_IP_PER_GAME
    else:
        per = PITCH_IP_PER_GAME
    return int(per * OUTS_PER_INNING * team_games)


def min_field_games(position: str, team_games: int) -> int:
    """Games at a (non-pitcher) position to qualify for its FPCT."""
    per = CATCHER_G_PER_GAME if position.lower() == "c" else FIELDER_G_PER_GAME
    return int(per * team_games)


def min_field_outs(team_games: int) -> int:
    """Outs pitched for a pitcher to qualify for pitcher FPCT."""
    return int(PITCHER_FIELD_IP_PER_GAME * OUTS_PER_INNING * team_games)


def pitcher_fpct_pool(pitchers: list[dict], team_games: int) -> list[dict]:
    """The pitchers who qualify for pitcher FPCT. Each needs outs, chances
    and fpct. A pitcher short of the innings still qualifies when he has a
    better FPCT than the qualified leader in more total chances."""
    need = min_field_outs(team_games)
    qualified = [p for p in pitchers if p["outs"] >= need]
    if not qualified:
        return []
    lead = max(qualified, key=lambda p: (p["fpct"], p["chances"]))
    return qualified + [
        p
        for p in pitchers
        if p["outs"] < need
        and p["fpct"] > lead["fpct"]
        and p["chances"] > lead["chances"]
    ]
