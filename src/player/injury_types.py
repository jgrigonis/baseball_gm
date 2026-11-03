# src/player/injury_types.py
"""
The catalog of specific injuries (plans/injury-details.md).

The sim first rolls a severity tier (minor, moderate, severe, surgery), which
sets roughly how long the player is out. Then it picks one injury of that tier
that fits what the player was doing (batting, running, fielding, pitching)
and, for fielders, where they were playing. The injury's own day range, which
sits inside its tier's range, sets the days missed.

After an injury the player comes back rusty (RUST below): a few ratings sit
lower for a while and fade back day by day, twice as fast on days he
doesn't play. Some injuries also leave something for good (LASTING
below), rolled when he comes back: a hamstring that never quite heals, a
torn ACL that costs speed, or a Tommy John pitcher who returns throwing
harder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random

# Days missed for each severity tier. Every injury's range sits inside its
# tier's, so the tier stays a good guide to how long a layoff is.
INJURY_TIERS = {
    "minor": (1, 7),
    "moderate": (7, 50),
    "pitcher": (12, 50),  # unused
    "severe": (57, 90),
    "surgery": (270, 540),
}

ACTIVITIES = ("batting", "running", "fielding", "pitching")


@dataclass(frozen=True)
class InjuryType:
    key: str
    label: str  # "Torn ACL": the name shown everywhere
    phrase: str  # "a torn ACL": for sentences ("lose Smith to a torn ACL")
    severity: str
    days: tuple[int, int]
    # Relative chance of this injury for each activity it can happen in.
    activities: dict[str, float]
    # Fielding only: multiplier by position, "*" for every other position.
    positions: dict[str, float] = field(default_factory=dict)

    def weight(self, activity: str, position: str | None = None) -> float:
        w = self.activities.get(activity, 0.0)
        if w and activity == "fielding" and self.positions:
            w *= self.positions.get(position or "", self.positions.get("*", 1.0))
        return w


_OF = {"lf": 1.0, "cf": 1.0, "rf": 1.0}
# Hard throwers among position players: catchers, shortstops, outfielders
_THROWERS = {"c": 3.0, "ss": 2.0, **{p: 1.5 for p in _OF}, "*": 0.3}


def _t(key, label, phrase, severity, days, activities, positions=None):
    return InjuryType(key, label, phrase, severity, days, activities, positions or {})


INJURY_TYPES: dict[str, InjuryType] = {
    t.key: t
    for t in [
        # ── Minor (1-7 days) ────────────────────────────────────────────────
        _t("hand_contusion", "Hand contusion", "a bruised hand", "minor", (1, 5),
           {"batting": 3}),
        _t("jammed_finger", "Jammed finger", "a jammed finger", "minor", (1, 6),
           {"batting": 1, "fielding": 2}),
        _t("ankle_sprain", "Ankle sprain", "a sprained ankle", "minor", (2, 7),
           {"running": 3, "fielding": 2}),
        _t("back_spasms", "Back spasms", "back spasms", "minor", (1, 6),
           {"batting": 1, "running": 1, "fielding": 1, "pitching": 1}),
        _t("blister", "Blister", "a blister", "minor", (2, 7),
           {"pitching": 3}),
        _t("arm_fatigue", "Arm fatigue", "arm fatigue", "minor", (3, 7),
           {"pitching": 3}),
        # ── Moderate (7-50 days) ────────────────────────────────────────────
        _t("hamstring_strain", "Hamstring strain", "a hamstring strain", "moderate",
           (10, 35), {"running": 4, "fielding": 1}),
        _t("groin_strain", "Groin strain", "a groin strain", "moderate", (10, 30),
           {"running": 2, "fielding": 2}),
        _t("oblique_strain", "Oblique strain", "an oblique strain", "moderate",
           (14, 45), {"batting": 3, "pitching": 2}),
        _t("wrist_sprain", "Wrist sprain", "a sprained wrist", "moderate", (10, 40),
           {"batting": 2}),
        _t("broken_finger", "Broken finger", "a broken finger", "moderate", (20, 45),
           {"batting": 1, "fielding": 1}, {"c": 3.0, "*": 0.0}),
        _t("concussion", "Concussion", "a concussion", "moderate", (7, 40),
           {"batting": 1, "fielding": 1},
           {"c": 3.0, **{p: 1.5 for p in _OF}, "*": 0.3}),
        _t("shoulder_inflammation", "Shoulder inflammation", "shoulder inflammation",
           "moderate", (15, 45), {"pitching": 3}),
        _t("elbow_inflammation", "Elbow inflammation", "elbow inflammation",
           "moderate", (15, 40), {"pitching": 3}),
        # ── Severe (57-90 days) ─────────────────────────────────────────────
        _t("broken_hamate", "Broken hamate", "a broken hamate", "severe", (57, 80),
           {"batting": 3}),
        _t("high_ankle_sprain", "High ankle sprain", "a high ankle sprain", "severe",
           (57, 90), {"running": 2, "fielding": 1}),
        _t("torn_meniscus", "Torn meniscus", "a torn meniscus", "severe", (60, 90),
           {"running": 1, "fielding": 2}),
        _t("separated_shoulder", "Separated shoulder", "a separated shoulder",
           "severe", (57, 90), {"fielding": 1},
           {**{p: 2.0 for p in _OF}, "*": 1.0}),
        _t("lat_strain", "Lat strain", "a lat strain", "severe", (57, 90),
           {"pitching": 3}),
        _t("flexor_strain", "Flexor strain", "a flexor strain", "severe", (57, 85),
           {"pitching": 2}),
        # ── Surgery (270-540 days) ──────────────────────────────────────────
        _t("tommy_john", "Tommy John surgery", "Tommy John surgery", "surgery",
           (365, 540), {"pitching": 5, "fielding": 0.3}, _THROWERS),
        _t("torn_rotator_cuff", "Torn rotator cuff", "a torn rotator cuff",
           "surgery", (300, 540), {"pitching": 3, "fielding": 0.5}, _THROWERS),
        _t("torn_acl", "Torn ACL", "a torn ACL", "surgery", (270, 400),
           {"running": 3, "fielding": 2}),
        _t("torn_achilles", "Torn Achilles", "a torn Achilles", "surgery",
           (300, 450), {"running": 2}),
        _t("hip_labrum", "Torn hip labrum", "a torn hip labrum", "surgery",
           (270, 360), {"batting": 2, "fielding": 1}),
        _t("back_surgery", "Back surgery", "back surgery", "surgery", (270, 400),
           {"batting": 2, "fielding": 0.5, "pitching": 0.5}),
    ]
}  # fmt: skip


# ── Rust ──────────────────────────────────────────────────────────────────────
# What each injury leaves behind when the player comes back: the most each
# rating can drop, and how many days the rust lasts if he plays every day.
# Both are rolled per injury (roll_rust), so no two comebacks are the same.
RUST: dict[str, tuple[int, dict[str, int]]] = {
    "hand_contusion": (7, {"contact": 2}),
    "jammed_finger": (5, {"contact": 2}),
    "ankle_sprain": (7, {"speed": 3}),
    "back_spasms": (5, {"power": 2}),
    "blister": (7, {"accuracy": 3}),
    "arm_fatigue": (7, {"stamina": 3}),
    "hamstring_strain": (21, {"speed": 5, "base_running": 3}),
    "groin_strain": (14, {"speed": 4, "infield": 3, "outfield": 3}),
    "oblique_strain": (21, {"power": 5, "strikes": 4}),
    "wrist_sprain": (30, {"power": 4, "contact": 3}),
    "broken_finger": (21, {"contact": 4}),
    "concussion": (21, {"eye": 4, "contact": 3}),
    "shoulder_inflammation": (21, {"strikes": 3, "stamina": 5}),
    "elbow_inflammation": (21, {"accuracy": 4}),
    "broken_hamate": (45, {"power": 6}),
    "high_ankle_sprain": (30, {"speed": 6}),
    "torn_meniscus": (30, {"speed": 4, "infield": 3, "outfield": 3}),
    "separated_shoulder": (30, {"arm": 5}),
    "lat_strain": (30, {"stamina": 6, "strikes": 4}),
    "flexor_strain": (30, {"strikes": 5, "accuracy": 3}),
    "tommy_john": (60, {"accuracy": 6}),  # command comes back last
    "torn_rotator_cuff": (60, {"strikes": 5, "stamina": 5, "arm": 4}),
    "torn_acl": (60, {"speed": 5}),
    "torn_achilles": (60, {"speed": 5, "base_running": 3}),
    "hip_labrum": (45, {"power": 4, "speed": 3}),
    "back_surgery": (45, {"power": 5}),
}

# A day on the bench (or a team off day) heals this much more rust than a
# day spent playing.
REST_FADE = 2.0


def roll_rust(
    injury_type: str | None,
    days_missed: int,
    age: int | None = None,
    durability: int | None = None,
    rng: random.Random | None = None,
) -> tuple[dict[str, float], float] | None:
    """Roll the rust an injury leaves: ({skill: points}, days it lasts if the
    player plays every day). None for an injury with no rust.

    - Each rating drops by half to all of its catalog amount.
    - The length is 50-150% of the catalog's, longer when the injury itself
      ran long for its kind, longer for players past 30 and shorter for
      young ones, and shorter for durable hitters. Pass durability only for
      hitters: it never applies to pitchers.
    """
    rust = RUST.get(injury_type or "")
    if not rust:
        return None
    rng = rng or random
    base_days, amounts = rust
    lo, hi = INJURY_TYPES[injury_type].days
    ran_long = (days_missed - lo) / (hi - lo) if hi > lo else 0.5
    ran_long = min(1.0, max(0.0, ran_long))
    length = base_days * rng.uniform(0.5, 1.5) * (0.8 + 0.4 * ran_long)
    if age is not None:
        length *= min(1.3, max(0.85, 1 + 0.03 * (age - 30)))
    if durability is not None:
        length *= 1 - (durability - 50) / 50 * 0.15
    skills = {k: round(v * rng.uniform(0.5, 1.0), 1) for k, v in amounts.items()}
    return skills, round(max(2.0, length), 1)


def rust_progress(days_back: int, days_played: int) -> float:
    """Rust healed after `days_back` days since returning, `days_played` of
    them in games: a day played counts 1, a day off counts REST_FADE."""
    days_played = min(days_played, days_back)
    return days_played + (days_back - days_played) * REST_FADE


def rust_left(
    skills: dict[str, float], length: float, days_back: int, days_played: int
) -> dict[str, float]:
    """The rust still there: each rating's drop shrinks evenly to zero."""
    left = max(0.0, 1 - rust_progress(days_back, days_played) / length)
    return {k: v * left for k, v in skills.items() if v * left >= 0.5}


