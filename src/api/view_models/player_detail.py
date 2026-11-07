# src/api/view_models/player_detail.py
#
# Data for the player panel (slide-in card) and the player career page.

from __future__ import annotations

from datetime import date

from src.player.injury_types import injury_label
from src.api.grade_curves import role_to_grade
from src.api.schemas import player_row_to_grades, skill_to_grade
from src.api.view_models.player_cards import (
    compute_ratings,
    overall_grade as player_overall_grade,
    overall_value as player_overall_value,
    ratings_to_grade_map,
    rust_view,
)
from src.db.repositories.all_star_repo import AllStarRepository
from src.db.repositories import contract_repo
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.happiness_repo import HappinessRepository
from src.player import happiness as hp
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.jersey_repo import JerseyRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.pitcher_state import PitcherStateRepository
from src.db.repositories.player_energy import PlayerEnergyRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.api.services import hr_derby, rookie_game
from src.api.services import awards as awards_service
from src.api.services import hall_of_fame, icons
from src.league import all_star
from src.league import awards as awards_mod
from src.api.services import season_value as sv
from src.stats import advanced, formulas
from src.web.utils import _current_league_date


def league_current_date(db, league_id: str) -> date | None:
    """The league's current game date, for energy recovery and injury checks."""
    league_row = LeagueRepository(db).get_by_id(league_id)
    current_date: date | None = None
    if league_row:
        season_id = SeasonRepository(db).get_current_id_for_league(league_id)
        date_str = _current_league_date(db, season_id, league_row.get("state", ""))
        if date_str:
            try:
                current_date = date.fromisoformat(date_str)
            except ValueError:
                pass
    return current_date


def _contract(db, league_id: str, pid: str) -> dict | None:
    """The deal he plays under this season, for the panel."""
    repo = ContractRepository(db)
    year = repo.current_year(league_id)
    if year is None:
        return None
    return contract_repo.view(repo.active(pid, year), year)


def _asking(db, league_id: str, pid: str) -> dict | None:
    """A free agent's asking price (services/free_agents.py)."""
    from src.api.services.free_agents import asking_deal, market_discount, price_scale
    from src.player.contracts import format_salary

    year = ContractRepository(db).current_year(league_id)
    record = PlayerRepository(db).look_up(pid)
    if year is None or record is None:
        return None
    deal = asking_deal(
        record, year, price_scale(db, league_id, year), market_discount(db, league_id)
    )
    return {"salary_text": format_salary(deal.salary), "years": deal.years}


def _waiver(db, pid: str) -> dict | None:
    """He's on waivers: when he clears, who let him go, and who's claimed
    him (services/waivers.py)."""
    from src.api.services import waivers
    from src.db.repositories.waiver_repo import WaiverRepository

    w = waivers.on_waivers(db, pid)
    if not w:
        return None
    return {
        "clears_text": waivers.clears_text(w),
        "from_team_id": w["from_team_id"],
        "claimants": WaiverRepository(db).claimants(w["id"]),
    }


def _happiness(db, league_id: str, pid: str) -> dict | None:
    """His public type and mood word, what's on his mind, and (for admins)
    the numbers behind it (src/player/happiness.py)."""
    repo = HappinessRepository(db, league_id)
    pers = repo.personalities([pid]).get(pid)
    if pers is None:
        return None
    row = repo.mood(pid)
    detail = (row or {}).get("detail") or {}
    drives = detail.get("drives") or {}
    today = league_current_date(db, league_id)
    return {
        "wants_trade": pid in repo.trade_requests([pid]),
        "refusing": bool(today and pid in repo.refusing([pid], today)),
        "type": pers.type,
        "blurb": hp.TYPES.get(pers.type, {}).get("blurb", ""),
        "cares": hp.type_cares(pers.type),
        "ruiner": pers.ruiner,
        "mood": hp.mood_word(row["mood"]) if row else None,
        "lines": detail.get("lines") or [],
        "admin": {
            "mood": round(row["mood"], 2) if row else None,
            "target": round(row["target"], 2) if row else None,
            "updated_on": row["updated_on"] if row else None,
            "traits": pers.traits,
            "climate": pers.climate,
            "clubhouse": detail.get("clubhouse"),
            "coaching": detail.get("coaching"),
            "drives": [
                {
                    "drive": d,
                    "weight": pers.drives.get(d, 0),
                    "sat": drives.get(d, [None])[0],
                    "why": drives.get(d, [None, ""])[1],
                }
                for d in hp.DRIVES
            ],
        },
    }


