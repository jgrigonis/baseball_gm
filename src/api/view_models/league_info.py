# src/api/view_models/league_info.py
#
# A league's settings, how far along it is, and who runs its teams. The lobby
# shows these before the league starts; the top bar's season pill and the
# League page show them after.

from __future__ import annotations

from src.api.services import owner_review
from src.db.repositories.league_repo import LeagueRepository
from src.league.league_constants import DEFAULT_INJURY_RATE
from src.league.league_modes import get_mode, injuries_allowed
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
        # Owners can fire GMs (src/api/services/owner_review.firing_on).
        "owner_firing": owner_review.firing_on(league),
        "pace_control": league["pace_control"],
        "sim_period_days": league["sim_period_days"],
        "num_seasons": league["num_seasons"],
        "is_public": bool(league["is_public"]),
        "join_code": None if league.get("single_player") else league.get("join_code"),
        "single_player": bool(league.get("single_player")),
        "late_joins": bool(league.get("late_joins")),
        "is_practice": bool(league.get("is_practice")),
        "trades_enabled": trades_enabled_for(league),
        "trade_vote": bool(league["trade_vote"]),
        "pick_trades": bool(league["pick_trades"]),
        "injuries_enabled": injuries_allowed(league),
        "injury_rate": league.get("injury_rate") or DEFAULT_INJURY_RATE,
        "weighted_schedule": bool(league.get("weighted_schedule")),
        "real_season": league.get("real_season"),
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
        """SELECT g.id, g.team_id, g.display_name, g.is_ai, g.persona_id, p.archetype,
                  t.city, t.mascot, u.username
           FROM gms g LEFT JOIN teams t ON t.id = g.team_id
           LEFT JOIN gm_personas p ON p.id = g.persona_id
           LEFT JOIN users u ON u.id = g.user_id
           WHERE g.league_id = %s AND g.fired_at IS NULL
           ORDER BY g.is_ai, t.city, t.mascot, g.created_at""",
        (league_id,),
    ).fetchall()
    return [dict(r) for r in rows]