def rust_days_to_clear(
    skills: dict[str, float], length: float, days_back: int, days_played: int
) -> int:
    """Days until no rating is down a whole point, if he plays every day."""
    biggest = max(skills.values(), default=0)
    if biggest <= 0:
        return 0
    # The last point is gone once the biggest drop is under half a point.
    needed = length * (1 - 0.5 / biggest)
    return max(0, math.ceil(needed - rust_progress(days_back, days_played)))


def choose_injury_type(
    severity: str,
    activity: str,
    position: str | None = None,
    rng: random.Random | None = None,
) -> InjuryType | None:
    """Pick an injury of this tier that fits the activity (and position, for
    fielders). None when nothing in the catalog fits."""
    rng = rng or random
    options = [
        (t, w)
        for t in INJURY_TYPES.values()
        if t.severity == severity and (w := t.weight(activity, position)) > 0
    ]
    if not options:
        # A position no fielding injury favors still gets one of the tier's
        # fielding injuries, weighted as if it had no position.
        options = [
            (t, w)
            for t in INJURY_TYPES.values()
            if t.severity == severity and (w := t.activities.get(activity, 0)) > 0
        ]
    if not options:
        return None
    pick = rng.random() * sum(w for _, w in options)
    for t, w in options:
        pick -= w
        if pick < 0:
            return t
    return options[-1][0]


