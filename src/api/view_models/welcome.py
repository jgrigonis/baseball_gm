# src/api/view_models/welcome.py
#
# The welcome screen a GM sees when their league starts, before the draft
# (plans/welcome-screen.md): their team's colors and uniforms, how the
# roster stacks up against the league, its stars and weak spots, its ages,
# the GM's draft slot, opening day and the other GMs. In later seasons the
# same page is the season preview, shown before each draft, and adds how
# last season went and what changed on the roster since: who got better or
# worse over the winter, and who retired.

from __future__ import annotations

import dataclasses
import hashlib
import re
import unicodedata
from pathlib import Path

from src.api.grade_curves import overall_to_grade
from src.api.schemas import skill_to_grade
from src.api.services.draft_needs import needs_for_draft
from src.api.view_models.draft import last_season
from src.api.view_models.league_info import league_gms
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.series_repo import SeriesRepository
from src.db.repositories.team_repo import TeamRepository
from src.league.offseason.draft_strategy import CHIPS, ratings, staff_groups
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.player.player_value import role_rating
from src.team.colors import colors_for

MAJORS = ("26man", "40man")
STARS = 5  # best players shown under Your stars
MOVERS = 3  # risers and fallers shown under Over the winter

# area key, label, what it's ranked on
AREAS = (
    ("lineup", "Lineup", "top 9 hitters' overall offense"),
    ("rotation", "Rotation", "top 5 starters"),
    ("bullpen", "Bullpen", "top 7 relievers"),
    ("defense", "Defense", "top 9 hitters' best position"),
)
# Shown with the areas, but they say how a lineup plays, not how good it is,
# so the verdict and the favorites leave them out.
STYLE_AREAS = (
    ("power", "Power", "starting 9's average power"),
    ("speed", "Speed", "starting 9's average speed"),
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

# The team's uniform pieces shown on the welcome screen: (file, label).
# The SVGs come from scripts/export_uniform_svgs.py (docs/design/uniforms/).
UNIFORMS_DIR = (
    Path(__file__).resolve().parents[2] / "web" / "static" / "img" / "uniforms"
)
JERSEYS = (
    ("jersey-home", "Home"),
    ("jersey-away", "Away"),
    ("jersey-alternate", "Alternate"),
)
CAPS = (("cap", "Cap"), ("cap-alternate", "Alternate cap"))

TAGLINES = (
    "{city} has waited all winter for this.",
    "A new era of {mascot} baseball starts now.",
    "The {mascot} {are} yours. Make {city} proud.",
    "Every dynasty starts with a first season.",
    "{city} is ready. {Are} the {mascot}?",
    "The box score is blank. Time to write history, {city}.",
    "Tradition doesn’t rest. Neither {do} the {mascot}.",
    "Built on history. Bound for October.",
    "Legends are made in October, but they start right here.",
    "The pieces are in place. The chase begins now.",
    "Hungrier. Faster. Stronger. This is {mascot} baseball.",
    "The future belongs to {city}. Witness the rise.",
    "Our town. Our turf. Our {mascot}.",
    "9 innings. 1 city. 1 heartbeat.",
    "The lights are on, the grass is green, and {city} is roaring.",
    "Every pitch matters. Every game counts. {city} is ready.",
)


# The season preview's line under the title, by how last season ended.
RETURN_TAGLINES = {
    "champion": "Defending champions. Everyone in the league is coming for {city} now.",
    "playoffs": "October had a taste of {mascot} baseball. {City} wants more.",
    "winning": "A winning season behind them. Time to take the next step.",
    "losing": "Last season is done. A clean slate for the {mascot}.",
}


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _avg_top(values: list[int], n: int) -> float:
    top = sorted(values, reverse=True)[:n]
    return sum(top) / len(top) if top else 0.0


def area_scores(
    players: list[tuple[PlayerRecord, dict]], staff: dict[str, str] | None = None
) -> dict[str, float]:
    """The team's average rating in each area, from its major league roster.
    Pitchers count toward the rotation or bullpen by `staff` ({player_id:
    sp|rp}, their job on the team), else by draft_strategy.staff_groups."""
    staff = staff or {}
    hitters = [(p, r) for p, r in players if not p.is_pitcher()]
    best_hitters = sorted(hitters, key=lambda x: x[1]["overall_player"], reverse=True)
    pitchers = [(p, r) for p, r in players if p.is_pitcher()]
    groups = staff_groups(pitchers, staff)
    pitchers = [(r, groups[p.id]) for p, r in pitchers]
    starters = best_hitters[:9]
    return {
        "lineup": _avg_top([r["overall_offense"] for _, r in hitters], 9),
        "rotation": _avg_top([r["sp"] for r, g in pitchers if g == "sp"], 5),
        "bullpen": _avg_top([r["rp"] for r, g in pitchers if g == "rp"], 7),
        "defense": _avg_top([r["defensive_value"] for _, r in starters], 9),
        "power": _avg_top([p.skills["power"] for p, _ in starters], 9),
        "speed": _avg_top([p.skills["speed"] for p, _ in starters], 9),
    }


def scouting_report(team_id: str, scores: dict[str, dict[str, float]]) -> dict:
    """Where the team ranks in each area (1 = best), and a sentence on it."""
    n = len(scores)
    mine = scores[team_id]
    areas = []
    for key, label, basis in AREAS + STYLE_AREAS:
        value = mine[key]
        rank = 1 + sum(1 for s in scores.values() if s[key] > value)
        areas.append(
            {
                "key": key,
                "label": label,
                "basis": basis,
                "rank": rank,
                "rank_text": f"{ordinal(rank)} of {n}",
                "grade": overall_to_grade(value, f"team_{key}"),
                "style": (key, label, basis) in STYLE_AREAS,
                # Bars run from the league's worst (short) to its best (full).
                "bar": 100 if n == 1 else round(100 - 85 * (rank - 1) / (n - 1)),
            }
        )
    core = [a for a in areas if not a["style"]]
    return {"areas": areas, "verdict": verdict(core, n)}


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
        tid: sum(s[key] for key, _, _ in AREAS) / len(AREAS)
        for tid, s in scores.items()
        if tid != team_id
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
        "grade": overall_to_grade(
            role_rating(p), "pitcher" if p.is_pitcher() else "hitter"
        ),
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
    }


