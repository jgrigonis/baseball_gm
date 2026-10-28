# src/api/services/leave_league.py
#
# A GM leaving a league. In the lobby they just drop off the list, since AI
# GMs only fill the empty teams when the league starts. Once the league has
# started, their team carries on under AI control: the GM row becomes an AI
# GM, so the team keeps its draft picks, results and standings, and the
# ready-check and injury news stop counting it. Their open trade offers are
# called off, and they drop out of the league's trade votes.
#
# A leaving commissioner hands the role to the human GM who has been in the
# league longest. When the last person leaves, the league is deleted with
# everything it owns, since nobody could ever open it again.

from __future__ import annotations

import shutil
from pathlib import Path

from src.api.services import trades
from src.db.locks import league_lock
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.league_repo import LeagueRepository
from src.util.locations import TEAM_FILES_DIR


def leave_league(conn, league_id: str, gm_id: str) -> None:
    league_repo = LeagueRepository(conn)
    gm_repo = GMRepository(conn)

    # Not in the middle of a sim: it has already decided whose team is human,
    # e.g. for the injury news it stores afterwards.
    with league_lock(conn, league_id):
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
            gm = gm_repo.get_by_id(gm_id)
            if gm and gm["team_id"]:
                trades.team_leaving(conn, league_id, gm["team_id"], gm_id)
            gm_repo.hand_team_to_ai(gm_id)

        deleted = not gm_repo.has_people(league_id)
        if deleted:
            league_repo.delete(league_id)
        conn.commit()

    if deleted:
        # The team and draft-class CSVs the league was built from.
        shutil.rmtree(Path(TEAM_FILES_DIR) / league_id, ignore_errors=True)
