# src/api/services/settings_votes.py
#
# Changing settings in a league with more than one person (Josh's rules,
# 2026-11-09). A league with one person lets its commissioner just edit them
# (src/api/services/league_settings.py); with more, the commissioner proposes
# and everyone else votes:
#   - only the commissioner proposes, and counts as a yes
#   - every other human GM votes Approve or Reject; AI GMs don't vote
#   - one Reject sinks it at once
#   - once everyone has approved it passes at once; otherwise it passes when
#     it closes, before the period two after the one it was made in runs, so
#     everyone gets two whole decision windows. A GM who hasn't voted by then
#     counts as a yes
#   - one open proposal a league; the commissioner can withdraw it
# A proposal that no longer fits when it passes (the league moved past the
# season count it sets) is void. Passing applies the changes the way the
# admin's edit does: trades off expires open offers, new timing restarts the
# window, and so on (league_settings.apply_changes).
#
# GMs hear about it as gm_notifications kind 'settings', shown in the news
# bar with a link to the League page, where the proposal and its votes are.

from __future__ import annotations

import uuid

from psycopg.types.json import Jsonb

from src.api.services import admin, league_settings
from src.api.view_models.league_info import league_gms
from src.db.locks import LeagueBusy, league_lock
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.notification_repo import NotificationRepository
from src.db.repositories.ready_check_repo import ReadyCheckRepository
from src.league.league_constants import UNLIMITED_SEASONS
from src.league.league_modes import is_blitz_style

# The settings a vote can change, in the form's order, with their labels.
VOTABLE = {
    "name": "League name",
    "num_seasons": "Seasons",
    "pace_control": "Pace",
    "decision_window_sec": "Decision window",
    "draft_window_sec": "Draft window",
    "lineup_window_sec": "Lineup window",
    "sim_period_days": "Days per sim period",
    "weighted_schedule": "Weighted schedule",
    "injuries_enabled": "Injuries",
    "injury_rate": "Injury rate",
    "trades_enabled": "Trades",
    "trade_vote": "Trade vote",
    "pick_trades": "Draft pick trades",
    "reentry_enabled": "Re-entry",
}
_TRADE_KEYS = ("trades_enabled", "trade_vote", "pick_trades")

# Windows a proposal stays open: the one it's made in, then two whole ones.
WINDOWS_OPEN = 2


def show(key: str, value) -> str:
    """A setting's value as the League page writes it."""
    if key == "num_seasons":
        return "Unlimited" if value == UNLIMITED_SEASONS else str(value)
    if key == "injury_rate":
        return f"{value}%"
    if key.endswith("_sec"):
        return f"{value}s"
    if key == "pace_control":
        return str(value).title()
    if key == "weighted_schedule":
        return "Weighted" if value else "Balanced"
    if isinstance(value, bool):
        return "On" if value else "Off"
    return str(value)


def describe(changes: dict) -> list[dict]:
    """Each change as {key, label, old, new} for the page and the news."""
    return [
        {
            "key": k,
            "label": VOTABLE[k],
            "old": show(k, c["old"]),
            "new": show(k, c["new"]),
        }
        for k, c in changes.items()
    ]


def _summary(changes: dict) -> str:
    return ", ".join(f"{d['label']} {d['new']}" for d in describe(changes))


def current(league: dict) -> dict:
    """The league's votable settings as they stand, the defaults filled in."""
    return league_settings.current_values(league, VOTABLE)


def _humans(conn, league_id: str) -> list[dict]:
    return [g for g in league_gms(conn, league_id) if not g["is_ai"]]


def can_propose(league: dict, gm_id: str | None, human_gms: int) -> bool:
    """Whether this GM can propose changes: the commissioner of a running
    league with more than one person in it."""
    return bool(
        gm_id
        and league["commissioner_gm_id"] == gm_id
        and league["state"] in league_settings.RUNNING
        and not league.get("is_practice")
        and human_gms >= 2
    )


