# src/api/services/custom_teams.py
"""
Custom teams: a contributor's own team of real player-seasons
(src/league/real_seasons/players.py), shared by code.

- Building or saving a copy of a team needs the Paid Contributor flag
  (users.is_contributor), or an admin. Anyone signed in can look at a
  shared team.
- A team holds up to 26 player-seasons. Any skill can be hand-edited from
  1 to 100; "Reset" goes back to the real rating.
- A share code opens a read-only view; "Save a copy" makes an independent
  team for the person who opened it.
- Custom teams only play in single-player leagues (part 3).
"""

from __future__ import annotations

import random
import string

from src.api.grade_curves import overall_to_grade
from src.db.repositories.custom_team_repo import CustomTeamRepository
from src.league.real_seasons import SKILLS, players
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_skills import PlayerSkills

ROSTER_MAX = 26
NAME_MAX = 40
PITCHERS_MIN = 10
STARTERS_MIN = 5
CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I
CODE_LENGTH = 8

PITCHER_POS = ("sp", "rp")

# Short labels for the skill columns and edit form, in SKILLS order.
SKILL_ABBR = {
    "contact": "CON",
    "power": "POW",
    "eye": "EYE",
    "speed": "SPD",
    "base_running": "BR",
    "bunting": "BUN",
    "durability": "DUR",
    "clutch": "CLU",
    "catching": "CA",
    "infield": "IF",
    "outfield": "OF",
    "arm": "ARM",
    "accuracy": "ACC",
    "strikes": "K",
    "ground_balls": "GB",
    "stamina": "STA",
    "recovery": "REC",
}
HITTER_SKILLS = SKILLS[:12]
PITCHER_SKILLS = SKILLS[12:]


class CustomTeamError(ValueError):
    """Something the person asked for can't be done; the message says why."""


def can_build(user: dict | None) -> bool:
    return bool(user and (user.get("is_admin") or user.get("is_contributor")))


def clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise CustomTeamError("Give the team a name.")
    if len(name) > NAME_MAX:
        raise CustomTeamError(f"Keep the name to {NAME_MAX} characters.")
    return name


def new_code(repo: CustomTeamRepository, rng: random.Random | None = None) -> str:
    rng = rng or random.SystemRandom()
    while True:
        code = "".join(rng.choice(CODE_LETTERS) for _ in range(CODE_LENGTH))
        if not repo.code_taken(code):
            return code


def normalize_code(code: str) -> str:
    keep = set(CODE_LETTERS) | set(string.ascii_uppercase) | set(string.digits)
    return "".join(c for c in code.upper() if c in keep)


def grade(skills: dict, pos: str, throws: str, age: int) -> tuple[str, int]:
    """Overall letter grade and value, as a pitcher or as a hitter."""
    r = PlayerEvaluator.rate_player(
        PlayerSkills(dict(skills), age=age), throws if throws in ("L", "R") else "R"
    )
    if pos in PITCHER_POS:
        value = max(r["sp"], r["rp"])
        return overall_to_grade(value, "pitcher"), round(value)
    value = r["overall_player"]
    return overall_to_grade(value, "hitter"), round(value)


def describe(season: players.PlayerSeason, skills: dict | None = None) -> dict:
    """What a page shows for one player-season, with edited skills if any."""
    real = season.skills
    now = {s: (skills or real).get(s, real[s]) for s in SKILLS}
    g, value = grade(now, season.pos, season.throws, season.age)
    return {
        "key": season.key,
        "name": season.name,
        "year": season.year,
        "born": season.born,
        "age": season.age,
        "pos": season.pos,
        "is_pitcher": season.pos in PITCHER_POS,
        "bats": season.bats,
        "throws": season.throws,
        "teams": "/".join(season.teams),
        "skills": now,
        "real": real,
        "edited": [s for s in SKILLS if now[s] != real[s]],
        "grade": g,
        "overall": value,
    }


def roster(team: dict) -> list[dict]:
    """The team's players, described, in the order they were added. A slot
    is the player's index in team["players"]."""
    out = []
    for slot, entry in enumerate(team["players"]):
        season = players.get(entry["key"])
        if season is None:
            continue  # a season the data no longer has
        row = describe(season, entry.get("skills"))
        row["slot"] = slot
        out.append(row)
    return out


