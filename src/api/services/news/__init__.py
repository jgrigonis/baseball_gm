# src/api/services/news/__init__.py
#
# The league news feed (plans/news-feed.md): short stories about what's
# happening around the league, written so a GM's moves feel like they matter.
# A trade names the GMs who made it; when the season ends, a follow-up story
# says whether it paid off. A milestone or an All-Star nod says who drafted
# or traded for the player.
#
# update_league() runs after every sim job (sim_jobs.run) and catches up from
# where the last run stopped: each season's news_through is the last league
# date it covered, so one day or a whole season simmed at once come out the
# same. Every story has a key, so running again never writes it twice. A
# season is closed once it's over and the next one has started (or the
# league is complete), and isn't looked at again.
#
# A league that was already running when the feed arrived starts from where
# it is: its finished seasons are closed without stories, and the current
# season's days so far are skipped.
#
# record_trades() runs as a trade goes through, so it's in the feed at once.

from __future__ import annotations

import logging

from src.api.services.news import events, games
from src.api.services.news.names import Names
from src.db.repositories.news_repo import NewsRepository

log = logging.getLogger(__name__)


def update_league(conn, league_id: str) -> None:
    league = conn.execute(
        "SELECT state FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if not league or league["state"] == "lobby":
        return
    repo = NewsRepository(conn)
    seasons = _seasons(conn, league_id)
    if not seasons:
        return
    if not repo.started(league_id):
        _start(conn, repo, league_id, seasons)
    progress = repo.progress(league_id)
    open_ids = [s["id"] for s in seasons if not progress[s["id"]]["news_closed"]]
    names = Names(conn, league_id)
    events.trades(conn, names, league_id, open_ids)
    events.drafts(conn, names, league_id, open_ids)
    for i, season in enumerate(seasons):
        sid = season["id"]
        if progress[sid]["news_closed"]:
            continue
        dates = _dates(conn, sid)
        since = progress[sid]["news_through"]
        if dates["last"] and (since is None or dates["last"] > since):
            games.write(conn, names, league_id, sid, since, dates["last"])
            repo.set_through(league_id, sid, dates["last"])
        events.all_stars(conn, names, league_id, sid)
        if dates["regular_over"]:
            events.season_end(conn, names, league_id, sid, dates["last_regular"])
        events.playoffs(conn, names, league_id, sid, season["year"])
        events.season_awards(conn, names, league_id, sid, season["year"])
        events.hall_of_fame(conn, names, league_id, sid, season["year"])
        later = i < len(seasons) - 1
        if later or league["state"] == "complete":
            # Over: the offseason that fired GMs and retired players has run.
            on = dates["last"] or f"{season['year']}-10-31"
            events.firings(conn, names, league_id, sid, on)
            events.retirements(conn, names, league_id, sid, on)
            repo.close(league_id, sid)


def record_trades(conn, league_id: str) -> None:
    """Write the story for any trade just made. In a savepoint, so a problem
    here is logged and never undoes the trade."""
    try:
        with conn.transaction():
            repo = NewsRepository(conn)
            seasons = _seasons(conn, league_id)
            if not seasons:
                return
            progress = repo.progress(league_id)
            open_ids = [
                s["id"] for s in seasons if not progress[s["id"]]["news_closed"]
            ]
            events.trades(conn, Names(conn, league_id), league_id, open_ids)
    except Exception:
        log.exception("League %s: couldn't write trade news", league_id)


def _seasons(conn, league_id: str) -> list[dict]:
    """The league's real seasons (not backstory), oldest first."""
    rows = conn.execute(
        """SELECT s.id, s.year FROM seasons s
           JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s AND NOT s.is_backstory
           ORDER BY s.year""",
        (league_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _dates(conn, season_id: str) -> dict:
    row = conn.execute(
        """SELECT MAX(game_date) FILTER (WHERE completed = 1) AS last,
                  MAX(game_date) FILTER (WHERE completed = 1 AND series_id IS NULL)
                      AS last_regular,
                  COUNT(*) FILTER (WHERE series_id IS NULL) AS regular,
                  COUNT(*) FILTER (WHERE series_id IS NULL
                                   AND (completed = 0 OR completed IS NULL)) AS left_to_play
           FROM games WHERE season_id = %s""",
        (season_id,),
    ).fetchone()
    return {
        "last": row["last"],
        "last_regular": row["last_regular"],
        "regular_over": row["regular"] > 0 and row["left_to_play"] == 0,
    }


def _start(conn, repo: NewsRepository, league_id: str, seasons: list[dict]) -> None:
    """The first run for a league: close the seasons already over and start
    the current one from its last day played, so a league that was running
    before the feed doesn't get a flood of old stories."""
    *past, current = seasons
    for s in past:
        repo.close(league_id, s["id"])
    repo.set_through(
        league_id, current["id"], _dates(conn, current["id"])["last"] or ""
    )
