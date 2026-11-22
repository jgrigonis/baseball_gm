# src/api/services/custom_players.py
"""
Made-up players (Josh, 2026-11-22): a contributor's own players, made in the
player creator and put on custom teams next to real player-seasons.

- Making or editing one needs the Paid Contributor flag, or an admin, the
  same gate as custom teams (services/custom_teams.py). Like custom teams,
  they only ever play in single-player leagues.
- "Roll" makes a random player the way the game makes its own: a position
  (picked, or drawn), base skills for it at 17 (PlayerFactory), talent
  ceilings, then aged to a roster age like TeamFactory does. He gets a
  random name, personality, face, home region and jersey wishes.
- Then everything can be changed: name, position, age, bats/throws, every
  skill and its ceiling, his type, traits, drives, favorite climate, morale
  ruiner, face, home region and the numbers he wants.
- A custom team names one as {"made": "<id>"}. When the team goes into a
  league (league_custom_teams.assign) the league gets a copy of him as he
  is then, so later edits don't reach a running league.
"""

from __future__ import annotations

import random
import uuid

from src.api.grade_curves import OVERALL_CUTOFFS
from src.api.services import custom_teams as ct
from src.league import team_pool
from src.league.real_seasons import SKILLS
from src.name_generator.names import NameGenerator
from src.player import face as face_mod
from src.player import happiness as hp
from src.player.home_region import REGION_WEIGHTS, random_home_region
from src.player.jersey_numbers import NUMBER_WEIGHTS, random_prefs
from src.player.player_evaluator import (
    LEFT_HAND_CAP,
    LEFT_HAND_CAPPED_POSITIONS,
    ROLE_WEIGHTS,
)
from src.player.player_factory import PlayerFactory
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.player.positions import AFFINITY_POSITIONS
from src.player.talent_caps import generate_talent_caps

NAME_MAX = 24
AGE_MIN = 17
AGE_MAX = 45
JERSEY_MAX = 3  # numbers he wants, favorite first
# Rolled players' ages: mostly prime-ish big leaguers.
ROLL_AGES = (21, 31)

POSITION_NAMES = {
    "sp": "Starting pitcher",
    "rp": "Relief pitcher",
    "c": "Catcher",
    "1b": "First base",
    "2b": "Second base",
    "ss": "Shortstop",
    "3b": "Third base",
    "lf": "Left field",
    "cf": "Center field",
    "rf": "Right field",
    "if": "Utility infield",
    "of": "Outfield",
    "dh": "Designated hitter",
}

SKILL_NAMES = {
    "contact": "Contact",
    "power": "Power",
    "eye": "Eye",
    "speed": "Speed",
    "base_running": "Base running",
    "bunting": "Bunting",
    "durability": "Durability",
    "clutch": "Clutch",
    "catching": "Catching",
    "infield": "Infield",
    "outfield": "Outfield",
    "arm": "Arm",
    "accuracy": "Accuracy",
    "strikes": "Strikes",
    "ground_balls": "Ground balls",
    "stamina": "Stamina",
    "recovery": "Recovery",
}

# The creator's skill groups, hitters' order (pitchers see Pitching first).
SKILL_GROUPS = (
    ("Hitting", ("contact", "power", "eye", "base_running", "bunting")),
    ("General", ("speed", "durability", "clutch")),
    ("Defense", ("catching", "infield", "outfield", "arm")),
    ("Pitching", ("accuracy", "strikes", "ground_balls", "stamina", "recovery")),
)

DRIVE_LABELS = {
    "money": "Money",
    "winning": "Winning",
    "impact": "Big role",
    "position": "His position",
    "stability": "Stable club",
    "location": "Close to home",
    "fame": "Fame",
}
TRAIT_HELP = {
    "ego": "Wants credit and the spotlight",
    "temper": "How fast his mood swings",
    "loyalty": "Sticks with his club",
}


class CustomPlayerError(ValueError):
    """Something about the player can't be saved; the message says why."""


def can_build(user: dict | None) -> bool:
    return ct.can_build(user)


def _new_id(rng: random.Random) -> str:
    return uuid.UUID(int=rng.getrandbits(128)).hex


# ── Rolling a random player ────────────────────────────────────────────


def random_name(rng: random.Random | None = None) -> dict:
    gen = NameGenerator(rng=rng or random.Random())
    return {"first_name": _title(gen.first("male")), "last_name": _title(gen.last())}


def _title(name: str) -> str:
    """The name lists are upper case: "MCDONALD" -> "Mcdonald", "O'NEIL" ->
    "O'Neil"."""
    out, up = [], True
    for ch in name.lower():
        out.append(ch.upper() if up else ch)
        up = not ch.isalpha()
    return "".join(out)


