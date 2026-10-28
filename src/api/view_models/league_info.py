# src/api/view_models/league_info.py
#
# A league's settings, how far along it is, and who runs its teams. The lobby
# shows these before the league starts; the top bar's season pill and the
# League page show them after.

from __future__ import annotations

from src.db.repositories.league_repo import LeagueRepository
from src.league.league_modes import get_mode
from src.league.trade_deadline import trades_enabled_for


def league_info(db, league: dict) -> dict:
    """What the settings rows (dashboard/partials/_league_settings_rows.html)
    and the League page show for one league."""
    gms = league_gms(db, league["id"])
    humans = sum(1 for g in gms if not g["is_ai"])
    return {
        "state": league["state"],
        "mode": get_mode(league["mode"]),
        "num_teams": league["num_teams"],
        "decision_window_sec": league["decision_window_sec"],
        "draft_window_sec": league["draft_window_sec"],
        "lineup_window_sec": league["lineup_window_sec"],
        "reentry_enabled": bool(league["reentry_enabled"]),
        "pace_control": league["pace_control"],
        "sim_period_days": league["sim_period_days"],
        "num_seasons": league["num_seasons"],
        "is_public": bool(league["is_public"]),
        "trades_enabled": trades_enabled_for(league["mode"]),
        "trade_vote": bool(league["trade_vote"]),
        "pick_trades": bool(league["pick_trades"]),
        # Seasons started so far, the current one included. 0 in the lobby.
        "season_number": LeagueRepository(db).count_seasons(league["id"]),
        "gms": gms,
        "human_gms": humans,
        # Before the league starts, open teams go to AI GMs at the start.
        "ai_gms": max(league["num_teams"] - humans, 0),
    }


def league_gms(db, league_id: str) -> list[dict]:
    """The league's active GMs with their teams, human GMs first."""
    rows = db.execute(
        """SELECT g.id, g.display_name, g.is_ai, t.city, t.mascot
           FROM gms g LEFT JOIN teams t ON t.id = g.team_id
           WHERE g.league_id = %s AND g.fired_at IS NULL
           ORDER BY g.is_ai, t.city, t.mascot, g.created_at""",
        (league_id,),
    ).fetchall()
    return [dict(r) for r in rows]
