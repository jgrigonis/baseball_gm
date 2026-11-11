# src/api/services/takeover.py
#
# Joining a league after it has started, by taking over a team an AI GM runs.
#
# It's only open between seasons: from the end of the playoffs (offseason)
# through the draft and preseason, never while the regular season or the
# playoffs are on. Mid-season the person would inherit half a season of
# someone else's moves, and the sim, the ready check and the career record
# would all have to agree on the day the team changed hands.
#
# The commissioner can close it with the league's Late joiners setting
# (leagues.late_joins). A private league is still only open to people with
# its join code; a public one to anyone.
#
# Taking over is leave_league in reverse: the AI GM's row becomes the
# person's (gm_repo.take_over_team), so the team keeps its draft picks,
# standings and history. Its open trade offers are called off, since the
# AI made them. The person's career record starts with the first season they
# run the team (gms.joined_year, see career.py).
#
# A person their owner fired (src/api/services/firing.py) in a league with
# re-entry on comes back the same way, whatever the Late joiners setting:
# one of the AI teams whose owners offer them the job (job_offers.py), never
# the one that fired them, between seasons. Their fired row gives way to the
# team's.

from __future__ import annotations

from src.api.services import firing, job_offers, sim_jobs, trades
from src.db.locks import league_lock
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.news_repo import NewsRepository
from src.db.repositories.team_game_repo import TeamGameRepository

# League states between one season's playoffs and the next season's games.
BETWEEN_SEASONS = ("offseason", "draft", "preseason")


class TakeoverClosed(Exception):
    """The league can't take a new GM right now; the message says why."""


def closed_reason(conn, league: dict, user_id: str | None = None) -> str | None:
    """Why a person can't take over a team in this started league now, or
    None if they can. With user_id, a person the league's owners fired
    gets the re-entry rules instead of the late joiners ones."""
    name = league["name"]
    fired = bool(user_id) and is_fired(conn, league["id"], user_id)
    if league.get("is_practice"):
        return f"{name} is a tutorial league, so it can't take new GMs."
    if league.get("single_player") and not fired:
        return f"{name} has a custom team, so it's single player."
    if league["state"] == "complete":
        return f"{name} is over."
    if fired and not league.get("reentry_enabled"):
        return f"{name} is one and done: a fired GM watches from then on."
    if not fired and not league.get("late_joins"):
        return f"{name} isn't taking new GMs once it has started."
    if league["state"] not in BETWEEN_SEASONS:
        return (
            f"{name} is in the middle of a season. New GMs can take over a team"
            " between seasons, from the end of the playoffs until Opening Day."
        )
    if not open_teams(conn, league["id"], user_id):
        return f"Every team in {name} already has a person running it."
    return None


def is_fired(conn, league_id: str, user_id: str) -> bool:
    """Whether this person's row in the league is a fired one."""
    row = conn.execute(
        "SELECT fired_at FROM gms WHERE league_id = %s AND user_id = %s",
        (league_id, user_id),
    ).fetchone()
    return bool(row and row["fired_at"])