def roll(
    rng: random.Random | None = None,
    position: str | None = None,
    age: int | None = None,
) -> dict:
    """A random player as the creator edits him (a dict like a stored row,
    without id or owner)."""
    rng = rng or random.Random()
    if position not in AFFINITY_POSITIONS:
        position = None
    base = PlayerFactory(rng=rng).create(position=position)
    age = age if age and AGE_MIN <= age <= AGE_MAX else rng.randint(*ROLL_AGES)
    caps = generate_talent_caps(base.skills.as_dict(), rng=rng)
    aged = base.skills.age_to(age, rng=rng, caps=caps)
    skills = {s: int(aged[s]) for s in SKILLS}
    seed = _new_id(rng)  # seeds the parts the game draws from an id
    pers = hp.random_personality(rng)
    name = random_name(rng)
    return {
        **name,
        "position": base.position,
        "bats": base.bats,
        "throws": base.throws,
        "age": age,
        "skills": skills,
        # A ceiling below where he is now would mean nothing.
        "caps": {s: max(int(caps.get(s, skills[s])), skills[s]) for s in SKILLS},
        "personality": {
            **pers.as_row(),
            "ruiner": hp.is_morale_ruiner(seed, pers.traits),
        },
        "face": face_mod.random_traits(seed),
        "home_region": random_home_region(rng),
        "jersey_prefs": random_prefs(rng)[:JERSEY_MAX],
    }


# ── Checking what the creator sends ────────────────────────────────────


def _int(value, label: str, lo: int, hi: int) -> int:
    try:
        v = int(value)
    except TypeError, ValueError:
        raise CustomPlayerError(f"{label} has to be a number.") from None
    if not lo <= v <= hi:
        raise CustomPlayerError(f"{label} has to be from {lo} to {hi}.")
    return v


def _name(value, label: str) -> str:
    name = " ".join(str(value or "").split())
    if not name:
        raise CustomPlayerError(f"Give him a {label}.")
    if len(name) > NAME_MAX:
        raise CustomPlayerError(f"Keep his {label} to {NAME_MAX} characters.")
    return name


def clean(data: dict) -> dict:
    """The creator's player, checked: every field there and in range.
    Raises CustomPlayerError with what to fix."""
    if not isinstance(data, dict):
        raise CustomPlayerError("That isn't a player.")
    position = data.get("position")
    if position not in AFFINITY_POSITIONS:
        raise CustomPlayerError("Pick a position.")
    bats, throws = data.get("bats"), data.get("throws")
    if bats not in ("L", "R", "S"):
        raise CustomPlayerError("Bats has to be L, R or S.")
    if throws not in ("L", "R"):
        raise CustomPlayerError("Throws has to be L or R.")
    raw_skills = data.get("skills") or {}
    raw_caps = data.get("caps") or {}
    skills, caps = {}, {}
    for s in SKILLS:
        skills[s] = _int(raw_skills.get(s), SKILL_NAMES[s], 1, 100)
        cap = raw_caps.get(s)
        cap = (
            skills[s]
            if cap in (None, "")
            else _int(cap, f"{SKILL_NAMES[s]} ceiling", 1, 100)
        )
        # A ceiling under his rating would mean nothing: he's already past it.
        caps[s] = max(cap, skills[s])
    pers = data.get("personality") or {}
    kind = pers.get("type")
    if kind not in hp.TYPES:
        raise CustomPlayerError("Pick a player type.")
    traits = {
        t: _int((pers.get("traits") or {}).get(t), t.capitalize(), 0, 100)
        for t in hp.TRAITS
    }
    drives = {
        d: _int((pers.get("drives") or {}).get(d), DRIVE_LABELS[d], 0, 100)
        for d in hp.DRIVES
    }
    climate = pers.get("climate") or None
    if climate is not None and climate not in team_pool.CLIMATES:
        raise CustomPlayerError("That isn't a climate.")
    region = data.get("home_region")
    if region not in REGION_WEIGHTS:
        raise CustomPlayerError("Pick where he's from.")
    jersey = []
    for n in data.get("jersey_prefs") or []:
        n = str(n).strip()
        if n not in NUMBER_WEIGHTS:
            raise CustomPlayerError(f"{n} isn't a jersey number (0 to 99, or 00).")
        if n not in jersey:
            jersey.append(n)
    if len(jersey) > JERSEY_MAX:
        raise CustomPlayerError(f"He can want up to {JERSEY_MAX} numbers.")
    return {
        "first_name": _name(data.get("first_name"), "first name"),
        "last_name": _name(data.get("last_name"), "last name"),
        "position": position,
        "bats": bats,
        "throws": throws,
        "age": _int(data.get("age"), "Age", AGE_MIN, AGE_MAX),
        "skills": skills,
        "caps": caps,
        "personality": {
            "type": kind,
            "traits": traits,
            "drives": drives,
            "climate": climate,
            "ruiner": bool(pers.get("ruiner")),
        },
        "face": face_mod.clean_traits(data.get("face") or {}),
        "home_region": region,
        "jersey_prefs": jersey,
    }