def player_panel_data(
    db, league_id: str, pid: str, current_date: date | None
) -> dict | None:
    """Everything the slide-in player panel shows for one player."""
    player_repo = PlayerRepository(db)
    status_repo = PlayerStatusRepository(db)
    energy_repo = PlayerEnergyRepository(db, league_id)
    inj_repo = InjuryRepository(db, league_id)
    team_repo = TeamRepository(db)
    season_repo = SeasonRepository(db)
    pss_repo = PlayerSeasonStatsRepository(db)

    p = player_repo.get_with_skills(pid)
    if not p:
        return None

    status = status_repo.get_status(pid) or "unassigned"
    en = (
        energy_repo.get_with_recovery(pid, current_date, p.get("durability", 50))
        if current_date
        else energy_repo.get(pid)
    )
    inj_log = inj_repo.get_injury_log(pid)
    team = team_repo.get_for_player(pid)

    grades = player_row_to_grades(p, p, status)
    ratings = compute_ratings(p, p.get("throws", "R"))

    # Season stats — use last season with actual games so draft/offseason state
    # doesn't accidentally point at the upcoming empty season
    _last_season = season_repo.get_last_with_completed_games(league_id)
    current_season_id = _last_season["id"] if _last_season else None
    pitch_stats = None
    bat_stats = None
    if current_season_id:
        stats_row = pss_repo.get_player_season(pid, current_season_id)
        if stats_row:
            s = stats_row
            lg = advanced.LeagueRates.of(pss_repo.get_season_totals(current_season_id))
            values = sv.season_values(db, current_season_id)
            if s.get("pitch_games_played", 0) > 0:
                outs = s.get("pitch_outs", 0) or 0
                er = s.get("pitch_earned_runs", 0) or 0
                era = round(formulas.era(er, outs), 2)
                walks = s.get("pitch_walks", 0) or 0
                hits = s.get("pitch_hits", 0) or 0
                whip = round(formulas.whip(hits, walks, outs), 2)
                pitch_stats = {
                    "G": s.get("pitch_games_played", 0),
                    "GS": s.get("pitch_games_started", 0),
                    "CG": s.get("pitch_complete_games", 0),
                    "SHO": s.get("pitch_shutouts", 0),
                    "W": s.get("pitch_wins", 0),
                    "L": s.get("pitch_losses", 0),
                    "SV": s.get("pitch_saves", 0),
                    "IP": formulas.ip_str(outs),
                    "H": hits,
                    "ER": er,
                    "BB": walks,
                    "K": s.get("pitch_strike_outs", 0),
                    "ERA": era,
                    "WHIP": whip,
                }
                if lg:
                    adv = advanced.pitching(s, lg)
                    pitch_stats["FIP"] = adv["FIP"]
                    pitch_stats["ERA+"] = adv["ERA_PLUS"]
                if sv.pit_war(values, pid) is not None:
                    pitch_stats["WAR"] = sv.pit_war(values, pid)
                if advanced.win_values(s, "pitch")["WPA"] is not None:
                    pitch_stats["WPA"] = advanced.win_values(s, "pitch")["WPA"]
                if s.get("pitch_no_hitters"):
                    pitch_stats["NH"] = s["pitch_no_hitters"]
            if s.get("bat_games_played", 0) > 0:
                ab = s.get("bat_ab", 0) or 0
                hits = s.get("bat_hits", 0) or 0
                bb = s.get("bat_walks", 0) or 0
                hbp = s.get("bat_hbp", 0) or 0
                sf = s.get("bat_sac_flys", 0) or 0
                avg = round(formulas.batting_average(hits, ab), 3)
                obp = round(formulas.on_base_pct(hits, bb, hbp, ab, sf), 3)
                tb = formulas.total_bases(
                    hits,
                    s.get("bat_doubles", 0) or 0,
                    s.get("bat_triples", 0) or 0,
                    s.get("bat_home_runs", 0) or 0,
                )
                slg = round(formulas.slugging_pct(tb, ab), 3)
                bat_stats = {
                    "G": s.get("bat_games_played", 0),
                    "AB": ab,
                    "H": hits,
                    "2B": s.get("bat_doubles", 0),
                    "3B": s.get("bat_triples", 0),
                    "HR": s.get("bat_home_runs", 0),
                    "RBI": s.get("bat_rbi", 0),
                    "R": s.get("bat_runs", 0),
                    "BB": bb,
                    "K": s.get("bat_strike_outs", 0),
                    "SB": s.get("bat_stolen_bases", 0),
                    "AVG": avg,
                    "OBP": obp,
                    "SLG": slg,
                    "OPS": round(obp + slg, 3),
                }
                if lg:
                    bat_stats["wRC+"] = advanced.batting(s, lg)["wRC_PLUS"]
                if sv.bat_war(values, pid) is not None:
                    bat_stats["WAR"] = sv.bat_war(values, pid)
                if advanced.win_values(s, "bat")["WPA"] is not None:
                    bat_stats["WPA"] = advanced.win_values(s, "bat")["WPA"]

    overall_grade = player_overall_grade(status, grades, ratings)
    overall_value = player_overall_value(status, grades, ratings)

    grade_map = ratings_to_grade_map(grades, p, ratings)

    # Best defensive grade for card display
    best_def_grade = (
        role_to_grade(ratings.get("best_def"), "best_def") if ratings else "%s"
    )
    best_def_label = ratings.get("best_def_label", "DEF") if ratings else "DEF"

    energy = None
    if grades.player_type != "pitcher":
        energy = {
            "current": round(en.current_energy * 100),
            "max": round(en.max_energy * 100),
            "consecutive_days": en.consecutive_days,
            "last_game_date": en.last_game_date,
            "season_games_played": en.season_games_played,
        }
    else:
        ps_repo = PitcherStateRepository(db, league_id)
        ps = (
            ps_repo.get_with_recovery(pid, current_date, p.get("recovery", 50))
            if current_date
            else ps_repo.get(pid)
        )
        if ps:
            days_rest = (
                (current_date - ps.last_game_date).days - 1
                if current_date and ps.last_game_date
                else None
            )
            energy = {
                "current": round(ps.current_energy * 100),
                "max": round(ps.max_energy * 100),
                "consecutive_days": ps.consecutive_days,
                "last_game_date": ps.last_game_date,
                "last_pitch_count": ps.last_pitch_count,
                "season_games_played": None,
                "days_rest": days_rest,
            }

    # Injury status
    injury = inj_repo.get(pid, as_of=current_date)
    raw_injury = injury.days_remaining if injury and injury.is_active else None

    return {
        **grades.model_dump(),
        "player_id": pid,
        "team_id": team["id"] if team else None,
        "team_city": team["city"] if team else "—",
        "team_mascot": team["mascot"] if team else "",
        "jersey_number": (
            JerseyRepository(db).number_of(team["id"], pid) if team else None
        ),
        "contract": _contract(db, league_id, pid),
        "asking": _asking(db, league_id, pid) if status == "free_agent" else None,
        "waiver": _waiver(db, pid) if status == "free_agent" else None,
        "home_region": p.get("home_region"),
        "happiness": _happiness(db, league_id, pid),
        "grades": grade_map,
        "overall_grade": overall_grade,
        "overall_value": round(overall_value) if overall_value is not None else None,
        "best_def_grade": best_def_grade,
        "best_def_label": best_def_label,
        "energy": energy,
        "injury_log": inj_log,
        "pitch_stats": pitch_stats,
        "bat_stats": bat_stats,
        "injured": raw_injury is not None,
        "injury_days": raw_injury,
        "rust": rust_view(inj_repo.get_rust([pid], as_of=current_date).get(pid)),
        "injury_name": (
            injury_label(injury.injury_type)
            if raw_injury is not None and injury.injury_type
            else None
        ),
        "returning": False,
        "all_star_years": _all_star_years(db, pid),
        "awards": player_awards(db, pid),
        "hall_of_fame": hall_of_fame.badge(db, pid),
        "icon_seasons": (
            icons.find(db, [(pid, team["id"])], {pid: overall_grade}).get(
                (pid, team["id"])
            )
            if team
            else None
        ),
    }


