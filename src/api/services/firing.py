# src/api/services/firing.py
#
# Owners firing GMs (plans/owners.md, build step 6). The end-of-season review
# (owner_review.py) decides who's fired; once the owner's review message is
# written, carry_out() makes it so, for AI GMs and people alike:
#
# - The GM row stays with the team, like when a person leaves
#   (leave_league.py), so the team keeps its draft picks and history. It
#   goes to a new AI persona, who starts at the owner's grace level.
# - A fired person gets a row of their own with no team and fired_at set, so
#   the league stays in their list and they can still watch it
#   (dependencies.get_gm_or_viewer treats them as a viewer). gm_firings
#   remembers the firing and what the owner said, for the banner they see and
#   the news.
# - Re-entry on (leagues.reentry_enabled): between seasons they can take over
#   any team an AI GM runs right away, except the one that fired them
#   (takeover.py). One and done: they watch from then on. If that leaves a
#   league with nobody running a team, the league is over.
# - A fired commissioner hands the role to the person who has been in the
#   league longest; with nobody else, a re-entry league keeps it on their new
#   row so they have it back once they take a team.

from __future__ import annotations

import random

from src.api.services import badges, career, personas, trades
from src.db.repositories.gm_repo import GMRepository


def carry_out(conn, league_id: str, season_id: str, year: int) -> list[dict]:
    """Fire every GM this season's review fired. Returns one dict per firing
    (gm_firings row fields). Safe to run twice: a GM already fired this
    season isn't fired again."""
    rows = conn.execute(
        """SELECT e.gm_id, e.wins, e.losses, e.owner_id, g.team_id, g.user_id,
                  g.persona_id, g.display_name, g.is_ai, t.city, t.mascot
           FROM gm_season_evaluations e
           JOIN gms g ON g.id = e.gm_id
           LEFT JOIN teams t ON t.id = g.team_id
           WHERE e.season_id = %s AND g.league_id = %s AND e.verdict = 'fired'
             AND g.fired_at IS NULL AND g.team_id IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM gm_firings f
                             WHERE f.gm_id = e.gm_id AND f.season_id = e.season_id)
           ORDER BY g.is_ai, t.city""",
        (season_id, league_id),
    ).fetchall()
    out = []
    for r in rows:
        out.append(_fire(conn, league_id, season_id, year, dict(r)))
    return out


def _review_message(conn, gm_id: str, season_id: str) -> str | None:
    row = conn.execute(
        """SELECT body FROM owner_messages
           WHERE gm_id = %s AND season_id = %s AND kind = 'review'
           ORDER BY id DESC LIMIT 1""",
        (gm_id, season_id),
    ).fetchone()
    return row["body"] if row else None


def _fire(conn, league_id: str, season_id: str, year: int, r: dict) -> dict:
    gm_repo = GMRepository(conn)
    gm_id = r["gm_id"]
    person = not r["is_ai"] and r["user_id"]
    message = _review_message(conn, gm_id, season_id)
    firing = {
        "league_id": league_id,
        "season_id": season_id,
        "year": year,
        "team_id": r["team_id"],
        "gm_id": gm_id,
        "user_id": r["user_id"] if person else None,
        "persona_id": None if person else r["persona_id"],
        "display_name": r["display_name"],
        "owner_id": r["owner_id"],
        "wins": r["wins"],
        "losses": r["losses"],
        "message": message,
    }
    conn.execute(
        """INSERT INTO gm_firings
               (league_id, season_id, year, team_id, gm_id, user_id, persona_id,
                display_name, owner_id, wins, losses, message)
           VALUES (%(league_id)s, %(season_id)s, %(year)s, %(team_id)s, %(gm_id)s,
                   %(user_id)s, %(persona_id)s, %(display_name)s, %(owner_id)s,
                   %(wins)s, %(losses)s, %(message)s)""",
        firing,
    )
    trades.team_leaving(
        conn, league_id, r["team_id"], gm_id, reason="the team fired its GM."
    )
    rng = random.Random(f"{season_id}:{gm_id}:fired")
    if not person:
        # A new AI GM: a different persona, starting fresh with the owner.
        personas.give_persona(conn, league_id, gm_id, rng)
        return firing

    # Their record so far, before the team stops being theirs.
    career.record_league(conn, league_id, leaving_gm_id=gm_id)
    badges.award(conn, r["user_id"])
    gm_repo.hand_team_to_ai(gm_id)
    personas.give_persona(conn, league_id, gm_id, rng)
    # The owner's messages were to them, not to the new GM.
    conn.execute("DELETE FROM owner_messages WHERE gm_id = %s", (gm_id,))
    fired_id = gm_repo.create_gm(
        league_id=league_id, display_name=r["display_name"], user_id=r["user_id"]
    )
    conn.execute("UPDATE gms SET fired_at = NOW() WHERE id = %s", (fired_id,))
    firing["fired_gm_id"] = fired_id

    league = conn.execute(
        "SELECT commissioner_gm_id, reentry_enabled FROM leagues WHERE id = %s",
        (league_id,),
    ).fetchone()
    if league["commissioner_gm_id"] == gm_id:
        nxt = gm_repo.next_commissioner(league_id, fired_id)
        if nxt is None and league["reentry_enabled"]:
            nxt = fired_id
        gm_repo.set_commissioner(nxt, league_id)
    return firing


def nobody_left(conn, league_id: str) -> bool:
    """True when no person runs a team in the league and nobody fired can
    come back: one and done, every person fired."""
    row = conn.execute(
        """SELECT l.reentry_enabled,
                  EXISTS (SELECT 1 FROM gms g WHERE g.league_id = l.id
                          AND g.user_id IS NOT NULL AND NOT g.is_ai
                          AND g.fired_at IS NULL AND g.team_id IS NOT NULL) AS active,
                  EXISTS (SELECT 1 FROM gm_firings f WHERE f.league_id = l.id
                          AND f.user_id IS NOT NULL) AS fired
           FROM leagues l WHERE l.id = %s""",
        (league_id,),
    ).fetchone()
    return bool(
        row and row["fired"] and not row["active"] and not row["reentry_enabled"]
    )


# ── A fired person ───────────────────────────────────────────────────────────


def fired_from(conn, league_id: str, user_id: str) -> list[str]:
    """The teams in this league that fired this person."""
    rows = conn.execute(
        "SELECT DISTINCT team_id FROM gm_firings WHERE league_id = %s AND user_id = %s",
        (league_id, user_id),
    ).fetchall()
    return [r["team_id"] for r in rows if r["team_id"]]


def latest(conn, league_id: str, user_id: str) -> dict | None:
    """This person's latest firing in the league, with the team and owner
    names, for the banner they see while they're out of a job."""
    row = conn.execute(
        """SELECT f.*, t.city, t.mascot, o.name AS owner_name, o.archetype
           FROM gm_firings f
           LEFT JOIN teams t ON t.id = f.team_id
           LEFT JOIN owner_personas o ON o.id = f.owner_id
           WHERE f.league_id = %s AND f.user_id = %s
           ORDER BY f.fired_at DESC, f.id DESC LIMIT 1""",
        (league_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def rehired(conn, league_id: str, user_id: str, team_id: str) -> None:
    """A fired person took another job in the league."""
    conn.execute(
        """UPDATE gm_firings SET rehired_team_id = %s, rehired_at = NOW()
           WHERE id = (SELECT id FROM gm_firings
                       WHERE league_id = %s AND user_id = %s
                       ORDER BY fired_at DESC, id DESC LIMIT 1)""",
        (team_id, league_id, user_id),
    )
