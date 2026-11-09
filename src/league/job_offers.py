# src/league/job_offers.py
"""
Job offers for a fired GM (plans/owners.md, "Applying for jobs after a
firing", Josh 2026-11-07). The pure part: src/api/services/job_offers.py
gathers the league and stores the offers.

A fired person doesn't just pick any team. Owners decide whether to offer
them a job, often by letting their own AI GM go:

- The GM's reputation (0 to 100) comes from their seasons under owners in
  this league: the average season score, titles and playoff runs, less a
  mark for each firing (the newest one hurts most).
- A job's appeal (0 to 100) comes from the team's strength now and in two
  years, and its market. Strong teams in big markets are the hardest to land.
- The owner's bar starts at the job's appeal. Ambitious owners want a proven
  winner (higher), patient ones give a reclamation project a shot (lower),
  and an owner unhappy with their AI GM is keen to hire (lower still); one
  whose AI GM is safe isn't looking.
- An owner offers when the GM's reputation clears their bar. Someone always
  offers: with no offer otherwise, the owner whose bar is lowest calls anyway.

Offers come in the owner's voice, by archetype. No numbers are ever shown.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from src.league import owners

# ── Reputation ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Record:
    """One season a GM had under an owner."""

    score: float
    made_playoffs: bool = False
    champion: bool = False


def reputation(seasons: list[Record], firings_ago: list[int]) -> int:
    """How owners see a GM, 0 to 100. firings_ago: for each time they were
    fired, how many seasons ago (0: this offseason). A GM with few seasons
    is pulled toward the middle: one great year isn't a career."""
    n = len(seasons)
    avg = sum(s.score for s in seasons) / (n + 1)
    rep = 50 + 35 * avg
    rep += 10 * sum(s.champion for s in seasons)
    rep += 3 * sum(s.made_playoffs for s in seasons)
    for ago in firings_ago:
        rep -= max(0, 15 - 5 * ago)
    return int(round(max(0, min(100, rep))))


# ── The job and the owner's bar ──────────────────────────────────────────────


def appeal(rank_now: float, rank_future: float, market: int) -> int:
    """How attractive the job is, 0 to 100. Ranks run 0 (best) to 1."""
    a = 100 * (1 - 0.6 * rank_now - 0.3 * rank_future) + 5 * (market - 3)
    return int(round(max(0, min(100, a))))


def bar(job_appeal: int, traits: dict, ai_security: int | None) -> float:
    """The reputation an owner wants before offering this job. ai_security:
    their AI GM's job security after the last review (None: not judged yet,
    taken as middling)."""
    t = owners.clean_traits(traits)
    b = job_appeal + 0.3 * (t["ambition"] - 50) - 0.25 * (t["patience"] - 50)
    security = 50 if ai_security is None else ai_security
    # Below 50 the owner wants a change; above it, they're happy as is.
    b += 0.6 * (security - 50)
    return b


@dataclass(frozen=True)
class Job:
    team_id: str
    archetype: str
    bar: float


def choose(jobs: list[Job], rep: int) -> tuple[list[str], bool]:
    """The teams whose owners offer the GM a job, and whether the only offer
    is the one someone always makes (no owner's bar was cleared)."""
    offers = [j.team_id for j in jobs if rep >= j.bar]
    if offers or not jobs:
        return offers, False
    keenest = min(jobs, key=lambda j: (j.bar, j.team_id))
    return [keenest.team_id], True


# ── What the owner says ──────────────────────────────────────────────────────

PITCH = {
    "The Tycoon": (
        "I want a ring, and I'll pay for it. Can you win now?",
        "Money's no object here. Titles are. Interested?",
    ),
    "The Penny-Pincher": (
        "I need someone who can win without breaking the bank.",
        "Keep the books in the black and we'll get along fine.",
    ),
    "The Hometown Owner": (
        "Our own kids are the future. Help me build around them.",
        "This club means everything to this town. Come take care of it.",
    ),
    "The Showman": (
        "Fill my ballpark and the job's yours.",
        "I want names on the marquee. Can you get me some?",
    ),
    "The Long-Gamer": (
        "There's no rush here. Build something that lasts.",
        "I think in decades. If you do too, let's talk.",
    ),
    "The Corporate Board": (
        "The board wants steady and sensible. Are you interested?",
        "We're looking for a safe pair of hands.",
    ),
    "The Grudge Holder": (
        "There's one team I need to beat. Help me do it.",
        "Win or lose, just beat our rival. Can you do that?",
    ),
    "The People's Owner": (
        "Our fans deserve better. Give them a reason to come out.",
        "This is the fans' team. Run it like it.",
    ),
    "The Absentee": (
        "Run it how you like. Just keep the money right.",
        "I won't be calling much. The job's there if you want it.",
    ),
    "The Meddler": (
        "I'll have plenty of ideas. Can you work with that?",
        "I like to be involved. If that suits you, the job's yours.",
    ),
}
DEFAULT_PITCH = ("We're looking for a new GM. Interested?",)

FIT = {
    "proven": (
        "Your record speaks for itself.",
        "I've watched what you can do.",
    ),
    "chance": (
        "You've had a rough patch, but I'm willing to take a chance.",
        "Everyone deserves a second shot.",
    ),
    "only": (
        "Nobody else is calling, I know. I'm willing to give you a shot anyway.",
        "It's not the glamour job, but it's a job.",
    ),
}


def message(
    archetype: str, rep: int, job_appeal: int, only: bool, rng: random.Random
) -> str:
    """The owner's offer, in their voice."""
    pitch = rng.choice(PITCH.get(archetype, DEFAULT_PITCH))
    fit = "only" if only else "proven" if rep >= job_appeal else "chance"
    return f"{rng.choice(FIT[fit])} {pitch}"
