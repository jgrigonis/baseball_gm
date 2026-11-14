# src/api/services/turn_alerts.py
#
# Emails a GM when a multiplayer league is waiting on them and they aren't
# looking. Two parts:
#
# The clock (advance_due_leagues): a league moves on when every GM is ready
# or its window runs out, but that check only ran when a GM's page asked for
# the status. With everyone gone, an expired window sat there. The sim
# worker now runs the check itself every few seconds for any timer-paced
# league whose window has run out (src/worker.py).
#
# The email (after_period): when a new period opens, each GM who is in it
# (not away, not knocked out of the playoffs) gets one email, if
#   - they have an email on file and haven't turned turn emails off (Account),
#   - their page isn't open on the league right now (gms.seen_at is set by the
#     ready bar's poll, every few seconds while the tab is showing),
#   - they've been back to the league since the last one (one email per
#     absence, however many periods go by), and
#   - the window is long enough to act on: MIN_WINDOW_SEC, or no clock at all
#     (confirmed pace). Blitz's two-minute windows are over before the email
#     is read.
#
# Emails are sent from a background thread, so a slow mail server never holds
# the league lock or the sim worker.

from __future__ import annotations

import logging
import threading

from src.api.services import mailer
from src.config import settings
from src.db.connection import rollback_quietly

log = logging.getLogger(__name__)

# Shortest window worth an email.
MIN_WINDOW_SEC = 300

# A GM whose ready bar polled within this long has the league open.
SEEN_WITHIN_SEC = 60

# What the league is waiting on, by state.
_WHAT_NEXT = {
    "draft": "the draft",
    "preseason": "setting your opening lineup",
    "season": "the next sim",
    "playoffs": "the next playoff game",
    "offseason": "the offseason",
}


def _send_in_background(emails: list[tuple[str, str, str]]) -> None:
    if not emails:
        return

    def send_all():
        for to, subject, text in emails:
            mailer.send(to, subject, text)

    threading.Thread(target=send_all, name="turn-emails", daemon=True).start()


def _site() -> str | None:
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    if settings.smtp_host:
        log.error("PUBLIC_BASE_URL is not set, so no turn emails were sent.")
        return None
    return ""  # dev: the email only goes to the log


def _minutes(seconds: float) -> str:
    minutes = max(1, round(seconds / 60))
    if minutes < 90:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = round(minutes / 60)
    return f"{hours} hours"


def due_emails(conn, league_id: str) -> list[tuple[str, str, str]]:
    """The turn emails the league's current period calls for, marking each
    GM alerted. Commit afterwards."""
    from src.api.services.ready_check import READY_CHECK_STATES, _gms

    league = conn.execute(
        """SELECT name, state, pace_control, is_paused,
                  CASE WHEN pace_control = 'timer'
                       THEN EXTRACT(EPOCH FROM period_deadline - NOW())
                  END AS seconds_left
           FROM leagues WHERE id = %s""",
        (league_id,),
    ).fetchone()
    if not league or league["is_paused"] or league["state"] not in READY_CHECK_STATES:
        return []
    seconds_left = league["seconds_left"]
    if league["pace_control"] == "timer":
        if seconds_left is None or seconds_left < MIN_WINDOW_SEC:
            return []
    elif league["pace_control"] != "confirmed":
        return []

    present = {
        g["id"] for g in _gms(conn, league_id, league["state"]) if not g["is_away"]
    }
    if not present:
        return []
    rows = conn.execute(
        """UPDATE gms g SET alerted_at = NOW()
           FROM users u
           WHERE u.id = g.user_id AND g.id = ANY(%s)
             AND u.email IS NOT NULL AND u.email <> '' AND u.turn_emails
             AND (g.seen_at IS NULL
                  OR g.seen_at < NOW() - %s * INTERVAL '1 second')
             AND (g.alerted_at IS NULL OR g.seen_at > g.alerted_at)
           RETURNING u.email, g.display_name""",
        (list(present), SEEN_WITHIN_SEC),
    ).fetchall()
    if not rows:
        return []
    site = _site()
    if site is None:
        return []

    name = league["name"]
    what = _WHAT_NEXT.get(league["state"], "the next period")
    if seconds_left is not None:
        when = (
            f"The clock is running: you have about {_minutes(seconds_left)} "
            f"before it moves on without you."
        )
    else:
        when = "It won't move on until everyone clicks Ready."
    emails = []
    for r in rows:
        text = (
            f"Hi {r['display_name']},\n\n"
            f"{name} is waiting on you for {what}. Set your lineup, look at "
            f"trades, then click Ready.\n\n"
            f"{when}\n\n"
            f"Open the league:\n{site}/leagues/{league_id}/\n\n"
            f"You'll get one of these each time you're away while the league "
            f"is waiting, not one per period. To stop them, turn off turn "
            f"emails on your Account page:\n{site}/account\n"
        )
        emails.append((r["email"], f"Your move in {name}", text))
    return emails


def after_period(conn, league_id: str) -> None:
    """Email the GMs a newly opened period is waiting on. Never raises: an
    email problem mustn't fail the sim that already ran."""
    try:
        emails = due_emails(conn, league_id)
        conn.commit()
    except Exception:
        log.exception("League %s: couldn't work out turn emails", league_id)
        rollback_quietly(conn)
        return
    _send_in_background(emails)


def mark_seen(conn, gm_id: str) -> None:
    """The GM has the league open (their ready bar just polled)."""
    conn.execute("UPDATE gms SET seen_at = NOW() WHERE id = %s", (gm_id,))
    conn.commit()


def advance_due_leagues(conn) -> int:
    """Queue the next period for every multiplayer league whose window has run
    out, or that has no window open yet, with no sim already queued. Returns
    how many were queued. The sim worker calls this on a timer."""
    from src.api.services import ready_check

    rows = conn.execute(
        """SELECT l.id FROM leagues l
           WHERE l.state = ANY(%s) AND l.pace_control = 'timer' AND NOT l.is_paused
             AND (l.period_deadline IS NULL OR l.period_deadline <= NOW())
             AND (SELECT COUNT(*) FROM gms g
                  WHERE g.league_id = l.id AND NOT g.is_ai
                    AND g.user_id IS NOT NULL AND g.fired_at IS NULL) > 1
             AND NOT EXISTS (SELECT 1 FROM sim_jobs j
                             WHERE j.league_id = l.id
                               AND j.state IN ('queued', 'running'))""",
        (list(ready_check.READY_CHECK_STATES),),
    ).fetchall()
    conn.commit()
    queued = 0
    for r in rows:
        try:
            if ready_check.advance_if_due(conn, r["id"]):
                queued += 1
        except Exception:
            log.exception("League %s: the clock couldn't move it on", r["id"])
            rollback_quietly(conn)
    return queued
