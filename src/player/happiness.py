# src/player/happiness.py
"""
Player happiness (plans/player-happiness.md): every player wants different
things, and his mood is how well his team gives him what he wants.

The rules live here, with no database. src/db/repositories/happiness_repo.py
gathers each team's numbers, calls these, and stores the moods.

- A player's personality is drawn once, from his id (like his jersey
  numbers): a public type ("Ring Chaser"), a weight from 0 to 100 on each
  drive, three trait dials, and sometimes a favorite climate.
- Each drive's satisfaction runs from -1 (badly let down) to +1 (couldn't be
  better). Their weighted sum, with his age shifting the weights, is his
  target mood.
- His mood moves toward the target a step at a time, faster for a volatile
  player, and is shown as a word ("restless") and a line or two on what's on
  his mind. GMs never see a number; admins see all of it.

Coaching and teammates are planned drives that aren't built yet.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from src.league import team_pool

DRIVES = ("money", "winning", "impact", "position", "stability", "location", "fame")
TRAITS = ("ego", "temper", "loyalty")

# Public player types. Each has the drives that matter most to it, a tilt on
# the traits (points added to a 15..85 draw) and how often it's drawn.
TYPES: dict[str, dict] = {
    "Mercenary": {
        "drives": ("money",),
        "traits": {"loyalty": -30},
        "chance": 14,
        "blurb": "Goes where the money is.",
    },
    "Ring Chaser": {
        "drives": ("winning",),
        "traits": {"ego": -10},
        "chance": 14,
        "blurb": "Wants a ring more than anything.",
    },
    "Spotlight Seeker": {
        "drives": ("fame", "impact"),
        "traits": {"ego": 25},
        "chance": 10,
        "blurb": "Wants the big stage and the big moments.",
    },
    "Grinder": {
        "drives": ("position", "stability"),
        "traits": {"ego": -25},
        "chance": 12,
        "blurb": "Just wants to play his position for a steady club.",
    },
    "Homebody": {
        "drives": ("location",),
        "traits": {"loyalty": 25},
        "chance": 12,
        "blurb": "Happiest close to home.",
    },
    "Franchise Star": {
        "drives": ("impact", "money", "fame"),
        "traits": {"ego": 30},
        "chance": 8,
        "blurb": "Wants to be the face of a team, and paid like it.",
    },
    "Company Man": {
        "drives": ("stability", "winning"),
        "traits": {"loyalty": 30, "ego": -15},
        "chance": 12,
        "blurb": "Loyal to a well-run club.",
    },
    "Easygoing": {
        "drives": (),
        "traits": {"temper": -30},
        "chance": 18,
        "blurb": "Hard to upset.",
    },
}

# A favorite climate, for the location drive: most players don't have one.
CLIMATE_CHANCE = 0.4
CLIMATE_WEIGHTS = {
    team_pool.WARM: 30,
    team_pool.TEMPERATE: 25,
    team_pool.TROPICAL: 15,
    team_pool.COLD: 15,
    team_pool.DESERT: 5,
}

# Mood words, from the top band down. Same idea as the owner card.
MOODS = (
    (0.55, "thrilled"),
    (0.25, "happy"),
    (-0.15, "content"),
    (-0.4, "restless"),
    (-0.65, "unhappy"),
    (-math.inf, "miserable"),
)


@dataclass(frozen=True)
class Personality:
    type: str
    drives: dict[str, int]
    traits: dict[str, int]
    climate: str | None = None

    def as_row(self) -> dict:
        return {
            "type": self.type,
            "drives": dict(self.drives),
            "traits": dict(self.traits),
            "climate": self.climate,
        }

    @classmethod
    def from_row(cls, row: dict) -> Personality:
        drives = {d: int((row.get("drives") or {}).get(d, 20)) for d in DRIVES}
        traits = {t: int((row.get("traits") or {}).get(t, 50)) for t in TRAITS}
        return cls(row["type"], drives, traits, row.get("climate"))


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def random_personality(rng: random.Random) -> Personality:
    names = list(TYPES)
    kind = rng.choices(names, weights=[TYPES[n]["chance"] for n in names])[0]
    spec = TYPES[kind]
    strong = set(spec["drives"])
    if kind == "Easygoing":
        drives = {d: rng.randint(5, 35) for d in DRIVES}
    else:
        drives = {
            d: rng.randint(60, 100) if d in strong else rng.randint(5, 40)
            for d in DRIVES
        }
    traits = {
        t: int(_clamp(rng.randint(15, 85) + spec["traits"].get(t, 0), 0, 100))
        for t in TRAITS
    }
    climate = None
    if rng.random() < CLIMATE_CHANCE:
        cl = list(CLIMATE_WEIGHTS)
        climate = rng.choices(cl, weights=[CLIMATE_WEIGHTS[c] for c in cl])[0]
    return Personality(kind, drives, traits, climate)


def personality_for(player_id: str) -> Personality:
    """The player's personality, seeded by his id so it's the same whether
    it's made at creation or backfilled."""
    return random_personality(random.Random(f"personality:{player_id}"))


