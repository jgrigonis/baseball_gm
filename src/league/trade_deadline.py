# src/league/trade_deadline.py
#
# When a season's trade window is open. Trades open once the draft is done
# (preseason) and close after the games of deadline day: the last day of the
# round that ends nearest game TRADE_DEADLINE_AFTER_GAMES. Every team plays one
# series per round, so one team's schedule gives the round boundaries.
#
# The deadline is worked out from the games already scheduled, so leagues
# made before trades existed get one too.

from __future__ import annotations

from src.league.league_constants import TRADE_DEADLINE_AFTER_GAMES
from src.league.league_modes import is_blitz_style, trades_allowed

# League states trades can happen in, as long as the deadline hasn't passed.
TRADE_STATES = ("preseason", "season")


def deadline_date(conn, season_id: str | None) -> str | None:
    """The ISO date of the season's trade deadline, or None with no schedule."""
    if not season_id:
        return None
    team = conn.execute(
        """SELECT home_team_id AS team_id FROM games
           WHERE season_id = %s AND series_id IS NULL
           ORDER BY game_date, id LIMIT 1""",
        (season_id,),
    ).fetchone()
    if not team:
        return None
    rows = conn.execute(
        """SELECT game_date,
                  CASE WHEN home_team_id = %s THEN away_team_id
                       ELSE home_team_id END AS opponent
           FROM games
           WHERE season_id = %s AND series_id IS NULL
             AND (home_team_id = %s OR away_team_id = %s)
           ORDER BY game_date, id""",
        (team["team_id"], season_id, team["team_id"], team["team_id"]),
    ).fetchall()
    return _nearest_series_end([(r["game_date"], r["opponent"]) for r in rows])


def _nearest_series_end(games: list[tuple[str, str]]) -> str | None:
    """The last date of the series that ends nearest game
    TRADE_DEADLINE_AFTER_GAMES, from one team's (date, opponent) games in
    order. A series is a run of games against the same opponent. The last
    series doesn't count, so a short season still has games after it."""
    if not games:
        return None
    best_date, best_gap = games[-1][0], None
    for i, (game_date, opponent) in enumerate(games[:-1]):
        if games[i + 1][1] == opponent:
            continue
        gap = abs(i + 1 - TRADE_DEADLINE_AFTER_GAMES)
        if best_gap is None or gap < best_gap:
            best_date, best_gap = game_date, gap
    return best_date


def last_played_date(conn, season_id: str) -> str | None:
    row = conn.execute(
        """SELECT MAX(game_date) AS d FROM games
           WHERE season_id = %s AND series_id IS NULL AND completed = 1""",
        (season_id,),
    ).fetchone()
    return row["d"] if row else None


def trades_enabled_for(mode: str | None) -> bool:
    """Leagues whose mode trades yet. Long Form waits until its 26-man is
    managed by hand (see plans/trades.md)."""
    return trades_allowed(mode) and is_blitz_style(mode)


def window(conn, league: dict, season_id: str | None) -> dict:
    """Whether trades are open in this league right now, the deadline, and
    whether today is deadline day (the games are done and trades close with
    the next one)."""
    enabled = trades_enabled_for(league.get("mode"))
    deadline = deadline_date(conn, season_id) if enabled else None
    last = last_played_date(conn, season_id) if deadline else None
    passed = bool(deadline and last and last > deadline)
    return {
        "enabled": enabled,
        "deadline": deadline,
        "open": enabled
        and deadline is not None
        and league.get("state") in TRADE_STATES
        and not passed,
        "deadline_day": bool(deadline and last == deadline),
    }
