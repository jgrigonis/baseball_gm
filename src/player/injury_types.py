# src/player/injury_types.py
"""
The catalog of specific injuries (plans/injury-details.md).

The sim first rolls a severity tier (minor, moderate, severe, surgery), which
sets roughly how long the player is out. Then it picks one injury of that tier
that fits what the player was doing (batting, running, fielding, pitching)
and, for fielders, where they were playing. The injury's own day range, which
sits inside its tier's range, sets the days missed.

Phase 1 is names only: no injury changes a rating yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
