# src/api/view_models/player_cards.py
#
# Player ratings and the grade dicts behind the player cards on the draft,
# roster and lineup pages.

from __future__ import annotations

import logging

from src.player.skill_map import SKILL_ABBREVIATIONS
from src.player.injury_types import injury_label
from src.api.grade_curves import overall_score, overall_to_grade, role_to_grade
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
    except ValueError:
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


# Statuses graded on the prospect rating and curve. Free agents are pros, so
# they are graded on the pro scale like rostered players.
PROSPECT_STATUSES = ("prospect", "unassigned")


def overall_value(status: str, grades, ratings: dict) -> float | None:
    """The number behind overall_grade, or None when it falls back to
    grades.overall."""
    if not ratings:
        return None
    if status in PROSPECT_STATUSES:
        return ratings.get("prospect")
    if grades.player_type == "pitcher":
        # Pitchers: best of SP/RP rating — overall_player is offense-based and useless
        return max(ratings.get("sp", 0), ratings.get("rp", 0)) or None
    return ratings.get("overall_player")


def overall_kind(status: str, grades) -> str:
    """Which curve overall_value is graded on (src/api/grade_curves.py)."""
    if status in PROSPECT_STATUSES:
        return "prospect"
    return "pitcher" if grades.player_type == "pitcher" else "hitter"


def overall_grade(status: str, grades, ratings: dict) -> str:
    """Prospect rating for undrafted players, position-aware rating for rostered."""
    value = overall_value(status, grades, ratings)
    if value is None:
        return grades.overall
    return overall_to_grade(value, overall_kind(status, grades))


# grade_map keys graded from compute_ratings; the rest are raw skills.
_RATING_KEYS = {
    "sp",
    "rp",
    "cp",
    "lead_off",
    "power_hitter",
    "contact_hitter",
    "overall_offense",
    "c",
    "1b",
    "2b",
    "3b",
    "ss",
    "lf",
    "cf",
    "rf",
}


def ratings_to_grade_map(grades, skills: dict, ratings: dict) -> list:
    """
    Build the section-based grade_map for the player detail panel.
    Pitchers:  Pitching / General / Defense / Hitting
    Hitters:   Hitting  / General / Defense / Pitching
    Sections a player is rarely used for carry off_role=True (General, Defense
    and Hitting for pitchers; Pitching for hitters).
    Pitching and Hitting also carry "roles": the composite ratings (SP/RP/CP,
    leadoff/contact/power hitter), shown under their own subheading.
    Ratings-based entries use role_to_grade (curved per role).
    """
    g = skill_to_grade  # shorthand

    def rg(key: str) -> str:
        return role_to_grade(ratings.get(key), key)

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
        ],
        "roles": [
            {"key": "sp", "label": "Starter", "grade": rg("sp")},
            {"key": "rp", "label": "Reliever", "grade": rg("rp")},
            {"key": "cp", "label": "Closer", "grade": rg("cp")},
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
        ],
        "roles": [
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
            {
                "key": "overall_offense",
                "label": "Off. rating",
                "grade": rg("overall_offense"),
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
        ],
    }

    # The number behind each grade, shown only to admins.
    for section in (
        pitching_section,
        hitting_section,
        defense_section,
        general_section,
    ):
        for skill in section["skills"] + section.get("roles", []):
            source = ratings if skill["key"] in _RATING_KEYS else skills
            value = (source or {}).get(skill["key"])
            skill["value"] = round(value) if value is not None else None

    # Off-role sections are what the player is rarely used for: the panel
    # tucks them behind a toggle.
    if grades.player_type == "pitcher":
        # General stays open: a pitcher's durability sets his injury risk.
        on_role = [pitching_section, general_section]
        off_role = [defense_section, hitting_section]
    else:
        on_role = [hitting_section, general_section, defense_section]
        off_role = [pitching_section]
    for section in on_role:
        section["off_role"] = False
    for section in off_role:
        section["off_role"] = True
    return on_role + off_role


# ── Card dicts ────────────────────────────────────────────────────────────────