# ── Showing one ────────────────────────────────────────────────────────


def describe(row: dict) -> dict:
    """What a list or a custom team's roster shows for a made-up player, in
    the same shape as custom_teams.describe gives a player-season."""
    pos = row["position"]
    g, value = ct.grade(row["skills"], pos, row["throws"], row["age"])
    return {
        "key": f"made:{row['id']}",
        "made_id": row["id"],
        "made": True,
        "name": f"{row['first_name']} {row['last_name']}",
        "year": None,
        "born": None,
        "age": row["age"],
        "pos": pos,
        "pos_name": POSITION_NAMES.get(pos, pos.upper()),
        "is_pitcher": pos in ct.PITCHER_POS,
        "bats": row["bats"],
        "throws": row["throws"],
        "teams": "",
        "skills": {s: row["skills"][s] for s in SKILLS},
        "real": {s: row["skills"][s] for s in SKILLS},
        "edited": [],
        "grade": g,
        "overall": value,
        "type": (row.get("personality") or {}).get("type"),
        "face": row.get("face"),
    }


def face_svg(row: dict, city: str | None = None, mascot: str | None = None) -> str:
    return face_mod.face_svg("", row["age"], city, mascot, row.get("face") or {})


def creator_config() -> dict:
    """What the creator page's script needs to grade a player as he's
    edited, and the choices it offers."""
    return {
        "role_weights": ROLE_WEIGHTS,
        "lhcap": [sorted(LEFT_HAND_CAPPED_POSITIONS), LEFT_HAND_CAP],
        "cutoffs": {k: OVERALL_CUTOFFS[k] for k in ("hitter", "pitcher")},
        "grades": [
            "A+",
            "A",
            "A-",
            "B+",
            "B",
            "B-",
            "C+",
            "C",
            "C-",
            "D+",
            "D",
            "D-",
            "F",
        ],
        "positions": [[p, p.upper(), POSITION_NAMES[p]] for p in AFFINITY_POSITIONS],
        "skills": SKILL_NAMES,
        "abbr": ct.SKILL_ABBR,
        "groups": [[t, list(ks)] for t, ks in SKILL_GROUPS],
        "types": {name: {"blurb": t["blurb"]} for name, t in hp.TYPES.items()},
        "traits": list(hp.TRAITS),
        "trait_help": TRAIT_HELP,
        "drives": list(hp.DRIVES),
        "drive_labels": DRIVE_LABELS,
        "climates": list(team_pool.CLIMATES),
        "regions": list(REGION_WEIGHTS),
        "face_colors": {
            "skin": list(face_mod.SKIN),
            "hair": list(face_mod.HAIR),
            "eyes": list(face_mod.IRIS),
        },
        "face_choices": {
            "facial_hair": list(face_mod.FACIAL_HAIR),
            "mouth": list(face_mod.MOUTHS),
            "nose": list(face_mod.NOSES),
        },
        "face_ranges": [
            {"key": t.key, "label": t.label, "lo": t.lo, "hi": t.hi}
            for t in face_mod.TRAITS
            if t.kind == "range"
        ],
        "age_range": [AGE_MIN, AGE_MAX],
        "name_max": NAME_MAX,
    }


# ── Into a league ──────────────────────────────────────────────────────


def snapshot(row: dict) -> dict:
    """The parts of him a league keeps (league_custom_teams.players)."""
    keep = (
        "first_name",
        "last_name",
        "position",
        "bats",
        "throws",
        "age",
        "skills",
        "caps",
        "personality",
        "face",
        "home_region",
        "jersey_prefs",
    )
    return {k: row[k] for k in keep}


def record(snap: dict, rng: random.Random) -> PlayerRecord:
    """A new game player from a league's copy of a made-up player."""
    skills = {s: int(snap["skills"][s]) for s in SKILLS}
    return PlayerRecord(
        id=_new_id(rng),
        first_name=snap["first_name"],
        last_name=snap["last_name"],
        bats=snap["bats"],
        throws=snap["throws"],
        position=snap["position"],
        skills=PlayerSkills(skills, age=int(snap["age"])),
        caps={s: int(snap["caps"].get(s, skills[s])) for s in SKILLS},
    )
