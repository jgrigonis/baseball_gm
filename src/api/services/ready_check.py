# src/api/services/ready_check.py
#
# How a multiplayer league (two or more human GMs) moves forward. Nobody sims
# it on their own: each period runs when every GM who isn't away has clicked
# Ready, or, under timer pace, when the Decision Window runs out.
#
# pace_control:
#   timer      every GM ready, or the window (decision_window_sec) runs out
#   confirmed  every GM ready; no clock
#   scheduled  a fixed real-world interval (not built yet)
#
# What a period does depends on the league's state: sim_period_days of the
# regular season, one playoff day, the offseason, or the draft.
#
# There is no background worker. The check runs whenever a GM clicks Ready or
# asks for the status, and the league lock decides which request runs the
# period, so it works with any number of server processes.

from __future__ import annotations

import logging

from src.api.services.draft_execute import execute_blitz_draft
from src.api.services.offseason_service import run_offseason
from src.api.services.sim_next import sim_days
from src.api.services.sim_playoff import sim_playoff
from src.db.locks import LeagueBusy, league_busy, league_lock
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.ready_check_repo import ReadyCheckRepository

log = logging.getLogger(__name__)

# League states in which a period can run.
READY_CHECK_STATES = ("draft", "preseason", "season", "playoffs", "offseason")


def is_multiplayer(conn, league_id: str) -> bool:
    return ReadyCheckRepository(conn).human_gm_count(league_id) > 1


def _due(period: dict, gms: list[dict]) -> bool:
    present = [g for g in gms if not g["is_away"]]
    # With everyone away only the clock moves the league.
    if present and all(g["ready"] for g in present):
        return True
    return (
        period["pace_control"] == "timer"
        and period["seconds_left"] is not None
        and period["seconds_left"] <= 0
    )


def _run_period(conn, league_id: str, state: str, days: int) -> None:
    if state in ("preseason", "season"):
        sim_days(league_id, conn, days)
    elif state == "playoffs":
        sim_playoff(league_id, conn, mode="game")
    elif state == "offseason":
        run_offseason(league_id, conn)
    elif state == "draft":
        draft = DraftRepository(conn).get_current_for_league(league_id)
        if draft and draft["state"] != "complete":
            execute_blitz_draft(draft["id"], conn)


def advance_if_due(conn, league_id: str) -> bool:
    """Run the league's next period if it is due. Returns True if this call
    ran it. Opens the Decision Window for a period that has none yet (the
    first one, or after a switch to timer pace)."""
    repo = ReadyCheckRepository(conn)
    period = repo.period(league_id)
    if (
        not period
        or period["state"] not in READY_CHECK_STATES
        or period["pace_control"] == "scheduled"
        or not is_multiplayer(conn, league_id)
    ):
        return False

    if period["pace_control"] == "timer" and period["period_deadline"] is None:
        repo.open_window(league_id)
        conn.commit()
        period = repo.period(league_id)

    if not _due(period, repo.gms(league_id)):
        return False

    try:
        with league_lock(conn, league_id):
            # Another request may have run it while we looked.
            now = repo.period(league_id)
            if now["sim_period"] != period["sim_period"] or not _due(
                now, repo.gms(league_id)
            ):
                return False
            log.info(
                "League %s: running period %s (%s)",
                league_id,
                now["sim_period"],
                now["state"],
            )
            _run_period(conn, league_id, now["state"], now["sim_period_days"])
            repo.next_period(league_id)
            conn.commit()
    except LeagueBusy:
        return False
    return True


def status(conn, league_id: str, gm_id: str) -> dict:
    """What the ready-check bar shows one GM."""
    if not is_multiplayer(conn, league_id):
        return {"multiplayer": False}
    repo = ReadyCheckRepository(conn)
    period = repo.period(league_id)
    gms = repo.gms(league_id)
    me = next((g for g in gms if g["id"] == gm_id), None)
    seconds_left = period["seconds_left"]
    return {
        "multiplayer": True,
        "pace": period["pace_control"],
        "league_state": period["state"],
        "active": period["state"] in READY_CHECK_STATES,
        "period": period["sim_period"],
        "seconds_left": max(0, round(seconds_left))
        if seconds_left is not None
        else None,
        "simming": league_busy(conn, league_id),
        "you_ready": bool(me and me["ready"]),
        "you_away": bool(me and me["is_away"]),
        "gms": [
            {"name": g["display_name"], "ready": g["ready"], "away": g["is_away"]}
            for g in gms
        ],
        "waiting_on": [
            g["display_name"] for g in gms if not g["ready"] and not g["is_away"]
        ],
    }


def set_ready(conn, league_id: str, gm_id: str, ready: bool) -> None:
    if not is_multiplayer(conn, league_id):
        raise ValueError("Ready-check is only used when a league has several GMs.")
    period = ReadyCheckRepository(conn).period(league_id)
    if period["state"] not in READY_CHECK_STATES:
        raise ValueError(f"Nothing to get ready for in state '{period['state']}'.")
    ReadyCheckRepository(conn).set_ready(gm_id, ready)
    conn.commit()


def set_away(conn, gm_id: str, away: bool) -> None:
    """An away GM doesn't hold up the ready-check."""
    ReadyCheckRepository(conn).set_away(gm_id, away)
    conn.commit()
