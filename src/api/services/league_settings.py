# src/api/services/league_settings.py
#
# The league settings a commissioner can change after the league starts,
# while they're the only person in it (Josh's call, 2026-11-09): the name,
# how many seasons, injuries, trades, draft pick trades, the schedule, days
# per sim period and re-entry. Once a second person joins they lock again,
# so nobody changes the rules on a league other people play in. The admin
# League page changes the same settings in any league
# (src/api/services/admin.py), and both go through apply_changes for what a
# change sets off.
#
# What each change does mid-league:
#   - Seasons can't go below the season being played, or once its playoffs
#     are over, below the next one (see fewest_seasons).
#   - Injuries off: nobody gets hurt from the next game on. Players already
#     hurt heal on their usual timeline.
#   - Injury rate: how often players get hurt, from the next game on.
#   - Trades off: every open offer expires.
#   - Draft pick trades off: open offers with a pick in them are called off.
#     Picks already traded stay traded.
#   - Schedule: this season's games are already made, so the new one starts
#     next season.

from __future__ import annotations

from src.api.services import trades
from src.db.locks import league_lock
from src.db.repositories.career_repo import CareerRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.trade_repo import TradeRepository
from src.api.view_models.league_info import league_gms
from src.league.league_constants import (
    DEFAULT_INJURY_RATE,
    INJURY_RATES,
    MAX_SEASONS,
    UNLIMITED_SEASONS,
)
from src.league.league_modes import injuries_allowed, is_blitz_style
from src.league.trade_deadline import trades_enabled_for

# The settings a solo commissioner can change, in the edit form's order.
SOLO_SETTINGS = (
    "name",
    "num_seasons",
    "sim_period_days",
    "injuries_enabled",
    "injury_rate",
    "trades_enabled",
    "pick_trades",
    "weighted_schedule",
    "reentry_enabled",
)

# The states a league can be edited in: started and not over yet.
RUNNING = ("draft", "preseason", "season", "playoffs", "offseason", "evaluation")
# Once the playoffs are done, the league already decided whether that season
# was its last (sim_playoff.py), so the count can't come back down to it.
_SEASON_OVER = ("offseason", "evaluation")

SIM_PERIOD_RANGE = (1, 30)


def current_values(league: dict, keys) -> dict:
    """These settings as the league has them, with the mode's defaults filled
    in for injuries and trades (older leagues may have none stored)."""
    out = {}
    for k in keys:
        if k == "injuries_enabled":
            out[k] = injuries_allowed(league)
        elif k == "injury_rate":
            out[k] = league.get("injury_rate") or DEFAULT_INJURY_RATE
        elif k == "trades_enabled":
            out[k] = trades_enabled_for(league)
        elif k in ("pick_trades", "trade_vote", "weighted_schedule", "reentry_enabled"):
            out[k] = bool(league.get(k))
        else:
            out[k] = league[k]
    return out


def fewest_seasons(state: str, season_count: int) -> int:
    """The lowest season count the league can be set to now: the season it's
    in, or the next one once this one's playoffs are over."""
    return season_count + 1 if state in _SEASON_OVER else season_count


def season_choices(state: str, season_count: int, current: int) -> list[int]:
    """The Seasons slider's stops: from the lowest allowed count to
    MAX_SEASONS, then unlimited (0). A league already past MAX_SEASONS keeps
    its count."""
    low = max(fewest_seasons(state, season_count), 1)
    choices = [*range(low, MAX_SEASONS + 1), UNLIMITED_SEASONS]
    if current not in choices:
        choices.insert(-1, current)
    return choices


def can_edit(league: dict, gm_id: str | None, human_gms: int) -> bool:
    """Whether this GM can change the league's settings: its commissioner,
    in a running league with no other person in it. Not the tutorial."""
    return bool(
        gm_id
        and league["commissioner_gm_id"] == gm_id
        and league["state"] in RUNNING
        and not league.get("is_practice")
        and human_gms < 2
    )