def open_proposal(conn, league_id: str) -> dict | None:
    """The league's open proposal with its votes, or None."""
    row = conn.execute(
        """SELECT * FROM settings_proposals
           WHERE league_id = %s AND status = 'open'""",
        (league_id,),
    ).fetchone()
    if not row:
        return None
    proposal = dict(row)
    proposal["votes"] = [
        dict(v)
        for v in conn.execute(
            """SELECT v.gm_id, v.vote, g.display_name, t.city, t.mascot
               FROM settings_votes v JOIN gms g ON g.id = v.gm_id
               LEFT JOIN teams t ON t.id = g.team_id
               WHERE v.proposal_id = %s
                 AND NOT g.is_ai AND g.fired_at IS NULL
               ORDER BY g.display_name""",
            (proposal["id"],),
        ).fetchall()
    ]
    return proposal


def view(conn, league: dict, gm_id: str | None) -> dict | None:
    """What the League page shows of the open proposal to this GM."""
    proposal = open_proposal(conn, league["id"])
    if not proposal:
        return None
    period = ReadyCheckRepository(conn).period(league["id"])
    left = max(proposal["closes_period"] - (period["sim_period"] or 0), 0)
    mine = next((v for v in proposal["votes"] if v["gm_id"] == gm_id), None)
    return {
        "id": proposal["id"],
        "changes": describe(proposal["changes"]),
        "votes": proposal["votes"],
        # Decision windows left, this one included.
        "windows_left": left,
        "can_vote": mine is not None,
        "my_vote": mine["vote"] if mine else None,
        "can_withdraw": gm_id is not None and proposal["proposer_gm_id"] == gm_id,
    }


def propose(conn, league_id: str, gm_id: str, form: dict) -> str | None:
    """The commissioner proposes the form's settings. Returns why not, or
    None once the proposal is open and the voters told."""
    league_repo = LeagueRepository(conn)
    league = league_repo.get_by_id(league_id)
    if not league:
        return "League not found."
    league = dict(league)
    humans = _humans(conn, league_id)
    if not can_propose(league, gm_id, len(humans)):
        return "Only the commissioner of a league with more than one person can propose changes."
    if open_proposal(conn, league_id):
        return "There's already a proposal waiting on votes."
    now = current(league)
    form = {k: v for k, v in form.items() if k in VOTABLE}
    if not is_blitz_style(league["mode"]):
        for k in _TRADE_KEYS:
            form.pop(k, None)
    if form.get("name") is not None:
        form["name"] = form["name"].strip()
    changes = {k: {"old": now[k], "new": v} for k, v in form.items() if v != now[k]}
    if not changes:
        return "Nothing changed."
    error = _error(conn, league, {k: c["new"] for k, c in changes.items()})
    if error:
        return error
    period = ReadyCheckRepository(conn).period(league_id)["sim_period"] or 0
    proposal_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO settings_proposals
               (id, league_id, proposer_gm_id, changes, closes_period)
           VALUES (%s, %s, %s, %s, %s)""",
        (proposal_id, league_id, gm_id, Jsonb(changes), period + WINDOWS_OPEN),
    )
    voters = [g for g in humans if g["id"] != gm_id]
    for g in voters:
        conn.execute(
            "INSERT INTO settings_votes (proposal_id, gm_id) VALUES (%s, %s)",
            (proposal_id, g["id"]),
        )
    proposer = next(
        (g["display_name"] for g in humans if g["id"] == gm_id), "The commissioner"
    )
    _tell(
        conn,
        [g["id"] for g in voters],
        "proposed",
        proposal_id,
        f"{proposer} proposed league settings changes ({_summary(changes)}). "
        "Vote on the League page. Not voting counts as approval.",
    )
    conn.commit()
    return None


def vote(conn, league_id: str, gm_id: str, yes: bool) -> str | None:
    """A GM votes on the open proposal. A Reject sinks it; the last Approve
    passes it. Returns why not, or None."""
    proposal = open_proposal(conn, league_id)
    if not proposal or not any(v["gm_id"] == gm_id for v in proposal["votes"]):
        return "There's no proposal for you to vote on."
    conn.execute(
        """UPDATE settings_votes SET vote = %s, voted_at = NOW()
           WHERE proposal_id = %s AND gm_id = %s""",
        (yes, proposal["id"], gm_id),
    )
    name = next(v["display_name"] for v in proposal["votes"] if v["gm_id"] == gm_id)
    if not yes:
        _close(
            conn,
            proposal,
            "rejected",
            f"{name} rejected",
            f"{name} rejected the league settings changes ({_summary(proposal['changes'])}). "
            "Nothing changes.",
        )
        conn.commit()
        return None
    conn.commit()
    # Everyone's approved: pass it now, unless a sim holds the league, in
    # which case it passes before the next period runs (close_due).
    if all(v["vote"] or v["gm_id"] == gm_id for v in proposal["votes"]):
        try:
            with league_lock(conn, league_id):
                _pass(conn, open_proposal(conn, league_id))
                conn.commit()
        except LeagueBusy:
            pass
    return None


def withdraw(conn, league_id: str, gm_id: str) -> str | None:
    proposal = open_proposal(conn, league_id)
    if not proposal or proposal["proposer_gm_id"] != gm_id:
        return "There's no proposal of yours to withdraw."
    _close(
        conn,
        proposal,
        "withdrawn",
        None,
        f"The commissioner withdrew the league settings changes ({_summary(proposal['changes'])}).",
    )
    conn.commit()
    return None


def close_due(conn, league_id: str, period: int) -> None:
    """Before a multiplayer period runs: pass the open proposal if its time
    is up or everyone has approved it. Run under the league lock."""
    proposal = open_proposal(conn, league_id)
    if not proposal:
        return
    if proposal["closes_period"] <= period or all(v["vote"] for v in proposal["votes"]):
        _pass(conn, proposal)


def _pass(conn, proposal: dict | None) -> None:
    """Apply a proposal's changes and tell everyone. Run under the lock."""
    if not proposal or proposal["status"] != "open":
        return
    league_repo = LeagueRepository(conn)
    league = dict(league_repo.get_by_id(proposal["league_id"]))
    settings = {k: c["new"] for k, c in proposal["changes"].items()}
    error = _error(conn, league, settings)
    if error:
        _close(
            conn,
            proposal,
            "void",
            error,
            f"The league settings changes ({_summary(proposal['changes'])}) "
            f"can't happen any more: {error}",
        )
        return
    league_repo.update_settings(league["id"], settings)
    league_settings.apply_changes(conn, league, settings)
    if any(k in settings for k in ("pace_control", *admin.WINDOW_KEYS)):
        admin.restart_window(conn, league["id"])
    _close(
        conn,
        proposal,
        "passed",
        None,
        f"League settings changed: {_summary(proposal['changes'])}.",
    )


