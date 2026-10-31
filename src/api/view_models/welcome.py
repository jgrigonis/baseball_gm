# src/api/view_models/welcome.py
#
# The welcome screen a GM sees once when their league starts, before the
# draft (plans/welcome-screen.md): their team's colors, how the
# roster stacks up against the league, its stars and weak spots, its ages,
# the GM's draft slot, opening day and the other GMs.

from __future__ import annotations

import hashlib

from src.api.schemas import skill_to_grade
from src.api.services.draft_needs import needs_for_draft
from src.api.view_models.draft import last_season
from src.api.view_models.league_info import league_gms
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.series_repo import SeriesRepository
from src.db.repositories.team_repo import TeamRepository
from src.league.offseason.draft_strategy import CHIPS, ratings
from src.player.player_record import PlayerRecord
from src.player.player_value import role_rating
from src.team.colors import colors_for

MAJORS = ("26man", "40man")
STARS = 5  # best players shown under Your stars

# area key, label, what it's ranked on
AREAS = (
    ("lineup", "Lineup", "top 9 hitters' overall offense"),
    ("rotation", "Rotation", "top 5 starters"),
    ("bullpen", "Bullpen", "top 7 relievers"),
    ("defense", "Defense", "top 9 hitters' best position"),
)

HITTER_SKILLS = (
    ("contact", "Contact"),
    ("power", "Power"),
    ("eye", "Eye"),
    ("speed", "Speed"),
    ("arm", "Arm"),
)
PITCHER_SKILLS = (
    ("strikes", "Stuff"),
    ("accuracy", "Control"),
    ("stamina", "Stamina"),
    ("ground_balls", "Ground balls"),
)

LEVELS = {0: "Low", 1: "Med", 2: "High"}

TAGLINES = (
    "{city} has waited all winter for this.",
    "A new era of {mascot} baseball starts now.",
    "The {mascot} are yours. Make {city} proud.",
    "Every dynasty starts with a first season.",
    "{city} is ready. Are the {mascot}?",
)


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _avg_top(values: list[int], n: int) -> float:
    top = sorted(values, reverse=True)[:n]
    return sum(top) / len(top) if top else 0.0


def area_scores(players: list[tuple[PlayerRecord, dict]]) -> dict[str, float]:
    """The team's average rating in each area, from its major league roster."""
    hitters = [(p, r) for p, r in players if not p.is_pitcher()]
    best_hitters = sorted(hitters, key=lambda x: x[1]["overall_player"], reverse=True)
    pitchers = [(p, r) for p, r in players if p.is_pitcher()]
    return {
        "lineup": _avg_top([r["overall_offense"] for _, r in hitters], 9),
        "rotation": _avg_top([r["sp"] for p, r in pitchers if p.position == "sp"], 5),
        "bullpen": _avg_top([r["rp"] for p, r in pitchers if p.position != "sp"], 7),
        "defense": _avg_top([r["defensive_value"] for _, r in best_hitters[:9]], 9),
    }


def scouting_report(team_id: str, scores: dict[str, dict[str, float]]) -> dict:
    """Where the team ranks in each area (1 = best), and a sentence on it."""
    n = len(scores)
    mine = scores[team_id]
    areas = []
    for key, label, basis in AREAS:
        value = mine[key]
        rank = 1 + sum(1 for s in scores.values() if s[key] > value)
        areas.append(
            {
                "key": key,
                "label": label,
                "basis": basis,
                "rank": rank,
                "rank_text": f"{ordinal(rank)} of {n}",
                "grade": skill_to_grade(round(value)),
                # Bars run from the league's worst (short) to its best (full).
                "bar": 100 if n == 1 else round(100 - 85 * (rank - 1) / (n - 1)),
            }
        )
    return {"areas": areas, "verdict": verdict(areas, n)}


def verdict(areas: list[dict], n: int) -> str:
    best = min(areas, key=lambda a: a["rank"])
    worst = max(areas, key=lambda a: a["rank"])
    top, bottom = n / 3, n - n / 3
    if n < 3 or best["rank"] == worst["rank"]:
        return "A balanced club, with no area far ahead of the others."
    if worst["rank"] <= top:
        return "A contender on paper: top third of the league everywhere."
    if best["rank"] > bottom:
        return "A long climb ahead: bottom third of the league everywhere."
    line = f"Built around its {best['label'].lower()} ({best['rank_text']})"
    if worst["rank"] > bottom:
        return f"{line}, but the {worst['label'].lower()} ({worst['rank_text']}) needs help."
    return f"{line}, with the {worst['label'].lower()} ({worst['rank_text']}) its weakest area."


def favorites(team_id: str, scores: dict, gms: list[dict], n: int = 3) -> list[dict]:
    """The other teams with the best rosters on paper, with their GMs."""
    by_team = {g["team_id"]: g for g in gms}
    strength = {
        tid: sum(s.values()) / len(s) for tid, s in scores.items() if tid != team_id
    }
    best = sorted(strength, key=strength.get, reverse=True)
    return [by_team[tid] for tid in best if tid in by_team][:n]


def star_card(p: PlayerRecord, r: dict) -> dict:
    skills = PITCHER_SKILLS if p.is_pitcher() else HITTER_SKILLS
    top = sorted(skills, key=lambda s: p.skills[s[0]], reverse=True)[:2]
    return {
        "player_id": p.id,
        "name": f"{p.first_name} {p.last_name}",
        "position": p.position.upper(),
        "age": p.age,
        "grade": skill_to_grade(role_rating(p)),
        "skills": [(label, skill_to_grade(p.skills[k])) for k, label in top],
    }