def open_teams(conn, league_id: str, user_id: str | None = None) -> list[dict]:
    """The teams an AI GM runs, with the GM and the team's last finished
    season, for the page where a person picks one. With user_id, not the
    teams that fired them; and for a fired person, only the teams whose
    owners offer them the job (job_offers.py), with each owner's message.
    Owners only make offers between seasons."""
    last = conn.execute(
        """SELECT s.id FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s
             AND EXISTS (SELECT 1 FROM team_game_stats tgs
                         JOIN games gm ON gm.id = tgs.game_id
                         WHERE gm.season_id = s.id)
           ORDER BY s.year DESC LIMIT 1""",
        (league_id,),
    ).fetchone()
    rows = conn.execute(
        """SELECT g.id AS gm_id, g.display_name, g.persona_id, p.archetype,
                  t.id AS team_id, t.city, t.mascot
           FROM gms g
           JOIN teams t ON t.id = g.team_id
           LEFT JOIN gm_personas p ON p.id = g.persona_id
           WHERE g.league_id = %s AND g.is_ai AND g.fired_at IS NULL
           ORDER BY t.city, t.mascot""",
        (league_id,),
    ).fetchall()
    teams = [dict(r) for r in rows]
    if user_id:
        gone = set(firing.fired_from(conn, league_id, user_id))
        teams = [t for t in teams if t["team_id"] not in gone]
    if last and teams:
        repo = TeamGameRepository(conn)
        for t in teams:
            t["last_wl"] = repo.get_team_wl(t["team_id"], last["id"])
    if user_id and is_fired(conn, league_id, user_id):
        league = conn.execute(
            "SELECT id, state FROM leagues WHERE id = %s", (league_id,)
        ).fetchone()
        if league["state"] not in BETWEEN_SEASONS:
            return []
        year = joined_year(conn, league)
        teams = job_offers.offers(conn, league_id, user_id, year, teams)
    return teams


def joined_year(conn, league: dict) -> int:
    """The first season a person taking over now would run their team: the
    one about to start. In the offseason that's the year after the newest
    season; from the draft on, the new season already exists."""
    row = conn.execute(
        """SELECT MAX(s.year) AS year FROM seasons s
           JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s""",
        (league["id"],),
    ).fetchone()
    year = row["year"] or 0
    return year + 1 if league["state"] == "offseason" else year


def take_over(conn, league_id: str, user: dict, team_id: str) -> str:
    """Hand the AI GM's team to the user. Returns their GM id. Raises
    TakeoverClosed if the league can't take them, or LeagueBusy while
    it's simming."""
    gm_repo = GMRepository(conn)
    with league_lock(conn, league_id):
        league = LeagueRepository(conn).get_by_id(league_id)
        if not league or league["state"] == "lobby":
            raise TakeoverClosed("That league isn't running.")
        mine = gm_repo.get_by_user_and_league(user["id"], league_id)
        if mine and not mine["fired_at"]:
            raise TakeoverClosed(f"You're already in {league['name']}.")
        # A sim job holds the lock only while it runs; one waiting in the
        # queue may be about to start the season.
        if sim_jobs.league_has_job(conn, league_id):
            raise TakeoverClosed(
                f"{league['name']} is moving on right now. Try again in a minute."
            )
        reason = closed_reason(conn, league, user["id"])
        if reason:
            raise TakeoverClosed(reason)
        ai = next(
            (
                t
                for t in open_teams(conn, league_id, user["id"])
                if t["team_id"] == team_id
            ),
            None,
        )
        if not ai:
            raise TakeoverClosed("Someone else already runs that team.")

        trades.team_leaving(
            conn, league_id, team_id, ai["gm_id"], reason="the team has a new GM."
        )
        if mine:
            # Back from a firing: their fired row gives way to the team's,
            # and a commissioner role kept for them comes along.
            gm_repo.delete_gm(mine["id"])
            if league["commissioner_gm_id"] == mine["id"]:
                gm_repo.set_commissioner(ai["gm_id"], league_id)
            firing.rehired(conn, league_id, user["id"], team_id)
        first_year = joined_year(conn, league)
        gm_repo.take_over_team(
            ai["gm_id"], user["id"], user["display_name"], first_year
        )
        # The new GM's front office starts at Standard, not at the levels the
        # GMs before them picked (Josh, 2026-11-11).
        BudgetRepository(conn).reset_levels(league_id, team_id, first_year)
        # The owner's messages were to the AI GMs who ran the team before, so
        # the new GM starts with an empty office, not a pile of unread mail.
        conn.execute("DELETE FROM owner_messages WHERE gm_id = %s", (ai["gm_id"],))
        # The News tab's badge counts from now, not from the league's start.
        news = NewsRepository(conn)
        news.mark_seen(ai["gm_id"], news.newest_id(league_id))
        conn.commit()
    return ai["gm_id"]
