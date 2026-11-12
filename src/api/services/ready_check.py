# src/api/services/ready_check.py
#
# How a multiplayer league (two or more human GMs) moves forward. Nobody sims
# it on their own: each period runs when every GM who isn't away has clicked
# Ready, or, under timer pace, when the Decision Window runs out.
#
# pace_control:
#   timer      every GM ready, or the window runs out: draft_window_sec for
#              the draft, lineup_window_sec for the preseason period (setting
#              the first lineup), decision_window_sec for everything else
#   confirmed  every GM ready; no clock
#   scheduled  a fixed real-world interval (not built yet)
#
# What a period does depends on the league's state: sim_period_days of the
# regular season, one playoff day, the offseason, or the draft.
#
# A period that starts with a person as an All-Star or Rookie Game captain,
# with picks still to make, gets the Lineup Window instead (or the Decision
# Window, if that's longer): a whole draft takes longer than one decision.
#
# In leagues that trade, the period that reaches the trade deadline stops
# after deadline day's games, and the next window is
# TRADE_DEADLINE_WINDOW_MULTIPLIER times as long, for last-minute deals.
# Before each period runs, trade offers between GMs whose time is up expire
# and league votes that end close (src/api/services/trades.py).
#
# In the playoffs, a GM whose team didn't make it, or has been knocked out,
# counts as away. With no GM left who isn't away, nobody has a decision to
# make, so the playoffs sim straight through without waiting on the clock.
#
# An admin can pause a league: nothing runs until they resume it, and resuming
# starts the period's window over.
#
# The check runs whenever a GM clicks Ready or asks for the status, and the
# sim worker runs it every few seconds for leagues whose window has run out,
# so a league moves on with nobody watching. When a new period opens, GMs who
# aren't looking get an email (src/api/services/turn_alerts.py). A period
# that's due is queued as a job for the sim worker (src/api/services/
# sim_jobs.py), which runs it; a league has one job at most, so however many
# requests see it come due at once, it runs once.

from __future__ import annotations

import logging

from src.api.services import all_star, owner_office, sim_jobs, trades, turn_alerts
from src.api.services.draft_execute import execute_blitz_draft
from src.api.services.offseason_service import run_offseason
from src.api.services.sim_next import sim_days
from src.api.services.sim_playoff import sim_playoff
from src.db.locks import LeagueBusy
from src.db.repositories.all_star_repo import AllStarRepository
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.happiness_repo import HappinessRepository
from src.db.repositories.news_repo import NewsRepository
from src.db.repositories.notification_repo import NotificationRepository
from src.db.repositories.playoff_repo import PlayoffRepository
from src.db.repositories.ready_check_repo import ReadyCheckRepository
from src.db.repositories.season_repo import SeasonRepository
from src.league import trade_deadline
from src.league.league_constants import TRADE_DEADLINE_WINDOW_MULTIPLIER

log = logging.getLogger(__name__)

# League states in which a period can run.
READY_CHECK_STATES = ("draft", "preseason", "season", "playoffs", "offseason")

# More periods than a full playoffs takes, so a sim that stops advancing can't
# keep the straight-through loop going forever.
MAX_STRAIGHT_THROUGH = 40


def is_multiplayer(conn, league_id: str) -> bool:
    return ReadyCheckRepository(conn).human_gm_count(league_id) > 1


def _gms(conn, league_id: str, state: str) -> list[dict]:
    """The human GMs, each marked `out` if it's the playoffs and their team
    isn't still in them. An out GM counts as away."""
    gms = ReadyCheckRepository(conn).gms(league_id)
    alive = None
    if state == "playoffs":
        season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
        alive = PlayoffRepository(conn).alive_team_ids(season_id)
    for g in gms:
        g["out"] = alive is not None and g["team_id"] not in alive
        g["is_away"] = g["is_away"] or g["out"]
    return gms


def _nobody_present(period: dict, gms: list[dict]) -> bool:
    """The playoffs with every GM away or out: nobody to wait for."""
    return period["state"] == "playoffs" and all(g["is_away"] for g in gms)


def _due(period: dict, gms: list[dict]) -> bool:
    present = [g for g in gms if not g["is_away"]]
    if _nobody_present(period, gms):
        return True
    # Otherwise, with everyone away only the clock moves the league.
    if present and all(g["ready"] for g in present):
        return True
    return (
        period["pace_control"] == "timer"
        and period["seconds_left"] is not None
        and period["seconds_left"] <= 0
    )


def _run_period(conn, league_id: str, state: str, days: int) -> bool:
    """Run one period. Returns True if the sim stopped at the trade deadline,
    so the next period gets the longer deadline window."""
    if state in ("preseason", "season"):
        return sim_days(league_id, conn, days).get("trade_deadline", False)
    elif state == "playoffs":
        sim_playoff(league_id, conn, mode="game")
    elif state == "offseason":
        run_offseason(league_id, conn)
    elif state == "draft":
        draft = DraftRepository(conn).get_current_for_league(league_id)
        if draft and draft["state"] != "complete":
            execute_blitz_draft(draft["id"], conn)
    return False


def _captain_drafting(conn, league_id: str) -> bool:
    """A person is an All-Star or Rookie Game captain with picks still to
    make, so the period gets the Lineup Window."""
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    return all_star.person_drafting(conn, league_id, season_id)