def _role_grades(g: dict, ratings: dict) -> None:
    """The role and per-position grades the lineup and draft lists sort by:
    SP, RP and CP (closer) for pitchers, hitter roles and positions for
    everyone else."""
    if g.get("player_type") == "pitcher":
        g["sp_grade"] = role_to_grade(ratings.get("sp", 0), "sp")
        g["rp_grade"] = role_to_grade(ratings.get("rp", 0), "rp")
        g["cp_grade"] = role_to_grade(ratings.get("cp", 0), "cp")
    else:
        g["leadoff_grade"] = role_to_grade(ratings.get("lead_off", 0), "lead_off")
        g["power_h_grade"] = role_to_grade(
            ratings.get("power_hitter", 0), "power_hitter"
        )
        g["contact_h_grade"] = role_to_grade(
            ratings.get("contact_hitter", 0), "contact_hitter"
        )
        g["offense_h_grade"] = role_to_grade(
            ratings.get("overall_offense", 0), "overall_offense"
        )
    for pos in ("c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "of", "if", "dh"):
        g[f"pos_{pos}"] = role_to_grade(ratings.get(pos, 0), pos)


def prospect_card(row: dict, skills: dict) -> dict:
    """A draft-board card. Prospects use the prospect rating for overall."""
    grades = player_row_to_grades(dict(row), skills, row["status"])
    ratings = compute_ratings(skills, dict(row).get("throws", "R"))
    g = grades.model_dump()
    if ratings:
        g["overall"] = overall_to_grade(ratings.get("prospect"), "prospect")
        g["best_def_grade"] = role_to_grade(ratings.get("best_def"), "best_def")
        g["best_def_label"] = ratings.get("best_def_label", "DEF")
        _role_grades(g, ratings)
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
            g["overall"] = (
                overall_to_grade(best_p, "pitcher") if best_p else g["overall"]
            )
            g["overall_score"] = overall_score(best_p or None, "pitcher")
            g["sp_grade"] = role_to_grade(ratings.get("sp", 0), "sp")
            g["rp_grade"] = role_to_grade(ratings.get("rp", 0), "rp")
        else:
            g["overall"] = overall_to_grade(ratings.get("overall_player"), "hitter")
            g["overall_score"] = overall_score(ratings.get("overall_player"), "hitter")
        g["best_def_grade"] = role_to_grade(ratings.get("best_def"), "best_def")
        g["best_def_label"] = ratings.get("best_def_label", "DEF")
        g["if_grade"] = role_to_grade(ratings.get("if", 0), "if")
        g["of_grade"] = role_to_grade(ratings.get("of", 0), "of")
        g["c_grade"] = role_to_grade(ratings.get("c", 0), "c")
        g["b1_grade"] = role_to_grade(ratings.get("1b", 0), "1b")
        # Per-position grades for the fielding line, as on the Lineup tab
        for pos in ("c", "1b", "2b", "3b", "ss", "lf", "cf", "rf"):
            g[f"pos_{pos}"] = role_to_grade(ratings.get(pos, 0), pos)
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
            g["overall"] = (
                overall_to_grade(best_p, "pitcher") if best_p else g["overall"]
            )
            g["bat_overall"] = overall_to_grade(ratings.get("overall_player"), "hitter")
        else:
            g["overall"] = overall_to_grade(ratings.get("overall_player"), "hitter")
            g["bat_overall"] = g["overall"]
        g["best_def_grade"] = role_to_grade(ratings.get("best_def"), "best_def")
        g["best_def_label"] = ratings.get("best_def_label", "DEF")
        # Per-position ratings also drive the assigned-position display
        _role_grades(g, ratings)
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
            p["stat_avg"] = f"{s['bat_hits'] / ab:.3f}" if ab else None
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


# Hover names for skills the game shows under another word (as in news).
_RUST_WORDS = {"strikes": "stuff", "accuracy": "control"}


def rust_view(rust: dict | None) -> dict | None:
    """A player's rust for display, or None when there's none:
    {"text": "SP −4 · BR −2", "tip": "Speed (SP) is down 4 and Base
    running (BR) is down 2.", "days": days until it's gone if he plays
    every day}. The badge shows text; the hover spells it out with tip."""
    if not rust:
        return None
    parts = [
        (k, SKILL_ABBREVIATIONS.get(k, k.upper()), round(v))
        for k, v in sorted(rust["skills"].items(), key=lambda kv: -kv[1])
        if round(v) >= 1
    ]
    if not parts:
        return None
    phrases = [
        f"{_RUST_WORDS.get(k, k.replace('_', ' ')).capitalize()} ({abbr}) is down {n}"
        for k, abbr, n in parts
    ]
    if len(phrases) > 1:
        phrases = [", ".join(phrases[:-1]) + " and " + phrases[-1]]
    return {
        "text": " · ".join(f"{abbr} −{n}" for _, abbr, n in parts),
        "tip": phrases[0] + ".",
        "days": rust["days_left"],
    }


def attach_moods(db, league_id: str, players: list[dict]) -> None:
    """Mark the players who are unhappy or worse, have asked for a trade,
    or are sitting out (src/player/happiness.py): p["mood_badge"]."""
    from src.api.view_models.player_detail import league_current_date
    from src.db.repositories.happiness_repo import HappinessRepository

    ids = [p["player_id"] for p in players if p.get("player_id")]
    badges = HappinessRepository(db, league_id).badges(
        ids, league_current_date(db, league_id)
    )
    for p in players:
        b = badges.get(p.get("player_id"))
        if b:
            p["mood_badge"] = b


def attach_injuries(
    players: list[dict],
    injured_map: dict,
    injury_types: dict | None = None,
    rust: dict | None = None,
) -> None:
    """Mark each card with its IL status from a {player_id: days_remaining} map,
    the injury's name from a {player_id: injury_type} map, and any rust left
    from a {player_id: rust} map (InjuryRepository.get_rust)."""
    injury_types = injury_types or {}
    rust = rust or {}
    for p in players:
        p["rust"] = rust_view(rust.get(p["player_id"]))
        raw_days = injured_map.get(p["player_id"])
        p["injured"] = raw_days is not None
        p["injury_days"] = raw_days if raw_days else None
        kind = injury_types.get(p["player_id"]) if raw_days is not None else None
        p["injury_name"] = injury_label(kind) if kind else None
        p["returning"] = False
