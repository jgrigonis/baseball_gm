# src/api/view_models/team_stats.py
#
# Context for the stats tab: one team's batting, pitching and fielding lines
# for a season (regular season or postseason).

from __future__ import annotations

from src.api.view_models.player_cards import attach_injuries
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.player_games import PlayerGameRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.stats import formulas


def team_stats_context(
    db,
    league_id: str,
    current_season_id: str | None,
    my_team_id: str | None,
    team_id: str | None,
    season_id: str | None,
    postseason: int,
) -> dict:
    """`team_id`, `season_id` and `postseason` are the user's picks, if any."""
    season_repo = SeasonRepository(db)
    team_repo = TeamRepository(db)

    # All seasons for this league, newest first
    all_seasons = season_repo.get_seasons_for_league(league_id)

    # Default to current season
    selected_season_id = season_id or current_season_id
    is_postseason = bool(postseason)

    # Default to user's team
    selected_team_id = team_id or my_team_id

    # All teams for the selected season
    all_teams = (
        team_repo.get_teams_in_league_season(league_id, selected_season_id)
        if selected_season_id
        else []
    )

    # With no team of their own (a viewer), or a team that isn't in the
    # selected season, start from the first team
    team_ids_in_season = {t["id"] for t in all_teams}
    if selected_team_id not in team_ids_in_season:
        selected_team_id = all_teams[0]["id"] if all_teams else None

    batters = []
    pitchers = []
    fielders = []
    team_games = 0

    if selected_season_id and selected_team_id:
        pss_repo = PlayerSeasonStatsRepository(db)
        team_games = pss_repo.get_max_games_played_for_team(
            selected_season_id, selected_team_id, is_postseason
        )
        min_ab = int(3.1 * team_games) if not is_postseason else 0
        min_outs = int(3 * team_games) if not is_postseason else 0

        rows = pss_repo.get_for_team(
            selected_season_id, selected_team_id, is_postseason
        )

        batters, pitchers = stat_lines(rows, min_ab, min_outs)
        fielders = fielding_lines(
            PlayerGameRepository(db).get_team_fielding_lines(
                selected_season_id, selected_team_id
            )
        )

    # Attach injury status only for current season
    is_current_season = selected_season_id == current_season_id
    injured_map = (
        InjuryRepository(db, league_id).get_team_injuries(selected_team_id)
        if selected_team_id and is_current_season
        else {}
    )
    attach_injuries(batters + pitchers + fielders, injured_map)

    # Year label for selected season
    selected_year = next(
        (s["year"] for s in all_seasons if s["id"] == selected_season_id), None
    )

    return {
        "all_teams": all_teams,
        "all_seasons": all_seasons,
        "selected_team_id": selected_team_id,
        "selected_season_id": selected_season_id,
        "selected_year": selected_year,
        "is_postseason": is_postseason,
        "team_games": team_games,
        "batters": batters,
        "pitchers": pitchers,
        "fielders": fielders,
    }


def stat_lines(rows: list, min_ab: int, min_outs: int) -> tuple[list, list]:
    """Batting and pitching lines from a team's player_season_stats rows."""
    batters = []
    pitchers = []
    for s in rows:
        ab = s.get("bat_ab") or 0
        h = s.get("bat_hits") or 0
        d = s.get("bat_doubles") or 0
        tr = s.get("bat_triples") or 0
        hr = s.get("bat_home_runs") or 0
        rbi = s.get("bat_rbi") or 0
        runs = s.get("bat_runs") or 0
        bb = s.get("bat_walks") or 0
        k = s.get("bat_strike_outs") or 0
        sb = s.get("bat_stolen_bases") or 0
        hbp = s.get("bat_hbp") or 0
        sf = s.get("bat_sac_flys") or 0
        g = s.get("bat_games_played") or 0

        if g > 0 or ab > 0:
            avg = round(formulas.batting_average(h, ab), 3)
            obp = round(formulas.on_base_pct(h, bb, hbp, ab, sf), 3)
            tb = formulas.total_bases(h, d, tr, hr)
            slg = round(formulas.slugging_pct(tb, ab), 3)
            qualifies_bat = ab >= min_ab
            ab_k = round(ab / k, 2) if k else None
            hr_ab = round(hr / ab, 3) if ab else None
            batters.append(
                {
                    "player_id": s["player_id"],
                    "name": f"{s['first_name']} {s['last_name']}",
                    "G": g,
                    "AB": ab,
                    "H": h,
                    "2B": d,
                    "3B": tr,
                    "HR": hr,
                    "RBI": rbi,
                    "R": runs,
                    "BB": bb,
                    "K": k,
                    "SB": sb,
                    "AVG": avg,
                    "OBP": obp,
                    "SLG": slg,
                    "OPS": round(obp + slg, 3),
                    "AB_K": ab_k,
                    "HR_AB": hr_ab,
                    "qualified": qualifies_bat,
                }
            )

        outs = s.get("pitch_outs") or 0
        pg = s.get("pitch_games_played") or 0
        if pg > 0 or outs > 0:
            er = s.get("pitch_earned_runs") or 0
            ph = s.get("pitch_hits") or 0
            pbb = s.get("pitch_walks") or 0
            pk = s.get("pitch_strike_outs") or 0
            phr = s.get("pitch_home_runs") or 0
            w = s.get("pitch_wins") or 0
            l = s.get("pitch_losses") or 0
            sv = s.get("pitch_saves") or 0
            ip_f = formulas.innings(outs)
            era = round(formulas.era(er, outs), 2)
            whip = round(formulas.whip(ph, pbb, outs), 2)
            bb9 = round(formulas.per_nine(pbb, outs), 2)
            hr9 = round(formulas.per_nine(phr, outs), 2)
            k9 = round(formulas.per_nine(pk, outs), 2)
            gs = s.get("pitch_games_started") or 0
            ip_disp = formulas.ip_str(outs)
            qualifies_pit = outs >= min_outs
            pitchers.append(
                {
                    "player_id": s["player_id"],
                    "name": f"{s['first_name']} {s['last_name']}",
                    "G": pg,
                    "GS": gs,
                    "CG": s.get("pitch_complete_games") or 0,
                    "SHO": s.get("pitch_shutouts") or 0,
                    "NH": s.get("pitch_no_hitters") or 0,
                    "W": w,
                    "L": l,
                    "SV": sv,
                    "IP": ip_disp,
                    "IP_val": ip_f,
                    "H": ph,
                    "ER": er,
                    "BB": pbb,
                    "K": pk,
                    "HR": phr,
                    "ERA": era,
                    "WHIP": whip,
                    "BB9": bb9,
                    "HR9": hr9,
                    "K9": k9,
                    "qualified": qualifies_pit,
                }
            )

    return batters, pitchers


def fielding_lines(def_rows: list) -> list:
    fielders = []
    for r in def_rows:
        po, a, e = r["po"] or 0, r["a"] or 0, r["e"] or 0
        denom = po + a + e
        fpct = round((po + a) / denom, 3) if denom else 1.0
        fielders.append(
            {
                "player_id": r["player_id"],
                "name": r["name"],
                "pos": r["position"].upper(),
                "G": r["g"] or 0,
                "PO": po,
                "A": a,
                "E": e,
                "DP": r["dp"] or 0,
                "TP": r["tp"] or 0,
                "PB": r["pb"] if r["pb"] else None,
                "FPCT": fpct,
            }
        )

    return fielders