def roll_days_missed(
    severity: str, rng: random.Random | None = None, injury_type: str | None = None
) -> int:
    """Days missed: from the injury's own range, else its tier's."""
    t = INJURY_TYPES.get(injury_type or "")
    lo, hi = t.days if t else INJURY_TIERS.get(severity, INJURY_TIERS["minor"])
    return (rng or random).randint(lo, hi)


def injury_label(injury_type: str | None, severity: str | None = None) -> str:
    """The injury's name, or the capitalized severity for injuries recorded
    before injuries had types."""
    t = INJURY_TYPES.get(injury_type or "")
    if t:
        return t.label
    return (severity or "injury").capitalize()


def injury_phrase(injury_type: str | None) -> str | None:
    t = INJURY_TYPES.get(injury_type or "")
    return t.phrase if t else None


# ── Lasting effects ──────────────────────────────────────────────────────────
# What an injury can leave for good, rolled once when the player comes back
# (roll_lasting). Each injury has a list of outcomes, best first:
# (key, weight, {skill: (low, high) points}). Most moderate and severe
# injuries heal fully most of the time; surgeries always roll an outcome,
# and Tommy John can bring a pitcher back throwing harder.


@dataclass(frozen=True)
class Outcome:
    key: str
    weight: float
    effects: dict[str, tuple[int, int]] = field(default_factory=dict)