def summary(rows: list[dict]) -> dict:
    """Counts by role, and what the team still needs to take the field."""
    pitchers = [r for r in rows if r["is_pitcher"]]
    starters = [r for r in pitchers if r["pos"] == "sp"]
    catchers = [r for r in rows if r["pos"] == "c"]
    needs = []
    if len(pitchers) < PITCHERS_MIN:
        needs.append(f"at least {PITCHERS_MIN} pitchers")
    if len(starters) < STARTERS_MIN:
        needs.append(f"at least {STARTERS_MIN} starting pitchers")
    if not catchers:
        needs.append("a catcher")
    return {
        "size": len(rows),
        "max": ROSTER_MAX,
        "pitchers": len(pitchers),
        "starters": len(starters),
        "hitters": len(rows) - len(pitchers),
        "needs": needs,
        "ready": not needs,
    }


# ── changes ────────────────────────────────────────────────────────────


def create(repo: CustomTeamRepository, user: dict, name: str) -> str:
    if not can_build(user):
        raise CustomTeamError("Custom teams are for paid contributors.")
    return repo.create(user["id"], clean_name(name), new_code(repo), [])


def owned(repo: CustomTeamRepository, user: dict, team_id: str) -> dict | None:
    team = repo.get(team_id)
    return team if team and team["owner_id"] == user["id"] else None


def add_player(repo: CustomTeamRepository, team: dict, key: str) -> None:
    entries = list(team["players"])
    season = players.get(key)
    if season is None:
        raise CustomTeamError("There's no such player-season.")
    if len(entries) >= ROSTER_MAX:
        raise CustomTeamError(f"A team holds {ROSTER_MAX} players. Remove one first.")
    for e in entries:
        pid, _, year = e["key"].rpartition("-")
        if pid == season.id:
            raise CustomTeamError(f"{season.name} is already on the team ({year}).")
    entries.append({"key": key, "skills": None})
    repo.save_players(team["id"], entries)


def remove_player(repo: CustomTeamRepository, team: dict, slot: int) -> None:
    entries = list(team["players"])
    if not 0 <= slot < len(entries):
        raise CustomTeamError("That player isn't on the team.")
    del entries[slot]
    repo.save_players(team["id"], entries)


def edit_skills(
    repo: CustomTeamRepository, team: dict, slot: int, values: dict[str, str]
) -> None:
    """Set a player's skills from a form; a skill left blank keeps its real
    value. Matching the real ratings everywhere clears the edit."""
    entries = list(team["players"])
    if not 0 <= slot < len(entries):
        raise CustomTeamError("That player isn't on the team.")
    season = players.get(entries[slot]["key"])
    if season is None:
        raise CustomTeamError("That player isn't on the team.")
    skills = {}
    for s in SKILLS:
        raw = (values.get(s) or "").strip()
        if not raw:
            skills[s] = season.skills[s]
            continue
        try:
            v = int(raw)
        except ValueError:
            raise CustomTeamError(f"{SKILL_ABBR[s]} has to be a number.") from None
        if not 1 <= v <= 100:
            raise CustomTeamError(f"{SKILL_ABBR[s]} has to be from 1 to 100.")
        skills[s] = v
    edited = skills != season.skills
    entries[slot] = {"key": season.key, "skills": skills if edited else None}
    repo.save_players(team["id"], entries)


def reset_skills(repo: CustomTeamRepository, team: dict, slot: int) -> None:
    entries = list(team["players"])
    if not 0 <= slot < len(entries):
        raise CustomTeamError("That player isn't on the team.")
    entries[slot] = {"key": entries[slot]["key"], "skills": None}
    repo.save_players(team["id"], entries)


def save_copy(repo: CustomTeamRepository, user: dict, team: dict) -> str:
    """A copy of someone's shared team, now the user's own to change."""
    if not can_build(user):
        raise CustomTeamError("Saving a copy is for paid contributors.")
    return repo.create(
        user["id"],
        team["name"],
        new_code(repo),
        [dict(e) for e in team["players"]],
        copied_from=team["id"],
    )