def age_profile(players: list[PlayerRecord]) -> dict | None:
    if not players:
        return None
    ages = sorted(players, key=lambda p: p.age)
    groups = [
        ("Rising", "25 and under", sum(1 for p in players if p.age <= 25)),
        ("Prime", "26 to 30", sum(1 for p in players if 26 <= p.age <= 30)),
        ("Veterans", "31 and over", sum(1 for p in players if p.age >= 31)),
    ]
    biggest = max(groups, key=lambda g: g[2])[0]
    outlook = {
        "Rising": "A young roster: it should get better as it grows up.",
        "Prime": "Most of the roster is in its prime: built to win now.",
        "Veterans": "A veteran roster: win now, before age catches up.",
    }[biggest]
    youngest, oldest = ages[0], ages[-1]
    return {
        "average": round(sum(p.age for p in players) / len(players), 1),
        "youngest": _named(youngest),
        "oldest": _named(oldest),
        "groups": [
            {
                "label": label,
                "range": span,
                "count": count,
                "share": round(100 * count / len(players)),
            }
            for label, span, count in groups
        ],
        "outlook": outlook,
    }


def _named(p: PlayerRecord) -> dict:
    return {"player_id": p.id, "name": f"{p.first_name} {p.last_name}", "age": p.age}


def team_colors(city: str, mascot: str) -> dict:
    c = colors_for(city, mascot)
    return {
        "code": c.code,
        "primary": c.primary,
        "secondary": c.secondary,
        "accent": c.accent,
        "ink": c.ink,
        "tagline": TAGLINES[
            hashlib.sha1(f"{city} {mascot}".encode()).digest()[0] % len(TAGLINES)
        ].format(city=city, mascot=mascot),
    }


def history(db, league_id: str, team_id: str, draft_season_id: str) -> dict | None:
    """The league's past as the GM takes over (plans/league-backstory.md):
    the team's last season, the defending champion, and the team's titles
    and playoff trips over the seasons before. None in a league with no
    past seasons."""
    last = last_season(db, league_id, team_id, draft_season_id)
    if not last:
        return None
    series = SeriesRepository(db)
    past = [
        s
        for s in SeasonRepository(db).get_seasons_for_league(league_id)
        if s["id"] != draft_season_id and series.get_finals_id(s["id"])
    ]
    champ = series.get_champion(past[0]["id"]) if past else None
    titles = playoffs = 0
    for s in past:
        result = series.get_team_playoff_result(team_id, s["id"])
        playoffs += result is not None
        titles += bool(result and result.startswith("Won Finals"))
    return {
        "last": last,
        "champion": (
            {
                "team_id": champ["team_id"],
                "city": champ["city"],
                "mascot": champ["mascot"],
                "is_mine": champ["team_id"] == team_id,
            }
            if champ
            else None
        ),
        "seasons": len(past),
        "titles": titles,
        "playoffs": playoffs,
    }


def welcome(db, league: dict, gm: dict) -> dict | None:
    """Everything the welcome screen shows, or None when the GM has no team
    or the league has no draft yet."""
    team_id = gm.get("team_id")
    draft_repo = DraftRepository(db)
    draft = draft_repo.get_current_for_league(league["id"])
    if not team_id or not draft:
        return None
    team = TeamRepository(db).get_city_and_mascot(team_id)
    order = [r["team_id"] for r in draft_repo.get_team_id_draft_order(draft["id"])]
    rosters = draft_repo.get_roster_records(order)

    rated = {
        tid: [(p, ratings(p)) for p, status in players if status in MAJORS]
        for tid, players in rosters.items()
    }
    scores = {tid: area_scores(players) for tid, players in rated.items()}
    mine = rated.get(team_id, [])
    stars = sorted(mine, key=lambda x: role_rating(x[0]), reverse=True)[:STARS]

    needs = needs_for_draft(db, draft["id"]).get(team_id)
    weak = [
        {
            "label": CHIPS[chip].label,
            "level": LEVELS.get(level, ""),
            "reason": needs.reasons.get(chip, ""),
        }
        for chip, level in (needs.chips.items() if needs else [])
    ]

    opener = GameRepository(db).opening_game(draft["season_id"], team_id)
    if opener:
        home = opener["home_team_id"] == team_id
        side = "away" if home else "home"
        opener = {
            "date": opener["game_date"],
            "home": home,
            "city": opener[f"{side}_city"],
            "mascot": opener[f"{side}_mascot"],
        }

    others = [g for g in league_gms(db, league["id"]) if g["id"] != gm["id"]]

    return {
        "city": team["city"],
        "mascot": team["mascot"],
        "colors": team_colors(team["city"], team["mascot"]),
        "report": scouting_report(team_id, scores) if team_id in scores else None,
        "stars": [star_card(p, r) for p, r in stars],
        "weak": weak,
        "ages": age_profile([p for p, _ in mine]),
        "pick": draft_repo.get_pick_position(draft["id"], team_id),
        "num_teams": len(order),
        "blitz": draft["format"] == "preference",
        "opener": opener,
        "humans": [g for g in others if not g["is_ai"]],
        "favorites": favorites(team_id, scores, others),
        "history": history(db, league["id"], team_id, draft["season_id"]),
    }
