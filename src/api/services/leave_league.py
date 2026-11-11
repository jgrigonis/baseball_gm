# src/api/services/leave_league.py
#
# A GM leaving a league. In the lobby they just drop off the list, since AI
# GMs only fill the empty teams when the league starts. Once the league has
# started, their team carries on under AI control: the GM row becomes an AI
# GM, so the team keeps its draft picks, results and standings, and the
# ready-check and injury news stop counting it. Their open trade offers are
# called off, and they drop out of the league's trade votes.
#
# A GM their owner fired (firing.py) has a row with no team, so there is
# nothing for AI to take over: the row goes, with their job offers, and the
# league drops off their list. That doesn't touch anything a sim reads, so it
# doesn't wait on the league's lock unless it deletes the league.
#
# A leaving commissioner hands the role to the human GM who has been in the
# league longest. When the last person leaves, the league is deleted with
# everything it owns, since nobody could ever open it again.

from __future__ import annotations

import random

from src.api.services import badges, career, personas, trades
from src.db.locks import league_lock
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.league_repo import LeagueRepository


# How long leaving waits for a sim day (or playoff game) to finish.
LEAVE_WAIT = 20


def leave_league(conn, league_id: str, gm_id: str) -> None:
    league_repo = LeagueRepository(conn)
    gm_repo = GMRepository(conn)

    gm = gm_repo.get_by_id(gm_id)
    if gm and gm["fired_at"]:
        _leave_fired(conn, league_id, gm)
        return

    # Not in the middle of a sim: it has already decided whose team is human,
    # e.g. for the injury news it stores afterwards.
    with league_lock(conn, league_id, wait=LEAVE_WAIT):
        league = league_repo.get_by_id(league_id)
        if not league:
            raise ValueError("League not found.")

        if league["commissioner_gm_id"] == gm_id:
            gm_repo.set_commissioner(
                gm_repo.next_commissioner(league_id, gm_id), league_id
            )

        if league["state"] == "lobby":
            gm_repo.delete_gm(gm_id)
        else:
            # Their record so far, before the team stops being theirs (and
            # before the league is deleted, if they're the last one out).
            career.record_league(conn, league_id, leaving_gm_id=gm_id)
            gm = gm_repo.get_by_id(gm_id)
            if gm and gm["user_id"]:
                badges.award(conn, gm["user_id"])
            if gm and gm["team_id"]:
                trades.team_leaving(conn, league_id, gm["team_id"], gm_id)
            gm_repo.hand_team_to_ai(gm_id)
            personas.give_persona(conn, league_id, gm_id, random.Random())

        if not gm_repo.has_people(league_id):
            league_repo.delete(league_id)
        elif league["state"] == "lobby":
            personas.fill_lobby(conn, league_id)  # an AI GM takes their place
        conn.commit()


def _leave_fired(conn, league_id: str, gm: dict) -> None:
    """A fired GM leaving: their teamless row goes, and the league with it if
    nobody else is left."""
    league_repo = LeagueRepository(conn)
    gm_repo = GMRepository(conn)
    league = league_repo.get_by_id(league_id)
    if not league:
        raise ValueError("League not found.")
    if not gm_repo.has_people(league_id, besides_gm_id=gm["id"]):
        # The last person out: the league goes, so wait out any sim first.
        with league_lock(conn, league_id, wait=LEAVE_WAIT):
            league_repo.delete(league_id)
            conn.commit()
        return
    if league["commissioner_gm_id"] == gm["id"]:
        gm_repo.set_commissioner(
            gm_repo.next_commissioner(league_id, gm["id"]), league_id
        )
    conn.execute(
        "DELETE FROM gm_job_offers WHERE league_id = %s AND user_id = %s",
        (league_id, gm["user_id"]),
    )
    gm_repo.delete_gm(gm["id"])
    conn.commit()