def _o(key, weight, **effects):
    return Outcome(key, weight, effects)


LASTING: dict[str, list[Outcome]] = {
    # ── Moderate ──
    "hamstring_strain": [_o("full", 90), _o("lingering", 10, speed=(-2, -1))],
    "concussion": [_o("full", 90), _o("lingering", 10, eye=(-3, -1))],
    # ── Severe ──
    "broken_hamate": [_o("full", 80), _o("lingering", 20, power=(-3, -1))],
    "high_ankle_sprain": [_o("full", 85), _o("lingering", 15, speed=(-2, -1))],
    "torn_meniscus": [_o("full", 70), _o("lingering", 30, speed=(-3, -1))],
    "separated_shoulder": [_o("full", 75), _o("lingering", 25, arm=(-3, -1))],
    "lat_strain": [_o("full", 85), _o("lingering", 15, stamina=(-3, -1))],
    "flexor_strain": [_o("full", 85), _o("lingering", 15, strikes=(-2, -1))],
    # ── Surgery ──
    "tommy_john": [
        _o("stronger", 25, strikes=(2, 5), arm=(1, 3)),
        _o("full", 55, strikes=(-1, 1)),
        _o("bad", 20, strikes=(-8, -3), accuracy=(-5, -2)),
    ],
    "torn_rotator_cuff": [
        _o("full", 15),
        _o("diminished", 60, strikes=(-6, -3), stamina=(-6, -3)),
        _o("bad", 25, strikes=(-10, -6), stamina=(-8, -5), accuracy=(-5, -2)),
    ],
    "torn_acl": [
        _o("full", 15),
        _o("typical", 65, speed=(-6, -3), base_running=(-4, -2),
           infield=(-3, -1), outfield=(-3, -1)),
        _o("bad", 20, speed=(-10, -6), base_running=(-4, -2),
           infield=(-3, -1), outfield=(-3, -1), durability=(-6, -3)),
    ],
    "torn_achilles": [
        _o("typical", 70, speed=(-8, -4), base_running=(-4, -2)),
        _o("bad", 30, speed=(-12, -8), base_running=(-4, -2), durability=(-5, -3)),
    ],
    "hip_labrum": [
        _o("full", 40),
        _o("typical", 60, power=(-4, -1), speed=(-3, -1)),
    ],
    "back_surgery": [
        _o("full", 35),
        _o("typical", 50, power=(-5, -2), durability=(-4, -2)),
        _o("bad", 15, power=(-8, -5), durability=(-5, -5)),
    ],
}  # fmt: skip

# How each outcome reads ("Came back stronger: KK +3").
OUTCOME_LABELS = {
    "stronger": "Came back stronger",
    "full": "Full recovery",
    "lingering": "Lingering effects",
    "typical": "Some lasting loss",
    "diminished": "Diminished",
    "bad": "Never the same",
}

# A pitcher's arm problems hit a position player's throwing arm instead, and
# a pitcher's back problems sap his stamina rather than his (unused) power.
_HITTER_SKILL = {"strikes": "arm", "stamina": "arm", "accuracy": "arm"}
_PITCHER_SKILL = {"power": "stamina"}

# Chance a lasting loss also lowers the player's talent cap, so he can't
# simply develop it back. Scaled by age and (hitters only) durability.
CAP_DROP_CHANCE = 0.10


def outcome_shift(age: int | None, durability: int | None) -> float:
    """Share of the odds that moves from the best outcome to the worst:
    ~3% per year past 30, ~3% the other way per year under 25, and up to
    5% either way for durability. Pass durability only for hitters."""
    shift = 0.0
    if age is not None:
        if age > 30:
            shift += 0.03 * (age - 30)
        elif age < 25:
            shift -= 0.03 * (25 - age)
    if durability is not None:
        shift -= (durability - 50) / 50 * 0.05
    return min(0.3, max(-0.3, shift))


