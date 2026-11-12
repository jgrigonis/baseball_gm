# src/api/view_models/team_stats.py
#
# Context for the stats tab: one team's batting, pitching and fielding lines
# for a season (regular season or postseason).

from __future__ import annotations

from src.api.services import season_value as sval
from src.api.view_models.player_cards import attach_injuries
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.player_games import PlayerGameRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_repo import TeamRepository
from src.stats import advanced, formulas, glossary, qualifiers as q


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
    record = None

    if selected_season_id and selected_team_id:
        pss_repo = PlayerSeasonStatsRepository(db)
        team_games = pss_repo.get_max_games_played_for_team(
            selected_season_id, selected_team_id, is_postseason
        )
        wins, losses = TeamGameRepository(db).get_team_record_for_phase(
            selected_season_id, selected_team_id, is_postseason
        )
        record = {"wins": wins, "losses": losses} if wins or losses else None
        # Qualifying is per team game; in the postseason everyone qualifies.
        qual_games = 0 if is_postseason else team_games

        rows = pss_repo.get_for_team(
            selected_season_id, selected_team_id, is_postseason
        )

        lg = advanced.LeagueRates.of(pss_repo.get_season_totals(selected_season_id))
        # WAR is a regular season number.
        values = {} if is_postseason else sval.season_values(db, selected_season_id)
        batters, pitchers = stat_lines(rows, qual_games, lg, values)
        fielders = fielding_lines(
            PlayerGameRepository(db).get_team_fielding_lines(
                selected_season_id, selected_team_id
            ),
            qual_games,
            {r["player_id"]: r.get("pitch_outs") or 0 for r in rows},
        )

    # Attach injury status only for current season
    is_current_season = selected_season_id == current_season_id
    show_injuries = selected_team_id and is_current_season
    inj = InjuryRepository(db, league_id)
    attach_injuries(
        batters + pitchers + fielders,
        inj.get_team_injuries(selected_team_id) if show_injuries else {},
        inj.get_team_injury_types(selected_team_id) if show_injuries else {},
    )

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
        "record": record,
        "batters": batters,
        "pitchers": pitchers,
        "fielders": fielders,
        "stat_tips": {
            "bat": glossary.BAT,
            "pit": glossary.PIT,
            "field": glossary.FIELD,
        },
    }


def stat_lines(
    rows: list,
    team_games: int,
    lg: advanced.LeagueRates | None = None,
    values: dict[str, dict] | None = None,
) -> tuple[list, list]:
    """Batting and pitching lines from a team's player_season_stats rows,
    each flagged qualified when he's played enough for his rate stats to
    count: 3.1 PA a team game; an inning a team game for a starter, half
    that for a reliever (fewer than half his games started). `lg`, the
    league's regular season rates, fills in the "+" stats and FIP;
    `values` (season_value.season_values) fills in WAR and Def."""
    values = values or {}
    min_pa = q.min_pa(team_games)
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
            qualifies_bat = q.plate_appearances(s) >= min_pa
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
                    "CS": s.get("bat_caught_stealing") or 0,
                    "AVG": avg,
                    "OBP": obp,
                    "SLG": slg,
                    "OPS": round(obp + slg, 3),
                    "AB_K": ab_k,
                    "HR_AB": hr_ab,
                    **advanced.batting(s, lg),
                    "Def": sval.defense(values, s["player_id"]),
                    "WAR": sval.bat_war(values, s["player_id"]),
                    **advanced.win_values(s, "bat"),
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
            qualifies_pit = outs >= q.min_outs(
                team_games, reliever=q.is_reliever(pg, gs)
            )
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
                    "PK": s.get("pitch_pickoffs") or 0,
                    "ERA": era,
                    "WHIP": whip,
                    "BB9": bb9,
                    "HR9": hr9,
                    "K9": k9,
                    **advanced.pitching(s, lg),
                    "WAR": sval.pit_war(values, s["player_id"]),
                    **advanced.win_values(s, "pitch"),
                    "qualified": qualifies_pit,
                }
            )

    return batters, pitchers


def catcher_lines(r) -> dict:
    """A catcher's running game: steals allowed, runners caught stealing,
    caught-stealing rate and runners he picked off. None (shown as —) at
    other positions."""
    if (r.get("position") or "").lower() != "c":
        return {"SB": None, "CS": None, "CS_PCT": None, "PK": None}
    sb, cs = r.get("sb") or 0, r.get("cs") or 0
    return {
        "SB": sb,
        "CS": cs,
        "CS_PCT": round(100 * cs / (sb + cs), 1) if sb + cs else None,
        "PK": r.get("cpk") or 0,
    }


def fielding_lines(
    def_rows: list, team_games: int, pitcher_outs: dict[str, int] | None = None
) -> list:
    """Fielding lines at each position, flagged qualified for FPCT: games
    there, half the team's games at catcher and two thirds elsewhere; for a
    pitcher an inning pitched a team game (pitcher_outs, by player)."""
    pitcher_outs = pitcher_outs or {}
    fielders = []
    for r in def_rows:
        po, a, e = r["po"] or 0, r["a"] or 0, r["e"] or 0
        denom = po + a + e
        fpct = round((po + a) / denom, 3) if denom else 1.0
        pos = r["position"]
        if pos == "p":
            qualified = pitcher_outs.get(r["player_id"], 0) >= q.min_field_outs(
                team_games
            )
        else:
            qualified = (r["g"] or 0) >= q.min_field_games(pos, team_games)
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
                **catcher_lines(r),
                "FPCT": fpct,
                "qualified": qualified,
            }
        )

    return fielders
