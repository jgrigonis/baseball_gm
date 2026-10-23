# src/api/view_models/player_cards.py
#
# Player ratings and the grade dicts behind the player cards on the draft,
# roster and lineup pages.

from __future__ import annotations

import logging

from src.api.schemas import player_row_to_grades, skill_to_grade
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_skills import PlayerSkills
from src.stats import formulas

logger = logging.getLogger(__name__)


def compute_ratings(skills: dict, throws: str) -> dict:
    """
    Run PlayerEvaluator on a raw skills dict.
    Returns the full ratings map plus derived composites:
      if_rating   = max(2b, 3b, ss)
      of_rating   = max(lf, cf, rf)
      best_def    = max(if, of, c, 1b)
      best_def_label = "IF" | "OF" | "CA" | "1B"
    """
    try:
        ps = PlayerSkills(skills)
        ratings = PlayerEvaluator.rate_player(ps, throws or "R")
    except Exception:
        logger.exception(
            "Failed to evaluate player skills: skills=%s throws=%s", skills, throws
        )
        return {}

    if_rating = max(ratings.get("2b", 0), ratings.get("3b", 0), ratings.get("ss", 0))
    of_rating = max(ratings.get("lf", 0), ratings.get("cf", 0), ratings.get("rf", 0))
    groups = {
        "IF": if_rating,
        "OF": of_rating,
        "CA": ratings.get("c", 0),
        "1B": ratings.get("1b", 0),
    }

    best_def_label = max(groups, key=groups.get)
    best_def = groups[best_def_label]

    ratings["if"] = if_rating
    ratings["of"] = of_rating
    ratings["best_def"] = best_def
    ratings["best_def_label"] = best_def_label
    return ratings


def overall_grade(status: str, grades, ratings: dict) -> str:
    """Prospect rating for undrafted players, position-aware rating for rostered."""
    if status in ("prospect", "unassigned", "free_agent"):
        return skill_to_grade(ratings.get("prospect")) if ratings else grades.overall
    if grades.player_type == "pitcher":
        # Pitchers: best of SP/RP rating — overall_player is offense-based and useless
        best_p = max(ratings.get("sp", 0), ratings.get("rp", 0)) if ratings else 0
        return skill_to_grade(best_p) if best_p else grades.overall
    return skill_to_grade(ratings.get("overall_player")) if ratings else grades.overall


def ratings_to_grade_map(grades, skills: dict, ratings: dict) -> list:
    """
    Build the section-based grade_map for the player detail panel.
    Pitchers:  Pitching / General / Defense / Hitting
    Hitters:   Hitting  / General / Defense / Pitching
    Ratings-based entries use skill_to_grade(rating_value).
    """
    g = skill_to_grade  # shorthand

    def rg(key: str) -> str:
        return g(ratings.get(key))

    pitching_section = {
        "section": "Pitching",
        "skills": [
            {
                "key": "strikes",
                "label": "Stuff",
                "grade": grades.stuff or g(skills.get("strikes")),
            },
            {
                "key": "accuracy",
                "label": "Control",
                "grade": grades.control or g(skills.get("accuracy")),
            },
            {
                "key": "stamina",
                "label": "Stamina",
                "grade": grades.stamina or g(skills.get("stamina")),
            },
            {
                "key": "recovery",
                "label": "Recovery",
                "grade": grades.recovery or g(skills.get("recovery")),
            },
            {
                "key": "ground_balls",
                "label": "GB tendency",
                "grade": g(skills.get("ground_balls")),
            },
            {"key": "sp", "label": "SP rating", "grade": rg("sp")},
            {"key": "rp", "label": "RP rating", "grade": rg("rp")},
        ],
    }

    hitting_section = {
        "section": "Hitting",
        "skills": [
            {
                "key": "contact",
                "label": "Contact",
                "grade": grades.contact or g(skills.get("contact")),
            },
            {
                "key": "power",
                "label": "Power",
                "grade": grades.power or g(skills.get("power")),
            },
            {"key": "eye", "label": "Eye", "grade": grades.eye or g(skills.get("eye"))},
            {
                "key": "speed",
                "label": "Speed",
                "grade": grades.speed or g(skills.get("speed")),
            },
            {
                "key": "base_running",
                "label": "Baserunning",
                "grade": g(skills.get("base_running")),
            },
            {"key": "bunting", "label": "Bunting", "grade": g(skills.get("bunting"))},
            {"key": "lead_off", "label": "Leadoff", "grade": rg("lead_off")},
            {
                "key": "power_hitter",
                "label": "Power hitter",
                "grade": rg("power_hitter"),
            },
            {
                "key": "contact_hitter",
                "label": "Contact hitter",
                "grade": rg("contact_hitter"),
            },
        ],
    }

    defense_section = {
        "section": "Defense",
        "skills": [
            {"key": "c", "label": "Catcher", "grade": rg("c")},
            {"key": "1b", "label": "First Base", "grade": rg("1b")},
            {"key": "2b", "label": "Second Base", "grade": rg("2b")},
            {"key": "3b", "label": "Third Base", "grade": rg("3b")},
            {"key": "ss", "label": "Shortstop", "grade": rg("ss")},
            {"key": "lf", "label": "Left Field", "grade": rg("lf")},
            {"key": "cf", "label": "Center Field", "grade": rg("cf")},
            {"key": "rf", "label": "Right Field", "grade": rg("rf")},
            {"key": "arm", "label": "Arm", "grade": grades.arm or g(skills.get("arm"))},
        ],
    }

    general_section = {
        "section": "General",
        "skills": [
            {"key": "clutch", "label": "Clutch", "grade": g(skills.get("clutch"))},
            {
                "key": "durability",
                "label": "Durability",
                "grade": g(skills.get("durability")),
            },
            {
                "key": "overall_offense",
                "label": "Off. rating",
                "grade": rg("overall_offense"),
            },
        ],
    }

    if grades.player_type == "pitcher":
        return [pitching_section, general_section, defense_section, hitting_section]
    else:
        return [hitting_section, general_section, defense_section, pitching_section]