def outcome_odds(
    injury_type: str, age: int | None = None, durability: int | None = None
) -> list[tuple[Outcome, float]]:
    """The injury's outcomes with their chances (summing to 1) for this
    player."""
    outcomes = LASTING.get(injury_type) or []
    if not outcomes:
        return []
    total = sum(o.weight for o in outcomes)
    odds = [o.weight / total for o in outcomes]
    if len(odds) > 1:
        shift = outcome_shift(age, durability)
        if shift > 0:
            moved = min(shift, odds[0])
            odds[0] -= moved
            odds[-1] += moved
        elif shift < 0:
            moved = min(-shift, odds[-1])
            odds[-1] -= moved
            odds[0] += moved
    return list(zip(outcomes, odds))


def cap_drop_chance(age: int | None, durability: int | None) -> float:
    """Chance a lasting loss lowers the talent cap too: 10% at 30, half
    that at 25 and under, up to double for old players, and less for
    durable hitters. Pass durability only for hitters."""
    chance = CAP_DROP_CHANCE
    if age is not None:
        chance *= min(2.0, max(0.5, 1 + 0.1 * (age - 30)))
    if durability is not None:
        chance *= 1 - (durability - 50) / 50 * 0.5
    return chance


@dataclass
class LastingResult:
    outcome: str
    effects: dict[str, int]  # {skill: points}, + or -
    cap_drop: bool = False  # losses lower the talent cap too


def roll_lasting(
    injury_type: str | None,
    pitcher: bool,
    age: int | None = None,
    durability: int | None = None,
    rng: random.Random | None = None,
) -> LastingResult | None:
    """Roll what an injury leaves for good when the player comes back. None
    for an injury with no outcome table. Durability is ignored for pitchers
    (it's never used for them), both as a nudge and as an effect."""
    odds = outcome_odds(injury_type or "", age, None if pitcher else durability)
    if not odds:
        return None
    rng = rng or random
    pick = rng.random()
    chosen = odds[-1][0]
    for outcome, chance in odds:
        pick -= chance
        if pick < 0:
            chosen = outcome
            break
    remap = _PITCHER_SKILL if pitcher else _HITTER_SKILL
    effects: dict[str, int] = {}
    for skill, (lo, hi) in chosen.effects.items():
        if pitcher and skill == "durability":
            continue
        n = rng.randint(lo, hi)
        if n == 0:
            continue
        skill = remap.get(skill, skill)
        old = effects.get(skill)
        # Two effects landing on one skill: the bigger one counts.
        if old is None or abs(n) > abs(old):
            effects[skill] = n
    cap_drop = False
    if any(v < 0 for v in effects.values()):
        chance = cap_drop_chance(age, None if pitcher else durability)
        cap_drop = rng.random() < chance
    return LastingResult(chosen.key, effects, cap_drop)


def outcome_label(outcome: str | None) -> str | None:
    return OUTCOME_LABELS.get(outcome or "")


def effects_text(effects: dict | None) -> str:
    """{"speed": -4, "strikes": 3} -> "SP −4 · KK +3", biggest first."""
    from src.player.skill_map import SKILL_ABBREVIATIONS

    parts = sorted((effects or {}).items(), key=lambda kv: -abs(kv[1]))
    return " · ".join(
        f"{SKILL_ABBREVIATIONS.get(k, k.upper())} {'+' if v > 0 else '−'}{abs(v)}"
        for k, v in parts
        if v
    )


def injury_effect(inj: dict | None) -> dict | None:
    """What an injury left for good, for display, from its log row (outcome,
    effects, cap_drop): {"text": "SP −4 · BR −2", "label": "Some lasting
    loss", "dir": "down" | "up" | "even", "title": hover text}. None while
    the player is still out, for injuries from before lasting effects, and
    for a full recovery from anything short of surgery (nothing to say)."""
    if not inj or not inj.get("outcome"):
        return None
    effects = inj.get("effects") or {}
    label = outcome_label(inj["outcome"]) or inj["outcome"]
    t = INJURY_TYPES.get(inj.get("injury_type") or "")
    if not effects:
        if t and t.severity == "surgery":
            return {"text": "", "label": label, "dir": "even", "title": label}
        return None
    total = sum(effects.values())
    direction = "up" if total > 0 else "down" if total < 0 else "even"
    if inj["outcome"] == "full":
        direction = "even"  # a point either way is still a full recovery
    title = label
    if inj.get("cap_drop"):
        title += ". His potential dropped too."
    return {
        "text": effects_text(effects),
        "label": label,
        "dir": direction,
        "title": title,
    }
