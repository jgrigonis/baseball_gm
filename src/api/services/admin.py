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

from src.api.services import league_settings
from src.api.services.leave_league import leave_league
from src.api.services.passwords import hash_password
from src.api.services.ready_check import READY_CHECK_STATES
from src.db.locks import LeagueBusy, league_lock
from src.db.migration_files import migration_010_admin
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.ready_check_repo import ReadyCheckRepository
from src.db.repositories.user_repo import UserRepository
from src.league.league_constants import (
    MAX_BACKSTORY_YEARS,
    MAX_SEASONS,
    UNLIMITED_SEASONS,
)
from src.league.league_modes import BLITZ, LONGFORM, SPEED_BLITZ, get_mode

# The modes and paces a league can be set to (the others aren't built yet).
MODES = (BLITZ.key, SPEED_BLITZ.key, LONGFORM.key)
PACES = ("timer", "confirmed")

# (min, max) for each number setting, matching the create-league form.
NUMBER_RANGES = {
    "sim_period_days": (1, 30),
    "num_seasons": (UNLIMITED_SEASONS, MAX_SEASONS),  # 0: unlimited
    "decision_window_sec": (30, 600),
    "draft_window_sec": (60, 1800),
    "lineup_window_sec": (60, 3600),
    # Each person's pick in a multiplayer live draft (Long Form).
    "pick_timer_sec": (15, 600),
    "backstory_years": (0, MAX_BACKSTORY_YEARS),
}

NUMBER_LABELS = {
    "sim_period_days": "Days per sim period",
    "num_seasons": "Number of seasons",
    "decision_window_sec": "Decision window",
    "draft_window_sec": "Draft window",
    "lineup_window_sec": "Lineup window",
    "pick_timer_sec": "Draft pick timer",
    "backstory_years": "Years of history",
}

# Settings that time the ready-check window. Changing one starts the current
# period's window over, so the new length applies now.
WINDOW_KEYS = tuple(k for k in NUMBER_RANGES if k.endswith("_sec"))
# The admin can set any window from 1 second to 2.5 hours (testing, odd
# leagues). Commissioners and GMs stay inside NUMBER_RANGES.
ADMIN_WINDOW_RANGE = (1, 9000)
_WINDOW_SETTINGS = ("pace_control", *WINDOW_KEYS)


def _new_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


# ── Leagues ───────────────────────────────────────────────────────────────────


def settings_error(
    league: dict, settings: dict, season_count: int, admin: bool = False
) -> str | None:
    """Why these settings can't be saved for the league, or None. The admin
    gets the wider ADMIN_WINDOW_RANGE for the window lengths."""
    if not settings["name"].strip():
        return "The league needs a name."
    if settings["mode"] != league["mode"]:
        if league["state"] != "lobby":
            return "The mode can only change before the league starts."
        if settings["mode"] not in MODES:
            return f"Unknown mode '{settings['mode']}'."
    if settings["pace_control"] not in PACES:
        return f"Unknown pace '{settings['pace_control']}'."
    fixed = get_mode(settings["mode"]).pace
    if fixed and settings["pace_control"] != fixed:
        return f"{get_mode(settings['mode']).label} leagues use {fixed.title()} pace."
    for key, (low, high) in NUMBER_RANGES.items():
        # A value from before the range narrowed (e.g. 100 seasons) can stay.
        if settings[key] == league.get(key):
            continue
        if admin and key in WINDOW_KEYS:
            low, high = ADMIN_WINDOW_RANGE
        if not low <= settings[key] <= high:
            return f"{NUMBER_LABELS[key]} must be between {low} and {high}."
    if (
        settings["backstory_years"] != league["backstory_years"]
        and league["state"] != "lobby"
    ):
        return "The years of history can only change before the league starts."
    error = league_settings.injury_rate_error(settings.get("injury_rate"), league)
    if error:
        return error
    low = league_settings.fewest_seasons(league["state"], season_count)
    if (
        settings["num_seasons"] != league["num_seasons"]
        and UNLIMITED_SEASONS < settings["num_seasons"] < low
    ):
        if low > season_count:
            return f"Season {season_count} is over, so the league needs at least {low}."
        return f"The league has already started season {season_count}."
    return None


def update_league_settings(conn, league_id: str, settings: dict) -> str | None:
    """Save the league's settings. Returns an error instead if they don't fit
    the league."""
    league_repo = LeagueRepository(conn)
    league = league_repo.get_by_id(league_id)
    if not league:
        raise ValueError("League not found.")
    error = settings_error(
        league, settings, league_repo.count_seasons(league_id), admin=True
    )
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
    try:
        with league_lock(conn, league_id):
            league_repo.update_settings(league_id, settings)
            # Trades turned off expire open offers, and so on.
            league_settings.apply_changes(conn, dict(league), settings)
    except LeagueBusy:
        conn.rollback()
        return "A sim is running in this league. Try again in a minute."
    timing_changed = any(settings[k] != league[k] for k in _WINDOW_SETTINGS)
    if timing_changed:
        restart_window(conn, league_id)
    conn.commit()
    return None


def restart_window(conn, league_id: str) -> None:
    """Give the current period a fresh window under timer pace, so a window
    that ran out while the league was paused, or under the old timing,
    doesn't sim it at once. Off timer pace the window goes, so a switch to
    Confirmed takes the clock away."""
    league = LeagueRepository(conn).get_by_id(league_id)
    repo = ReadyCheckRepository(conn)
    if league["pace_control"] != "timer":
        repo.close_window(league_id)
    elif league["state"] in READY_CHECK_STATES:
        repo.open_window(league_id)


def set_paused(conn, league_id: str, paused: bool) -> None:
    """Pause a league, or resume it. Waits for a sim that's running to finish
    first: it raises LeagueBusy, so the admin can try again."""
    with league_lock(conn, league_id):
        LeagueRepository(conn).set_paused(league_id, paused)
        if not paused:
            restart_window(conn, league_id)
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


def uses_default_admin_name(user) -> bool:
    """An admin still signing in with the login the first deploy created
    (migration_010_admin). Everyone knows that name, so they're nudged to
    pick their own: on the account page and atop the admin pages."""
    return bool(
        user
        and user.get("is_admin")
        and (user.get("username") or "").lower()
        == migration_010_admin.DEFAULT_ADMIN_USERNAME.lower()
    )
