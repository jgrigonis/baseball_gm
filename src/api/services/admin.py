# src/api/services/admin.py
#
# What the admin pages (src/api/routers/admin.py) do to leagues and users.
# Kept apart from the routes so the CLI and tests can use them too.
#
# Removing a GM goes through leave_league, so it works the same as the GM
# leaving: in the lobby they drop off the list, after the start AI takes over
# their team, the commissioner role passes on, and a league with nobody left
# is deleted. Deleting a user removes them from each of their leagues that
# way first.

from __future__ import annotations

import uuid

from src.api.services.leave_league import leave_league
from src.api.services.passwords import hash_password
from src.api.services.ready_check import READY_CHECK_STATES
from src.db.locks import league_lock
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.ready_check_repo import ReadyCheckRepository
from src.db.repositories.user_repo import UserRepository
from src.league.league_constants import MAX_BACKSTORY_YEARS
from src.league.league_modes import BLITZ, SPEED_BLITZ

# The modes and paces a league can be set to (the others aren't built yet).
MODES = (BLITZ.key, SPEED_BLITZ.key)
PACES = ("timer", "confirmed")

# (min, max) for each number setting, matching the create-league form.
NUMBER_RANGES = {
    "sim_period_days": (1, 30),
    "num_seasons": (1, 420),
    "decision_window_sec": (30, 600),
    "draft_window_sec": (60, 1800),
    "lineup_window_sec": (60, 3600),
    "backstory_years": (0, MAX_BACKSTORY_YEARS),
}

NUMBER_LABELS = {
    "sim_period_days": "Days per sim period",
    "num_seasons": "Number of seasons",
    "decision_window_sec": "Decision window",
    "draft_window_sec": "Draft window",
    "lineup_window_sec": "Lineup window",
    "backstory_years": "Years of history",
}

# Settings that time the ready-check window. Changing one starts the current
# period's window over, so the new length applies now.
_WINDOW_SETTINGS = ("pace_control", *(k for k in NUMBER_RANGES if k.endswith("_sec")))


def _new_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


# ── Leagues ───────────────────────────────────────────────────────────────────


def settings_error(league: dict, settings: dict, season_count: int) -> str | None:
    """Why these settings can't be saved for the league, or None."""
    if not settings["name"].strip():
        return "The league needs a name."
    if settings["mode"] != league["mode"]:
        if league["state"] != "lobby":
            return "The mode can only change before the league starts."
        if settings["mode"] not in MODES:
            return f"Unknown mode '{settings['mode']}'."
    if settings["pace_control"] not in PACES:
        return f"Unknown pace '{settings['pace_control']}'."
    for key, (low, high) in NUMBER_RANGES.items():
        if not low <= settings[key] <= high:
            return f"{NUMBER_LABELS[key]} must be between {low} and {high}."
    if (
        settings["backstory_years"] != league["backstory_years"]
        and league["state"] != "lobby"
    ):
        return "The years of history can only change before the league starts."
    if settings["num_seasons"] < season_count:
        return f"The league has already started season {season_count}."
    return None


def update_league_settings(conn, league_id: str, settings: dict) -> str | None:
    """Save the league's settings. Returns an error instead if they don't fit
    the league."""
    league_repo = LeagueRepository(conn)
    league = league_repo.get_by_id(league_id)
    if not league:
        raise ValueError("League not found.")
    error = settings_error(league, settings, league_repo.count_seasons(league_id))
    if error:
        return error

    gm_repo = GMRepository(conn)
    commissioner = settings.pop("commissioner_gm_id", None)
    if commissioner and commissioner != league["commissioner_gm_id"]:
        gm = gm_repo.get_by_id(commissioner)
        if not _is_person(gm, league_id):
            return "The commissioner has to be one of the league's human GMs."
        gm_repo.set_commissioner(commissioner, league_id)

    settings["name"] = settings["name"].strip()
    league_repo.update_settings(league_id, settings)
    timing_changed = any(settings[k] != league[k] for k in _WINDOW_SETTINGS)
    if timing_changed:
        _restart_window(conn, league_id)
    conn.commit()
    return None


def _restart_window(conn, league_id: str) -> None:
    """Give the current period a fresh window under timer pace, so a window
    that ran out while the league was paused, or under the old timing,
    doesn't sim it at once."""
    league = LeagueRepository(conn).get_by_id(league_id)
    if league["pace_control"] == "timer" and league["state"] in READY_CHECK_STATES:
        ReadyCheckRepository(conn).open_window(league_id)


def set_paused(conn, league_id: str, paused: bool) -> None:
    """Pause a league, or resume it. Waits for a sim that's running to finish
    first: it raises LeagueBusy, so the admin can try again."""
    with league_lock(conn, league_id):
        LeagueRepository(conn).set_paused(league_id, paused)
        if not paused:
            _restart_window(conn, league_id)
        conn.commit()


def _is_person(gm: dict | None, league_id: str) -> bool:
    """A person's GM in this league (not an AI GM)."""
    return bool(
        gm and gm["league_id"] == league_id and gm["user_id"] and not gm["is_ai"]
    )


def remove_gm(conn, league_id: str, gm_id: str) -> None:
    if not _is_person(GMRepository(conn).get_by_id(gm_id), league_id):
        raise ValueError("Only a person's GM can be removed from a league.")
    leave_league(conn, league_id, gm_id)


# ── Users ─────────────────────────────────────────────────────────────────────


def create_user(
    conn,
    username: str,
    password: str,
    email: str | None,
    is_admin: bool,
    must_change: bool,
) -> str:
    """Add an account. Callers check the username, password and email first."""
    user_id = str(uuid.uuid4())
    UserRepository(conn).insert_user(
        user_id,
        _new_token(),
        username,
        username,
        hash_password(password),
        email=email,
        is_admin=is_admin,
        must_change_password=must_change,
    )
    conn.commit()
    return user_id


def set_password(conn, user_id: str, password: str, must_change: bool) -> None:
    """Set a user's password. It signs them out everywhere."""
    UserRepository(conn).set_password(
        user_id, hash_password(password), _new_token(), must_change
    )
    conn.commit()


def delete_user(conn, user_id: str) -> None:
    """Remove the user from each of their leagues, then delete the account."""
    gms = conn.execute(
        "SELECT id, league_id FROM gms WHERE user_id = %s", (user_id,)
    ).fetchall()
    for gm in gms:
        leave_league(conn, gm["league_id"], gm["id"])
    UserRepository(conn).delete(user_id)
    conn.commit()


def user_leagues(conn, user_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT l.id, l.name, l.state, l.is_paused, g.id AS gm_id,
                  (l.commissioner_gm_id = g.id) AS is_commissioner
           FROM gms g JOIN leagues l ON l.id = g.league_id
           WHERE g.user_id = %s
           ORDER BY l.created_at DESC""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]