# ── Drive satisfaction ──────────────────────────────────────────────────────
# Each returns (satisfaction, why): why picks the "on his mind" line.


def money(salary: int | None, worth: float, rookie: bool = False) -> tuple[float, str]:
    """Paid against what his grade is worth on the market. Being underpaid
    stings more than being overpaid pleases. A player on his rookie deal
    knows the score, so it only bothers a star a little."""
    if not salary or worth <= 0:
        return 0.0, "none"
    ratio = salary / worth
    if rookie:
        # Only a star on a rookie deal minds, and only a little.
        return -0.3 * _clamp((worth - 8_000_000) / 15_000_000, 0, 1), "rookie"
    if ratio < 1:
        return _clamp((ratio - 1) * 2.5), "under"
    return _clamp((ratio - 1) * 1.2, hi=0.8), "over"


STATE_OUTLOOK = {
    "all-in": 0.5,
    "contending": 0.25,
    "retooling": -0.05,
    "ramping-up": -0.15,
    "rebuilding": -0.45,
    "aging-out": -0.3,
}


def winning(wins: int, losses: int, state: str | None) -> tuple[float, str]:
    """This season's record, leaning on the team's outlook (team state)
    until enough games are in."""
    games = wins + losses
    outlook = STATE_OUTLOOK.get(state or "", 0.0)
    record = _clamp((wins / games - 0.5) * 5) if games else 0.0
    w = games / (games + 30)
    return _clamp(w * record + (1 - w) * outlook), "record"


# Pitcher roles, as a share of a starter's importance.
BULLPEN_ROLE = {
    "Closer": 0.75,
    "Setup": 0.6,
    "Middle": 0.4,
    "Specialist": 0.4,
    "Long": 0.35,
    "Utility": 0.3,
}


@dataclass
class Usage:
    """How a team is using a player lately."""

    team_games: int = 0  # the team's games in the window
    starts: int = 0  # his starts in them (hitters)
    slots: list[int] = field(default_factory=list)  # batting order of each start
    positions: list[str] = field(default_factory=list)  # position of each start
    in_rotation: bool = False
    bullpen_role: str | None = None
    minors: bool = False


MIN_TEAM_GAMES = 3
ROLE_SLACK = 0.1


def expected_hitter_role(rank: int) -> float:
    """How big a role a hitter expects, from where his rating ranks among
    his team's hitters (0 = best): the top nine expect to play every day,
    the best near the top of the order."""
    if rank < 9:
        return 0.8 + 0.2 * (8 - rank) / 8
    if rank < 13:
        return 0.25
    return 0.1


def hitter_role(u: Usage) -> float:
    if u.minors:
        return 0.0
    share = min(1.0, u.starts / u.team_games) if u.team_games else 0.0
    if not u.slots:
        return 0.8 * share
    avg = sum(u.slots) / len(u.slots)
    return 0.8 * share + 0.2 * share * (9 - avg) / 8


def expected_pitcher_role(rank: int, affinity: str) -> float:
    if affinity == "rp":
        return 0.75 if rank < 6 else 0.4
    if rank < 5:
        return 1.0
    if rank < 8:
        return 0.6
    return 0.35


def pitcher_role(u: Usage) -> float:
    if u.minors:
        return 0.0
    if u.in_rotation:
        return 1.0
    return BULLPEN_ROLE.get(u.bullpen_role or "", 0.3)


def impact(
    is_pitcher: bool,
    affinity: str,
    rank: int,
    team_size: int,
    usage: Usage,
    ego: int,
) -> tuple[float, str]:
    """A big role for his talent, and being one of the best on the team.
    Falling short of the role he expects hurts, more for a big ego."""
    if is_pitcher:
        actual = pitcher_role(usage)
        expected = expected_pitcher_role(rank, affinity)
    elif usage.team_games < MIN_TEAM_GAMES and not usage.minors:
        actual = expected = expected_hitter_role(rank)
    else:
        actual = hitter_role(usage)
        expected = expected_hitter_role(rank)
    # A little below what he expects (batting fifth, not third) isn't a slight.
    gap = actual - expected
    if -ROLE_SLACK <= gap < 0:
        gap = 0.0
    elif gap < 0:
        gap += ROLE_SLACK
    pct = rank / max(1, team_size - 1)
    star = max(0.0, 0.5 - pct) * 0.6
    if gap < 0:
        sat = gap * 2.5 * (0.5 + ego / 100)
        why = _short_role_why(is_pitcher, affinity, usage)
    else:
        sat = gap * 1.0
        why = "star" if star > 0.15 else "role"
    return _clamp(sat + star), why


