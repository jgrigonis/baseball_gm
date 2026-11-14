"""New arrivals (Josh, 2026-11-14): a player who joined a team by trade,
signing or waiver claim wears a NEW tag on its Roster and Lineup rows for
NEW_DAYS league days. team_players.joined_on holds the league date he came
(migration 131); players a team drafted or started with have none.
"""

from __future__ import annotations

from datetime import date

from src.api.services.news import moves as move_news
from src.db.repositories.season_repo import SeasonRepository

NEW_DAYS = 7


def today(conn, league_id: str) -> str:
    """The league's date for a move, as the news uses it."""
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    return move_news.today(conn, season_id)


def mark(conn, league_id: str, team_id: str, player_id: str) -> None:
    """Note the day a player joined a team."""
    conn.execute(
        "UPDATE team_players SET joined_on = %s WHERE team_id = %s AND player_id = %s",
        (today(conn, league_id), team_id, player_id),
    )


def attach(conn, league_id: str, team_id: str | None, players: list[dict]) -> None:
    """p["arrived"] = "Joined Jun 3" on cards of players who joined within
    NEW_DAYS league days."""
    if not team_id or not players:
        return
    rows = conn.execute(
        """SELECT player_id, joined_on FROM team_players
           WHERE team_id = %s AND joined_on IS NOT NULL""",
        (team_id,),
    ).fetchall()
    if not rows:
        return
    now = date.fromisoformat(today(conn, league_id)[:10])
    fresh = {}
    for r in rows:
        try:
            joined = date.fromisoformat(str(r["joined_on"])[:10])
        except ValueError:
            continue
        if 0 <= (now - joined).days < NEW_DAYS:
            fresh[r["player_id"]] = f"Joined {joined.strftime('%b')} {joined.day}"
    for p in players:
        when = fresh.get(p.get("player_id"))
        if when:
            p["arrived"] = when