# ── Card dicts ────────────────────────────────────────────────────────────────


def prospect_card(row: dict, skills: dict) -> dict:
    """A draft-board card. Prospects use the prospect rating for overall."""
    grades = player_row_to_grades(dict(row), skills, row["status"])
    ratings = compute_ratings(skills, dict(row).get("throws", "R"))
    g = grades.model_dump()
    if ratings:
        g["overall"] = skill_to_grade(ratings.get("prospect"))
        g["best_def_grade"] = skill_to_grade(ratings.get("best_def"))
        g["best_def_label"] = ratings.get("best_def_label", "DEF")
    if g.get("player_type") == "pitcher":
        g["ground_balls"] = skill_to_grade(skills.get("ground_balls"))
    return g


def draft_roster_card(row: dict, skills: dict) -> dict:
    """A card for the GM's current roster in the draft page's right-hand column."""
    d = dict(row)
    grades = player_row_to_grades(d, skills, d["status"])
    ratings = compute_ratings(skills, d.get("throws", "R"))
    g = grades.model_dump()
    if ratings:
        if g.get("player_type") == "pitcher":
            best_p = max(ratings.get("sp", 0), ratings.get("rp", 0))
            g["overall"] = skill_to_grade(best_p) if best_p else g["overall"]
        else:
            g["overall"] = skill_to_grade(ratings.get("overall_player"))
        g["best_def_grade"] = skill_to_grade(ratings.get("best_def"))
        g["best_def_label"] = ratings.get("best_def_label", "DEF")
    if g.get("player_type") == "pitcher":
        g["ground_balls"] = skill_to_grade(skills.get("ground_balls"))
    return g


def roster_card(d: dict) -> dict:
    """A roster-page card. `d` is a roster row with the skills batched in."""
    grades = player_row_to_grades(d, d, d["status"])
    ratings = compute_ratings(d, d.get("throws", "R"))
    g = grades.model_dump()
    if ratings:
        if g.get("player_type") == "pitcher":
            best_p = max(ratings.get("sp", 0), ratings.get("rp", 0))
            g["overall"] = skill_to_grade(best_p) if best_p else g["overall"]
            g["sp_grade"] = skill_to_grade(ratings.get("sp", 0))
            g["rp_grade"] = skill_to_grade(ratings.get("rp", 0))
        else:
            g["overall"] = skill_to_grade(ratings.get("overall_player"))
        g["best_def_grade"] = skill_to_grade(ratings.get("best_def"))
        g["best_def_label"] = ratings.get("best_def_label", "DEF")
        g["if_grade"] = skill_to_grade(ratings.get("if", 0))
        g["of_grade"] = skill_to_grade(ratings.get("of", 0))
        g["c_grade"] = skill_to_grade(ratings.get("c", 0))
        g["b1_grade"] = skill_to_grade(ratings.get("1b", 0))
    g["base_running"] = skill_to_grade(d.get("base_running"))
    g["bunting"] = skill_to_grade(d.get("bunting"))
    g["ground_balls"] = skill_to_grade(d.get("ground_balls"))
    return g