# The line under the age chart, by which third of the league the team's
# average age falls in. Most players in a league are 25 and under, so counting
# the team's own age groups called nearly every roster young.
AGE_OUTLOOKS = {
    "young": "One of the league's younger rosters: it should get better as it grows up.",
    "middle": "Right around the league's average age: a mix of youth and experience.",
    "old": "One of the league's older rosters: win now, before age catches up.",
}


def age_rank(team_id: str, rosters: dict[str, list[PlayerRecord]]) -> dict | None:
    """Where the team's average age ranks in the league: counted from the
    young end in the younger half of the league, from the old end in the
    older half, so a team reads as "3rd youngest" or "2nd oldest" and never
    "18th youngest". Ties share a rank."""
    averages = {
        tid: sum(p.age for p in players) / len(players)
        for tid, players in rosters.items()
        if players
    }
    if team_id not in averages or len(averages) < 2:
        return None
    mine = round(averages[team_id], 1)
    rounded = [round(a, 1) for a in averages.values()]
    n = len(rounded)
    younger = sum(1 for a in rounded if a < mine)
    older = sum(1 for a in rounded if a > mine)
    tied = n - younger - older > 1
    # Thirds by how many teams are younger or older, so tied teams land in
    # the same third.
    third = "young" if younger < n / 3 else "old" if older < n / 3 else "middle"
    if younger <= older:
        rank, end = younger + 1, "youngest"
    else:
        rank, end = older + 1, "oldest"
    place = end.capitalize() if rank == 1 else f"{ordinal(rank)} {end}"
    if tied:
        place = f"Tied for {place.lower() if rank == 1 else place}"
    return {
        "rank": rank,
        "end": end,
        "tied": tied,
        "of": n,
        "label": f"{place} of {n} teams",
        "league_average": round(sum(averages.values()) / n, 1),
        "outlook": AGE_OUTLOOKS[third],
    }


def _named(p: PlayerRecord) -> dict:
    return {"player_id": p.id, "name": f"{p.first_name} {p.last_name}", "age": p.age}


def verbs(mascot: str) -> dict:
    """The verbs a tagline needs to agree with the team's name: the Titans
    are, but the Rain, the Weird and the Berlin Bear is."""
    if mascot.endswith("s"):
        return {"are": "are", "Are": "Are", "do": "do"}
    return {"are": "is", "Are": "Is", "do": "does"}


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
        ].format(city=city, mascot=mascot, **verbs(mascot)),
    }


def return_tagline(city: str, mascot: str, history: dict | None) -> str:
    """The season preview's tagline, from how the team's last season went."""
    last = (history or {}).get("last")
    champ = (history or {}).get("champion")
    if champ and champ["is_mine"]:
        key = "champion"
    elif last and last["playoffs"]:
        key = "playoffs"
    elif last and last["w"] > last["l"]:
        key = "winning"
    else:
        key = "losing"
    return RETURN_TAGLINES[key].format(city=city, City=city, mascot=mascot)