def _short_role_why(is_pitcher: bool, affinity: str, u: Usage) -> str:
    if u.minors:
        return "minors"
    if is_pitcher:
        return "rotation" if affinity == "sp" else "bullpen"
    share = u.starts / u.team_games if u.team_games else 0
    if share < 0.7:
        return "bench"
    return "order"


POSITION_GROUP = {
    "1b": "if",
    "2b": "if",
    "3b": "if",
    "ss": "if",
    "lf": "of",
    "cf": "of",
    "rf": "of",
}


def position_credit(affinity: str, played: str) -> float:
    if played == affinity:
        return 1.0
    if affinity in ("if", "of") and POSITION_GROUP.get(played) == affinity:
        return 1.0
    if affinity == "dh":
        return 0.6
    if played == "dh":
        return 0.25
    if POSITION_GROUP.get(played) and POSITION_GROUP.get(played) == POSITION_GROUP.get(
        affinity
    ):
        return 0.5
    return 0.0


def position(is_pitcher: bool, affinity: str, usage: Usage) -> tuple[float, str]:
    """Playing his own position. For a pitcher: a starter wants to start."""
    if is_pitcher:
        if usage.minors:
            return 0.0, "none"
        if affinity == "sp" and not usage.in_rotation:
            return -0.3, "rotation"
        if affinity == "rp" and usage.in_rotation:
            return -0.1, "bullpen"
        return 0.3, "own_p"
    if not usage.positions:
        return 0.0, "none"
    share = sum(position_credit(affinity, p) for p in usage.positions) / len(
        usage.positions
    )
    return _clamp(-1 + 1.4 * share), "own" if share >= 0.7 else "off"


def stability(
    history_pct: float | None, seasons: int, trades: int
) -> tuple[float, str]:
    """A franchise with a track record: winning seasons in the last few
    years, and not churning the roster with trades."""
    record = _clamp((history_pct - 0.5) * 6) if history_pct is not None else 0.0
    w = min(1.0, seasons / 3)
    churn = _clamp(-max(0, trades - 3) * 0.15, -0.6, 0.0)
    return _clamp(w * record * 0.8 + churn + 0.1), "record" if churn > -0.3 else "churn"


def _region_distance(a: str, b: str) -> float:
    """Degrees around the globe between two regions' middles."""
    d = abs(REGION_LONGITUDE[a] - REGION_LONGITUDE[b]) % 360
    return min(d, 360 - d)


REGION_LONGITUDE = {
    r: sum(t.longitude for t in team_pool.TEAM_POOL if t.region == r)
    / max(1, sum(1 for t in team_pool.TEAM_POOL if t.region == r))
    for r in team_pool.REGIONS
}

# Partial credit for the region nearest home when home has no team in the
# league (Josh, 2026-11-04).
NEAREST_REGION_CREDIT = 0.5


def location(
    home: str | None,
    team_region: str,
    team_climate: str,
    league_regions: set[str],
    likes_climate: str | None,
) -> tuple[float, str]:
    """Close to home, and his kind of weather if he has one. A player whose
    home region has no team in the league treats the nearest region that
    does as home, at partial credit."""
    if not home:
        return 0.0, "none"
    if home in league_regions or not league_regions:
        near, credit = home, 1.0
    else:
        near = min(league_regions, key=lambda r: (_region_distance(home, r), r))
        credit = NEAREST_REGION_CREDIT
    if team_region == near:
        sat, why = credit, "home"
    else:
        far = _region_distance(near, team_region) / 180
        sat, why = -0.1 - 0.6 * far, "away"
    if likes_climate:
        if team_climate == likes_climate:
            sat = 0.8 * sat + 0.2
        else:
            sat = 0.8 * sat - 0.2
            if why != "home":
                why = "climate"
    return _clamp(sat), why


def fame(market: int, all_star: bool) -> tuple[float, str]:
    """A big market, and being an All-Star."""
    sat = (market - 3) / 2 * 0.8 + (0.3 if all_star else 0.0)
    return _clamp(sat), "market" if not all_star else "all-star"


# ── Putting it together ─────────────────────────────────────────────────────


def age_weights(drives: dict[str, int], age: int) -> dict[str, float]:
    """Young players care more about playing time and money; past 30 they
    shift toward winning a ring."""
    w = {d: float(drives.get(d, 0)) for d in DRIVES}
    if age <= 25:
        w["impact"] *= 1.3
        w["money"] *= 1.1
    elif age > 30:
        w["winning"] *= min(1.6, 1 + 0.1 * (age - 30))
        w["impact"] *= 0.85
    return w