def lineup_card(d: dict) -> dict:
    """A lineup-page card, with per-position grades and hitting grades for
    pitchers too (they need them when batting)."""
    grades = player_row_to_grades(d, d, d["status"])
    ratings = compute_ratings(d, d.get("throws", "R"))
    g = grades.model_dump()
    if ratings:
        if g.get("player_type") == "pitcher":
            best_p = max(ratings.get("sp", 0), ratings.get("rp", 0))
            g["overall"] = skill_to_grade(best_p) if best_p else g["overall"]
            g["sp_grade"] = skill_to_grade(ratings.get("sp", 0))
            g["rp_grade"] = skill_to_grade(ratings.get("rp", 0))
            g["bat_overall"] = skill_to_grade(ratings.get("overall_player"))
        else:
            g["overall"] = skill_to_grade(ratings.get("overall_player"))
            g["leadoff_grade"] = skill_to_grade(ratings.get("lead_off", 0))
            g["power_h_grade"] = skill_to_grade(ratings.get("power_hitter", 0))
            g["contact_h_grade"] = skill_to_grade(ratings.get("contact_hitter", 0))
            g["oofense_h_grade"] = skill_to_grade(ratings.get("offense", 0))
            g["bat_overall"] = g["overall"]
        g["best_def_grade"] = skill_to_grade(ratings.get("best_def"))
        g["best_def_label"] = ratings.get("best_def_label", "DEF")
        # Per-position ratings for assigned-position display
        for pos in ("c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "of", "if", "dh"):
            g[f"pos_{pos}"] = skill_to_grade(ratings.get(pos, 0))
    # Raw skill grades not in PlayerGrades — needed for sort and batting display
    g["base_running"] = skill_to_grade(d.get("base_running"))
    g["bunting"] = skill_to_grade(d.get("bunting"))
    g["ground_balls"] = skill_to_grade(d.get("ground_balls"))
    # Hitting grades for all players — pitchers need these when batting
    for key in ("contact", "power", "eye", "speed", "arm"):
        if g.get(key) is None:
            g[key] = skill_to_grade(d.get(key))
    return g


def attach_roster_stats(players: list[dict], stats_map: dict) -> None:
    """Add the season stat line shown on each roster card."""
    for p in players:
        s = stats_map.get(p["player_id"])
        if s and p.get("player_type") != "pitcher":
            ab = s["bat_ab"] or 0
            p["stat_g"] = s["bat_games_played"] or 0
            p["stat_avg"] = f"{s['bat_hits']/ab:.3f}" if ab else None
            p["stat_hr"] = s["bat_home_runs"] or 0
            p["stat_rbi"] = s["bat_rbi"] or 0
        elif s and p.get("player_type") == "pitcher":
            outs = s["pitch_outs"] or 0
            p["stat_gs"] = s["pitch_games_started"] or 0
            p["stat_ip"] = formulas.ip_str(outs) if outs else None
            p["stat_era"] = (
                f"{formulas.era(s['pitch_earned_runs'], outs):.2f}" if outs else None
            )
            p["stat_w"] = s["pitch_wins"] or 0
            p["stat_l"] = s["pitch_losses"] or 0
            p["stat_sv"] = s["pitch_saves"] or 0


def attach_injuries(players: list[dict], injured_map: dict) -> None:
    """Mark each card with its IL status from a {player_id: days_remaining} map."""
    for p in players:
        raw_days = injured_map.get(p["player_id"])
        p["injured"] = raw_days is not None
        p["injury_days"] = raw_days if raw_days else None
        p["returning"] = False