def advance_if_due(conn, league_id: str) -> bool:
    """Queue the league's next period for the sim worker if it is due.
    Returns True if this call queued it. Opens the Decision Window for a period that has none yet (the
    first one, or after a switch to timer pace)."""
    repo = ReadyCheckRepository(conn)
    period = repo.period(league_id)
    if (
        not period
        or period["state"] not in READY_CHECK_STATES
        or period["pace_control"] == "scheduled"
        or period["is_paused"]
        or not is_multiplayer(conn, league_id)
    ):
        return False

    if period["pace_control"] == "timer" and period["period_deadline"] is None:
        repo.open_window(league_id)
        conn.commit()
        period = repo.period(league_id)

    if not _due(period, _gms(conn, league_id, period["state"])):
        return False

    try:
        sim_jobs.submit(conn, league_id, "period", {"sim_period": period["sim_period"]})
    except LeagueBusy:
        # Already queued, or something else is moving the league on.
        return False
    return True


def run_period(conn, league_id: str, sim_period: int) -> bool:
    """Run the period that was due when its job was queued, holding the
    league lock (the sim worker's job, src/api/services/sim_jobs.py).
    Returns False without running anything if it isn't due any more."""
    repo = ReadyCheckRepository(conn)
    now = repo.period(league_id)
    # Another job may have run it, or an admin paused the league, since.
    if (
        not now
        or now["is_paused"]
        or now["sim_period"] != sim_period
        or not _due(now, _gms(conn, league_id, now["state"]))
    ):
        return False
    # Keep going while it's the playoffs and there's nobody to wait for:
    # straight through to the offseason.
    for _ in range(MAX_STRAIGHT_THROUGH):
        log.info(
            "League %s: running period %s (%s)",
            league_id,
            now["sim_period"],
            now["state"],
        )
        trades.close_due(conn, league_id, now["sim_period"])
        # (Imported here: settings_votes reaches this module through admin.)
        from src.api.services import settings_votes

        settings_votes.close_due(conn, league_id, now["sim_period"])
        at_deadline = _run_period(conn, league_id, now["state"], now["sim_period_days"])
        repo.next_period(
            league_id,
            window_multiplier=TRADE_DEADLINE_WINDOW_MULTIPLIER if at_deadline else 1,
            lineup_window=_captain_drafting(conn, league_id),
        )
        conn.commit()
        now = repo.period(league_id)
        if not _nobody_present(now, _gms(conn, league_id, now["state"])):
            break
    # Email the GMs who aren't looking that it's their move.
    turn_alerts.after_period(conn, league_id)
    return True


def status(conn, league_id: str, gm_id: str) -> dict:
    """What the ready-check bar shows one GM."""
    if not is_multiplayer(conn, league_id):
        return {"multiplayer": False}
    period = ReadyCheckRepository(conn).period(league_id)
    gms = _gms(conn, league_id, period["state"])
    me = next((g for g in gms if g["id"] == gm_id), None)
    seconds_left = period["seconds_left"]
    league = {
        "mode": period["mode"],
        "state": period["state"],
        "trades_enabled": period["trades_enabled"],
    }
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    window = trade_deadline.window(conn, league, season_id)
    # All-Star voting (the tab shows in the season and the playoffs), and
    # whether this GM still has a ballot to save.
    star_phase = (
        all_star.phase(conn, season_id)
        if period["state"] in ("season", "playoffs")
        else "none"
    )
    return {
        "multiplayer": True,
        "pace": period["pace_control"],
        "league_state": period["state"],
        "active": period["state"] in READY_CHECK_STATES,
        "paused": period["is_paused"],
        "period": period["sim_period"],
        "seconds_left": max(0, round(seconds_left))
        if seconds_left is not None
        else None,
        # A period (or another sim) queued or running. Not the league lock:
        # trades, budget saves, roster moves and even another GM's poll
        # checking it hold that for a moment, and the page would flash
        # "simming" with I'm ready greyed out.
        "simming": sim_jobs.league_has_job(conn, league_id),
        # The sim stopped after deadline day's games: last chance to trade.
        "trade_deadline": window["open"] and window["deadline_day"],
        # Offers and votes waiting on this GM, and whether they have news
        # to fetch (e.g. an offer another GM just made them).
        "trade_inbox": trades.inbox_count(conn, league_id, me or {}) if me else 0,
        "has_news": NotificationRepository(conn).has_unseen(gm_id),
        # Stories since the GM last opened the News tab (its badge).
        "news_unseen": NewsRepository(conn).count_unseen(league_id, gm_id),
        # Players who've asked to be traded (the Roster tab's badge).
        "trade_wanted": HappinessRepository(conn, league_id).team_trade_requests(
            me["team_id"] if me else None
        ),
        # Owner messages the GM hasn't read (the Owner tab's badge).
        "owner_unseen": owner_office.unseen(conn, gm_id),
        "all_star": star_phase,
        "all_star_vote_due": bool(
            star_phase == "open"
            and me
            and me["team_id"]
            and AllStarRepository(conn).ballot(season_id, me["team_id"]) is None
        ),
        # A pick in the All-Star draft (or the tie for the last spot) waiting
        # on this GM, a captain.
        "all_star_turn": bool(
            star_phase == "done"
            and me
            and all_star.my_turn(conn, league_id, season_id, me["team_id"])
        ),
        "you_ready": bool(me and me["ready"]),
        "you_away": bool(me and me["is_away"] and not me["out"]),
        "you_out": bool(me and me["out"]),
        "gms": [
            {
                "name": g["display_name"],
                "ready": g["ready"],
                "away": g["is_away"],
                "out": g["out"],
            }
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