def solo_error(league: dict, settings: dict, season_count: int) -> str | None:
    """Why these settings can't be saved, or None."""
    if not settings["name"].strip():
        return "The league needs a name."
    seasons = settings["num_seasons"]
    if seasons != league["num_seasons"]:
        low = max(fewest_seasons(league["state"], season_count), 1)
        if seasons != UNLIMITED_SEASONS and not low <= seasons <= MAX_SEASONS:
            return f"Seasons must be between {low} and {MAX_SEASONS}, or unlimited."
    days = settings["sim_period_days"]
    if days != league["sim_period_days"]:
        low, high = SIM_PERIOD_RANGE
        if not low <= days <= high:
            return f"Days per sim period must be between {low} and {high}."
    error = injury_rate_error(settings.get("injury_rate"), league)
    if error:
        return error
    return None


def injury_rate_choices(current: int) -> list[int]:
    """The Injury rate slider's stops, with the league's own rate among them
    even if the steps have changed since it was set."""
    return sorted({*INJURY_RATES, current})


def injury_rate_error(rate, league: dict | None = None) -> str | None:
    """Why this Injury rate can't be saved, or None. A league keeps the rate
    it has even if the steps change."""
    if rate is None or (league and rate == league.get("injury_rate")):
        return None
    if rate not in INJURY_RATES:
        steps = ", ".join(f"{r}%" for r in INJURY_RATES)
        return f"Injury rate must be one of {steps}."
    return None


def save_solo(conn, league_id: str, gm_id: str, settings: dict) -> str | None:
    """A solo commissioner saves the edit form. Returns why it can't be saved
    instead, if it can't. Raises LeagueBusy while a sim is running, since
    turning trades off changes offers the sim may be deciding."""
    league_repo = LeagueRepository(conn)
    with league_lock(conn, league_id):
        league = league_repo.get_by_id(league_id)
        humans = sum(1 for g in league_gms(conn, league_id) if not g["is_ai"])
        if not league or not can_edit(dict(league), gm_id, humans):
            return "Only the commissioner of a one-person league can change these."
        league = dict(league)
        settings = {k: settings.get(k) for k in SOLO_SETTINGS}
        if settings["injury_rate"] is None:  # an older form without the slider
            settings["injury_rate"] = current_values(league, ["injury_rate"])[
                "injury_rate"
            ]
        if not is_blitz_style(league["mode"]):
            # Long Form doesn't trade yet, so its trade settings stay put.
            settings["trades_enabled"] = league["trades_enabled"]
            settings["pick_trades"] = league["pick_trades"]
        error = solo_error(league, settings, league_repo.count_seasons(league_id))
        if error:
            return error
        settings["name"] = settings["name"].strip()
        league_repo.update_settings(league_id, settings)
        apply_changes(conn, league, settings)
        # A vote left open from when others were in the league is moot now.
        conn.execute(
            """UPDATE settings_proposals SET status = 'withdrawn', decided_at = NOW(),
                      reason = 'edited alone'
               WHERE league_id = %s AND status = 'open'""",
            (league_id,),
        )
        conn.commit()
    return None


def apply_changes(conn, before: dict, settings: dict) -> None:
    """What saving these settings sets off, given the league as it was. Run
    after the new settings are written, under the league lock."""
    league_id = before["id"]
    if "name" in settings and settings["name"] != before["name"]:
        CareerRepository(conn).rename_league(league_id, settings["name"])  # profiles
    if "trades_enabled" in settings and not settings["trades_enabled"]:
        trades.close_all(conn, league_id)
    elif "pick_trades" in settings and not settings["pick_trades"]:
        _call_off_pick_offers(conn, league_id)


def _call_off_pick_offers(conn, league_id: str) -> None:
    """Draft pick trades were turned off: every open offer with a pick in it
    is off."""
    for offer in TradeRepository(conn).open_offers(league_id):
        items = offer["sent"] + offer["received"]
        if any(i.get("is_pick") for i in items):
            trades.void(conn, league_id, offer, "draft pick trades were turned off.")
