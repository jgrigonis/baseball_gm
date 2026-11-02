# src/api/view_models/lineup.py
#
# Context for the lineup tab: the active roster split into hitters and
# pitchers, the saved lineup/rotation/bullpen, and stat lines for display.

from __future__ import annotations

from src.api.view_models.player_cards import attach_injuries, lineup_card
from src.db.repositories.bullpen_roles_repo import BullpenRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.lineup_preference_repo import LineupPreferenceRepository
from src.db.repositories.player_games import PlayerGameRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.player.face import face_url
from src.stats import formulas
from src.team.manager_profile import ManagerProfile


def lineup_context(db, league_id: str, gm: dict, season_id: str | None) -> dict:
    team_id = gm["team_id"]

    # For stat display use last season with completed games so preseason still
    # shows last year's numbers when building the new lineup.
    _stats_s = SeasonRepository(db).get_last_with_completed_games(league_id)
    stats_season_id = _stats_s["id"] if _stats_s else season_id

    # Load all 40-man players with grades (skills batched in the query)
    player_repo = PlayerRepository(db)
    hitters = []
    pitchers = []
    team = TeamRepository(db).get_city_and_mascot(team_id) or {}
    for row in player_repo.get_active_roster_with_skills(team_id):
        g = lineup_card(row)
        g["face_url"] = face_url(
            g["player_id"], g.get("age"), team.get("city"), team.get("mascot")
        )
        if g.get("player_type") == "pitcher":
            pitchers.append(g)
        else:
            hitters.append(g)

    # Load saved lineup preferences, rotation, bullpen
    lp_repo = LineupPreferenceRepository(db)
    rot_repo = TeamRotationsRepository(db, league_id)
    bp_repo = BullpenRepository(db)

    saved_lineup = lp_repo.get_by_gm_id(gm["id"])
    saved_rotation = (
        rot_repo.get_saved_rotation(team_id, season_id) if season_id else []
    )
    saved_bullpen = bp_repo.get_roles_map(team_id, season_id) if season_id else {}
    saved_rotation_pointer = (
        rot_repo.get_rotation_pointer_player(team_id, season_id)
        if season_id and saved_rotation
        else None
    )

    # Attach season stats to each player for display
    if stats_season_id:
        stats_map = PlayerSeasonStatsRepository(db).get_team_stats_map(
            stats_season_id, team_id
        )
        attach_lineup_stats(hitters, pitchers, stats_map)

    # Load fielding stats by player+position for the season
    fielding_stats_map: dict = {}
    if stats_season_id:
        fielding_stats_map = fielding_by_position(
            PlayerGameRepository(db).get_team_fielding_by_position(
                stats_season_id, team_id
            )
        )

    inj = InjuryRepository(db, league_id)
    attach_injuries(
        hitters + pitchers,
        inj.get_team_injuries(team_id),
        inj.get_team_injury_types(team_id),
        inj.get_rust([p["player_id"] for p in hitters + pitchers]),
    )
    # Tell template whether we're in playoffs so the nav button points the right way
    league_row = LeagueRepository(db).get_by_id(league_id)
    return {
        "hitters": hitters,
        "pitchers": pitchers,
        "fielding_stats_map": fielding_stats_map,
        "saved_lineup": saved_lineup,
        "saved_rotation": saved_rotation,
        "saved_bullpen": saved_bullpen,
        "saved_rotation_pointer": saved_rotation_pointer,
        "is_playoffs": league_row and league_row["state"] == "playoffs",
        # How many starters Auto-fill and Rebuild put in the rotation (Strategy tab)
        "rotation_size": ManagerProfile.from_row(
            GMRepository(db).get_profile(gm["id"])
        ).rotation_size,
    }


def attach_lineup_stats(hitters: list, pitchers: list, stats_map: dict) -> None:
    for p in hitters:
        s = stats_map.get(p["player_id"])
        if s and (s["bat_ab"] or 0) > 0:
            avg = s["bat_hits"] / s["bat_ab"]
            p["stat_avg"] = f"{avg:.3f}"
            p["stat_hr"] = s["bat_home_runs"] or 0
        else:
            p["stat_avg"] = None
            p["stat_hr"] = None
    for p in pitchers:
        s = stats_map.get(p["player_id"])
        if s and (s["bat_ab"] or 0) > 0:
            avg = s["bat_hits"] / s["bat_ab"]
            p["stat_avg"] = f"{avg:.3f}"
            p["stat_hr"] = s["bat_home_runs"] or 0
        else:
            p["stat_avg"] = None
            p["stat_hr"] = None
        if s and (s["pitch_games_played"] or 0) > 0:
            outs = s["pitch_outs"] or 0
            p["stat_gs"] = s["pitch_games_started"] or 0
            p["stat_era"] = (
                f"{formulas.era(s['pitch_earned_runs'], outs):.2f}" if outs else "--"
            )
            p["stat_ip"] = formulas.ip_str(outs)
            p["stat_w"] = s["pitch_wins"] or 0
            p["stat_l"] = s["pitch_losses"] or 0
            p["stat_sv"] = s["pitch_saves"] or 0
        else:
            p["stat_gs"] = None
            p["stat_era"] = None
            p["stat_ip"] = None
            p["stat_w"] = None
            p["stat_l"] = None
            p["stat_sv"] = None


def fielding_by_position(fd_rows: list) -> dict:
    """{player_id: {position: fielding line}} from per-position fielding totals."""
    fielding_stats_map: dict = {}
    for r in fd_rows:
        pid = r["player_id"]
        po, a, e = (r["po"] or 0), (r["a"] or 0), (r["e"] or 0)
        total = po + a + e
        fpct = round((po + a) / total, 3) if total > 0 else None
        fielding_stats_map.setdefault(pid, {})[r["position"]] = {
            "g": r["g"],
            "po": po,
            "a": a,
            "e": e,
            "pb": r["pb"] or 0,
            "fpct": fpct,
        }

    return fielding_stats_map