def movers(db, players: list[PlayerRecord], season_id: str | None) -> dict | None:
    """Who got better and who slipped since the end of `season_id`, by
    their overall rating then (the season's skill snapshot) and now. None
    without a snapshot to compare with."""
    if not season_id or not players:
        return None
    rows = db.execute(
        "SELECT * FROM player_skills_history WHERE season_id = %s AND player_id = ANY(%s)",
        (season_id, [p.id for p in players]),
    ).fetchall()
    then = {r["player_id"]: PlayerSkills.from_db_row(r) for r in rows}
    changes = []
    for p in players:
        if p.id not in then:
            continue
        kind = "pitcher" if p.is_pitcher() else "hitter"
        before = role_rating(dataclasses.replace(p, skills=then[p.id]))
        now = role_rating(p)
        if now != before:
            changes.append(
                {
                    **_named(p),
                    "position": p.position.upper(),
                    "change": now - before,
                    "was": overall_to_grade(before, kind),
                    "now": overall_to_grade(now, kind),
                }
            )
    if not changes:
        return None
    changes.sort(key=lambda c: c["change"], reverse=True)
    return {
        "up": [c for c in changes if c["change"] > 0][:MOVERS],
        "down": [c for c in reversed(changes) if c["change"] < 0][:MOVERS],
    }


def retirees(db, team_id: str, season_id: str | None) -> list[dict]:
    """The team's players who retired after `season_id`, best first."""
    if not season_id:
        return []
    rows = db.execute(
        """SELECT p.id, p.first_name, p.last_name, p.position, ps.age
           FROM player_retirements r
           JOIN players p ON p.id = r.player_id
           JOIN player_skills ps ON ps.player_id = p.id
           WHERE r.former_team_id = %s AND r.season_id = %s
           ORDER BY p.last_name, p.first_name""",
        (team_id, season_id),
    ).fetchall()
    return [
        {
            "player_id": r["id"],
            "name": f"{r['first_name']} {r['last_name']}",
            "position": r["position"].upper(),
            "age": r["age"],
        }
        for r in rows
    ]


def uniform_slug(city: str) -> str:
    """The folder a city's uniform SVGs live in: "São Paulo" -> "sao-paulo"."""
    ascii_city = unicodedata.normalize("NFKD", city).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_city.lower()).strip("-")


def uniforms(city: str) -> dict | None:
    """Paths under static/ for the team's jerseys, caps and patch, or None
    for a team without a uniform set yet."""
    slug = uniform_slug(city)
    folder = UNIFORMS_DIR / slug
    names = [n for n, _ in JERSEYS + CAPS] + ["patch"]
    if not all((folder / f"{n}.svg").exists() for n in names):
        return None

    def pieces(items):
        return [
            {"path": f"img/uniforms/{slug}/{n}.svg", "label": label}
            for n, label in items
        ]

    return {
        "jerseys": pieces(JERSEYS),
        "caps": pieces(CAPS),
        "patch": f"img/uniforms/{slug}/patch.svg",
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
    staff = draft_repo.get_staff_groups(order)

    rated = {
        tid: [(p, ratings(p)) for p, status in players if status in MAJORS]
        for tid, players in rosters.items()
    }
    scores = {tid: area_scores(players, staff) for tid, players in rated.items()}
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
    past = history(db, league["id"], team_id, draft["season_id"])
    seasons = SeasonRepository(db)
    season = seasons.get_year(draft["season_id"])
    # The league's first season gets the welcome screen; every one after it
    # is a season preview, with what changed since the one before.
    first = LeagueRepository(db).count_seasons(league["id"]) <= 1
    before = [
        s["id"]
        for s in seasons.get_seasons_for_league(league["id"])
        if season and s["year"] < season["year"]
    ]
    last_id = before[0] if before and not first else None
    colors = team_colors(team["city"], team["mascot"])
    if not first:
        colors["tagline"] = return_tagline(team["city"], team["mascot"], past)

    return {
        "season_id": draft["season_id"],
        "year": season["year"] if season else None,
        "first": first,
        "draft_done": draft["state"] == "complete",
        "city": team["city"],
        "mascot": team["mascot"],
        "colors": colors,
        "uniforms": uniforms(team["city"]),
        "report": scouting_report(team_id, scores) if team_id in scores else None,
        "stars": [star_card(p, r) for p, r in stars],
        "weak": weak,
        "ages": age_profile([p for p, _ in mine]),
        "age_rank": age_rank(
            team_id, {tid: [p for p, _ in ps] for tid, ps in rated.items()}
        ),
        "pick": draft_repo.get_pick_position(draft["id"], team_id),
        "num_teams": len(order),
        "blitz": draft["format"] == "preference",
        "opener": opener,
        "humans": [g for g in others if not g["is_ai"]],
        "favorites": favorites(team_id, scores, others),
        "history": past,
        "movers": movers(db, [p for p, _ in mine], last_id),
        "retirees": retirees(db, team_id, last_id),
    }