def _close(conn, proposal: dict, status: str, reason: str | None, text: str) -> None:
    conn.execute(
        """UPDATE settings_proposals SET status = %s, reason = %s, decided_at = NOW()
           WHERE id = %s""",
        (status, reason, proposal["id"]),
    )
    # The vote's popups have nothing left to answer.
    conn.execute(
        """UPDATE gm_notifications SET seen_at = NOW()
           WHERE seen_at IS NULL AND kind = 'settings'
             AND payload->>'proposal_id' = %s""",
        (proposal["id"],),
    )
    everyone = [g["id"] for g in _humans(conn, proposal["league_id"])]
    _tell(conn, everyone, status, proposal["id"], text)


def _tell(conn, gm_ids, event: str, proposal_id: str, text: str) -> None:
    notes = NotificationRepository(conn)
    for gm_id in gm_ids:
        notes.add(
            gm_id,
            "settings",
            {"event": event, "proposal_id": proposal_id, "text": text},
        )


def _error(conn, league: dict, changes: dict) -> str | None:
    """Why these changes don't fit the league, or None. The admin's checks,
    with the rest of the settings as they stand."""
    full = {
        "name": league["name"],
        "mode": league["mode"],
        "pace_control": league["pace_control"],
        "backstory_years": league["backstory_years"],
        **{k: league[k] for k in admin.NUMBER_RANGES},
        **changes,
    }
    return admin.settings_error(
        league, full, LeagueRepository(conn).count_seasons(league["id"])
    )