def target(
    personality: Personality, age: int, sats: dict[str, tuple[float, str]]
) -> float:
    """The mood his situation points to, -1 to 1. A loyal player shrugs
    off some of the bad."""
    w = age_weights(personality.drives, age)
    total = sum(w[d] for d in sats) or 1.0
    score = sum(w[d] * sats[d][0] for d in sats) / total
    if score < 0:
        score *= 1 - 0.35 * personality.traits["loyalty"] / 100
    # Weights are normalized, so a player with one strong drive and little
    # else feels that drive at full strength.
    return _clamp(score * 1.6)


def step(mood: float, goal: float, temper: int) -> float:
    """One week's move toward the target: a volatile player gets there
    faster."""
    k = 0.2 + 0.3 * temper / 100
    return _clamp(mood + k * (goal - mood))


def mood_word(mood: float) -> str:
    for cut, word in MOODS:
        if mood >= cut:
            return word
    return MOODS[-1][1]


# A drive has to carry at least this share of his weights to come up.
MIND_SHARE = 0.14

# What's on his mind, by drive and reason. {pos} is his position's name,
# {home} his home region, {climate} the weather he likes.
BAD_LINES = {
    ("money", "under"): "Thinks he's underpaid.",
    ("money", "rookie"): "Can't wait to get off his rookie deal.",
    ("winning", "record"): "Tired of losing.",
    ("impact", "bench"): "Wants to play every day.",
    ("impact", "order"): "Wants to bat higher in the order.",
    ("impact", "minors"): "Thinks he belongs in the majors.",
    ("impact", "rotation"): "Wants a spot in the rotation.",
    ("impact", "bullpen"): "Wants a bigger role in the bullpen.",
    ("position", "off"): "Wants to play {pos}.",
    ("position", "rotation"): "Wants to start, not relieve.",
    ("position", "bullpen"): "Would rather pitch in relief.",
    ("stability", "record"): "Doubts the front office.",
    ("stability", "churn"): "Uneasy with all the trades.",
    ("location", "away"): "Misses home ({home}).",
    ("location", "climate"): "Wishes he played somewhere {climate}.",
    ("location", "home"): "Wishes he played somewhere {climate}.",
    ("fame", "market"): "Wants a bigger stage.",
}
GOOD_LINES = {
    ("money", "over"): "Happy with his contract.",
    ("winning", "record"): "Loving the winning.",
    ("impact", "star"): "Enjoys being the man here.",
    ("impact", "role"): "Happy with his role.",
    ("position", "own"): "Glad to be playing {pos}.",
    ("stability", "record"): "Trusts the organization.",
    ("location", "home"): "Loves playing close to home.",
    ("fame", "market"): "Enjoys the big-city spotlight.",
    ("fame", "all-star"): "Enjoys the spotlight.",
}
# "Wants to play {pos}."
PLAY_POSITION = {
    "c": "catcher",
    "1b": "first base",
    "2b": "second base",
    "ss": "shortstop",
    "3b": "third base",
    "lf": "left field",
    "cf": "center field",
    "rf": "right field",
    "if": "the infield",
    "of": "the outfield",
    "dh": "DH",
    "sp": "starter",
    "rp": "reliever",
}
CLIMATE_WORD = {
    team_pool.TROPICAL: "tropical",
    team_pool.DESERT: "hot and dry",
    team_pool.WARM: "warm",
    team_pool.TEMPERATE: "mild",
    team_pool.COLD: "cold",
}


def on_his_mind(
    personality: Personality,
    age: int,
    sats: dict[str, tuple[float, str]],
    affinity: str,
    home: str | None,
    limit: int = 2,
) -> list[str]:
    """A line or two on what matters most to him right now, good or bad:
    the drives that move his mood the most."""
    w = age_weights(personality.drives, age)
    total = sum(w[d] for d in sats) or 1.0
    ranked = sorted(sats, key=lambda d: -abs(w[d] * sats[d][0]) / total)
    lines = []
    said = set()
    for d in ranked:
        sat, why = sats[d]
        pull = w[d] * sat / total
        # Only what he cares about: a drive with a small weight never comes
        # up, however good or bad it is.
        if abs(pull) < 0.04 or w[d] / total < MIND_SHARE:
            continue
        # A starter stuck in the bullpen says so once, not twice.
        topic = "rotation" if why in ("rotation", "bullpen") else d
        if topic in said:
            continue
        said.add(topic)
        table = BAD_LINES if sat < 0 else GOOD_LINES
        line = table.get((d, why))
        if not line:
            continue
        lines.append(
            line.format(
                pos=PLAY_POSITION.get(affinity, affinity),
                home=home or "home",
                climate=CLIMATE_WORD.get(personality.climate or "", "else"),
            )
        )
        if len(lines) >= limit:
            break
    return lines