def player_awards(db, pid: str) -> list[dict]:
    """A player's awards grouped by award, in awards.AWARDS order: icon,
    name, years, and each year's line ("2027 Atlantic"), for badges."""
    grouped: dict[str, dict] = {}
    order = {a.key: i for i, a in enumerate(awards_mod.AWARDS)}
    for r in awards_service.for_player(db, pid):
        g = grouped.setdefault(
            r["award"],
            {"key": r["award"], "icon": r["icon"], "name": r["name"], "years": []},
        )
        g["years"].append(r["year"])
    return sorted(grouped.values(), key=lambda g: order[g["key"]])


def _award_icons_by_year(awards: list[dict]) -> dict[int, str]:
    out: dict[int, str] = {}
    for a in awards:
        for y in a["years"]:
            out[y] = out.get(y, "") + a["icon"]
    return out


def _all_star_years(db, pid: str) -> list[int]:
    """The years a player was voted an All-Star."""
    return [r["year"] for r in AllStarRepository(db).seasons_for(pid)]


def player_career_data(db, league_id: str, pid: str) -> dict | None:
    """Ratings, season-by-season stats, injuries and skill history for one player."""
    player_repo = PlayerRepository(db)

    p = player_repo.get_with_skills(pid)
    if not p:
        return None

    status = PlayerStatusRepository(db).get_status(pid) or "unassigned"
    grades = player_row_to_grades(p, p, status)
    ratings = compute_ratings(p, p.get("throws", "R"))

    # Current ratings grouped into sections
    _sections = [
        (
            "Pitching",
            [
                ("strikes", "Stuff"),
                ("accuracy", "Control"),
                ("stamina", "Stamina"),
                ("recovery", "Recovery"),
                ("ground_balls", "Ground Balls"),
            ],
        ),
        (
            "Hitting",
            [
                ("contact", "Contact"),
                ("power", "Power"),
                ("eye", "Eye"),
                ("base_running", "Baserunning"),
                ("bunting", "Bunting"),
            ],
        ),
        (
            "Defense",
            [
                ("catching", "Catching"),
                ("infield", "Infield"),
                ("outfield", "Outfield"),
                ("arm", "Arm"),
            ],
        ),
        (
            "General",
            [
                ("speed", "Speed"),
                ("clutch", "Clutch"),
                ("durability", "Durability"),
            ],
        ),
    ]
    rating_sections = [
        {
            "section": section,
            "skills": [
                {"label": label, "grade": skill_to_grade(p[key])}
                for key, label in skills
                if p.get(key) is not None
            ],
        }
        for section, skills in _sections
    ]

    # Career stats — regular season + playoffs, newest first; playoffs above reg season within year
    stat_rows = player_repo.get_career_stats(pid)

    pitching_seasons = []
    batting_seasons = []
    p_totals: dict = {}
    b_totals: dict = {}
    pp_totals: dict = {}
    pb_totals: dict = {}
    pss_repo = PlayerSeasonStatsRepository(db)
    league_rates: dict[str, advanced.LeagueRates | None] = {}

    def _lg(season_id):
        if season_id not in league_rates:
            league_rates[season_id] = advanced.LeagueRates.of(
                pss_repo.get_season_totals(season_id)
            )
        return league_rates[season_id]

    def _weigh(t: dict, key: str, val, weight: int):
        """Totals of a "+" stat or FIP are its seasons, weighted by PA or outs."""
        if val is not None and weight:
            t[f"_{key}_sum"] = t.get(f"_{key}_sum", 0) + val * weight
            t[f"_{key}_w"] = t.get(f"_{key}_w", 0) + weight

    def _weighted(d: dict, key: str, ndigits: int | None):
        total, w = d.pop(f"_{key}_sum", 0), d.pop(f"_{key}_w", 0)
        return round(total / w, ndigits) if w else None

    stat_rows = [dict(x) for x in stat_rows]
    # A season's WAR goes on one row: the team he played the most for.
    war_row: dict[str, int] = {}
    for i, r in enumerate(stat_rows):
        if r.get("is_postseason"):
            continue
        played = (r.get("bat_games_played") or 0) + (r.get("pitch_games_played") or 0)
        best = war_row.get(r["season_id"])
        if best is None or played > (
            (stat_rows[best].get("bat_games_played") or 0)
            + (stat_rows[best].get("pitch_games_played") or 0)
        ):
            war_row[r["season_id"]] = i

    def _war(i: int, r: dict, side) -> float | None:
        if war_row.get(r["season_id"]) != i:
            return None
        return side(sv.season_values(db, r["season_id"]), pid)

    for i, r in enumerate(stat_rows):
        yr = r["year"]
        is_post = bool(r.get("is_postseason"))
        team = f"{r['team_city']} {r['team_mascot']}"

        if (r.get("pitch_games_played") or 0) > 0:
            outs = r.get("pitch_outs", 0) or 0
            er = r.get("pitch_earned_runs", 0) or 0
            hits = r.get("pitch_hits", 0) or 0
            bb = r.get("pitch_walks", 0) or 0
            era = round(formulas.era(er, outs), 2)
            whip = round(formulas.whip(hits, bb, outs), 2)
            prow = {
                "year": yr,
                "team": team,
                "postseason": is_post,
                "G": r.get("pitch_games_played", 0),
                "GS": r.get("pitch_games_started", 0),
                "CG": r.get("pitch_complete_games", 0),
                "SHO": r.get("pitch_shutouts", 0),
                "NH": r.get("pitch_no_hitters", 0),
                "W": r.get("pitch_wins", 0),
                "L": r.get("pitch_losses", 0),
                "SV": r.get("pitch_saves", 0),
                "IP": formulas.ip_str(outs),
                "H": hits,
                "ER": er,
                "BB": bb,
                "K": r.get("pitch_strike_outs", 0),
                "HR": r.get("pitch_home_runs", 0),
                "ERA": era,
                "WHIP": whip,
            }
            adv = advanced.pitching(r, _lg(r["season_id"]))
            prow["FIP"] = adv["FIP"]
            prow["ERA+"] = adv["ERA_PLUS"]
            prow["WAR"] = _war(i, r, sv.pit_war)
            prow["WPA"] = advanced.win_values(r, "pitch")["WPA"]
            pitching_seasons.append(prow)
            t = p_totals if not is_post else pp_totals
            for k in (
                "G",
                "GS",
                "CG",
                "SHO",
                "NH",
                "W",
                "L",
                "SV",
                "H",
                "ER",
                "BB",
                "K",
                "HR",
            ):
                t[k] = t.get(k, 0) + prow[k]
            t["_outs"] = t.get("_outs", 0) + outs
            _weigh(t, "FIP", prow["FIP"], outs)
            _weigh(t, "ERA+", prow["ERA+"], outs)
            if prow["WAR"] is not None:
                t["_war"] = t.get("_war", 0.0) + prow["WAR"]
            if prow["WPA"] is not None:
                t["_wpa"] = t.get("_wpa", 0.0) + prow["WPA"]

        if (r.get("bat_games_played") or 0) > 0:
            ab = r.get("bat_ab", 0) or 0
            h = r.get("bat_hits", 0) or 0
            bb = r.get("bat_walks", 0) or 0
            hbp = r.get("bat_hbp", 0) or 0
            sf = r.get("bat_sac_flys", 0) or 0
            dbl = r.get("bat_doubles", 0) or 0
            trp = r.get("bat_triples", 0) or 0
            hr = r.get("bat_home_runs", 0) or 0
            slg_num = formulas.total_bases(h, dbl, trp, hr)
            obp = formulas.on_base_pct(h, bb, hbp, ab, sf)
            slg = formulas.slugging_pct(slg_num, ab)
            brow = {
                "year": yr,
                "team": team,
                "postseason": is_post,
                "G": r.get("bat_games_played", 0),
                "AB": ab,
                "H": h,
                "2B": dbl,
                "3B": trp,
                "HR": hr,
                "RBI": r.get("bat_rbi", 0) or 0,
                "R": r.get("bat_runs", 0) or 0,
                "BB": bb,
                "K": r.get("bat_strike_outs", 0) or 0,
                "SB": r.get("bat_stolen_bases", 0) or 0,
                "AVG": round(formulas.batting_average(h, ab), 3),
                "OBP": round(obp, 3),
                "SLG": round(slg, 3),
                "OPS": round(obp + slg, 3),
            }
            adv = advanced.batting(r, _lg(r["season_id"]))
            brow["wRC+"] = adv["wRC_PLUS"]
            brow["OPS+"] = adv["OPS_PLUS"]
            brow["WAR"] = _war(i, r, sv.bat_war)
            brow["WPA"] = advanced.win_values(r, "bat")["WPA"]
            batting_seasons.append(brow)
            t = b_totals if not is_post else pb_totals
            for k in (
                "G",
                "AB",
                "H",
                "2B",
                "3B",
                "HR",
                "RBI",
                "R",
                "BB",
                "K",
                "SB",
            ):
                t[k] = t.get(k, 0) + brow[k]
            t["_ab"] = t.get("_ab", 0) + ab
            t["_h"] = t.get("_h", 0) + h
            t["_bb"] = t.get("_bb", 0) + bb
            t["_hbp"] = t.get("_hbp", 0) + hbp
            t["_sf"] = t.get("_sf", 0) + sf
            t["_slg_num"] = t.get("_slg_num", 0) + slg_num
            _weigh(t, "wRC+", brow["wRC+"], advanced.pa(r))
            _weigh(t, "OPS+", brow["OPS+"], advanced.pa(r))
            if brow["WAR"] is not None:
                t["_war"] = t.get("_war", 0.0) + brow["WAR"]
            if brow["WPA"] is not None:
                t["_wpa"] = t.get("_wpa", 0.0) + brow["WPA"]

    def _pitch_totals(d: dict) -> dict | None:
        if not d:
            return None
        outs = d.pop("_outs", 0)
        fip = _weighted(d, "FIP", 2)
        era_plus = _weighted(d, "ERA+", 0)
        war = d.pop("_war", None)
        wpa = d.pop("_wpa", None)
        return {
            "WAR": round(war, 1) if war is not None else None,
            "WPA": round(wpa, 2) if wpa is not None else None,
            **d,
            "FIP": fip,
            "ERA+": int(era_plus) if era_plus is not None else None,
            "IP": formulas.ip_str(outs),
            "ERA": round(formulas.era(d.get("ER", 0), outs), 2),
            "WHIP": round(formulas.whip(d.get("H", 0), d.get("BB", 0), outs), 2),
        }

    def _bat_totals(d: dict) -> dict | None:
        if not d:
            return None
        ab = d.pop("_ab", 0)
        h = d.pop("_h", 0)
        bb = d.pop("_bb", 0)
        hbp = d.pop("_hbp", 0)
        sf = d.pop("_sf", 0)
        slg_num = d.pop("_slg_num", 0)
        obp = formulas.on_base_pct(h, bb, hbp, ab, sf)
        slg = formulas.slugging_pct(slg_num, ab)
        wrc_plus = _weighted(d, "wRC+", 0)
        ops_plus = _weighted(d, "OPS+", 0)
        war = d.pop("_war", None)
        wpa = d.pop("_wpa", None)
        return {
            "WAR": round(war, 1) if war is not None else None,
            "WPA": round(wpa, 2) if wpa is not None else None,
            **d,
            "wRC+": int(wrc_plus) if wrc_plus is not None else None,
            "OPS+": int(ops_plus) if ops_plus is not None else None,
            "AVG": round(formulas.batting_average(h, ab), 3),
            "OBP": round(obp, 3),
            "SLG": round(slg, 3),
            "OPS": round(obp + slg, 3),
        }

    pitching_totals = _pitch_totals(p_totals)
    pitching_playoff_totals = _pitch_totals(pp_totals)
    batting_totals = _bat_totals(b_totals)
    batting_playoff_totals = _bat_totals(pb_totals)

    # Injuries grouped by season year
    inj_repo = InjuryRepository(db, league_id)
    all_inj = inj_repo.get_injuries_by_year(pid)
    injuries_by_year: dict[str, list] = {}
    for r in all_inj:
        yr = str(r["season_year"]) if r["season_year"] else "Pre-season"
        injuries_by_year.setdefault(yr, []).append(dict(r))

    # Skills history by season
    skills_history = player_repo.get_skills_history(pid)
    _skill_cols = [
        "durability",
        "clutch",
        "speed",
        "power",
        "eye",
        "contact",
        "base_running",
        "bunting",
        "catching",
        "infield",
        "outfield",
        "arm",
        "accuracy",
        "stamina",
        "recovery",
        "ground_balls",
        "strikes",
    ]
    skills_history = [
        {
            **{k: v for k, v in dict(r).items() if k not in _skill_cols},
            **{k: skill_to_grade(r[k]) for k in _skill_cols},
        }
        for r in skills_history
    ]

    overall_grade = player_overall_grade(status, grades, ratings)
    award_list = player_awards(db, pid)

    return {
        **grades.model_dump(),
        "player_id": pid,
        "overall_grade": overall_grade,
        "rating_sections": rating_sections,
        "pitching_seasons": pitching_seasons,
        "pitching_totals": pitching_totals,
        "pitching_playoff_totals": pitching_playoff_totals,
        "batting_seasons": batting_seasons,
        "batting_totals": batting_totals,
        "batting_playoff_totals": batting_playoff_totals,
        "injuries_by_year": injuries_by_year,
        "skills_history": skills_history,
        "all_star_years": _all_star_years(db, pid),
        "awards": award_list,
        "hall_of_fame": hall_of_fame.badge(db, pid),
        "award_icons": _award_icons_by_year(award_list),
        "all_star_games": [
            {**r, "summary": all_star.line_text(r)}
            for r in AllStarRepository(db).career_lines(pid)
        ],
        "hr_derbies": hr_derby.career(db, pid),
        "rookie_games": [
            {**r, "summary": all_star.line_text(r)} for r in rookie_game.career(db, pid)
        ],
    }
