# src/league/owner_messages.py
"""
What owners say, and how they feel (plans/owners.md, "Messages").

GMs only learn what their owner wants from what the owner says, so messages
never show a number. They're built from templates keyed by dimension and
tone, with several wordings each, and picked by what the owner weighs most
and by how far each thing is from what they expected.

Mood is an in-season running read of the same thing the season review
scores: how the season is going for what this owner cares about. Temper sets
how fast it moves. The GM sees it as a word on the owner card.

src/api/services/owner_office.py decides when owners write and stores the
messages.
"""

from __future__ import annotations

import random

from src.league import owners

# ── Mood ─────────────────────────────────────────────────────────────────────
# (lowest mood for the word, word), best first. Mood runs from -1 to 1.
MOODS = (
    (0.45, "thrilled"),
    (0.15, "pleased"),
    (-0.12, "content"),
    (-0.35, "uneasy"),
    (-0.6, "frustrated"),
    (-2.0, "furious"),
)


def mood_word(mood: float) -> str:
    for floor, word in MOODS:
        if mood >= floor:
            return word
    return MOODS[-1][1]


def next_mood(mood: float, reading: float, temper: int) -> float:
    """Mood after a check: part of the way to what the season reads as now.
    A steady owner moves a quarter of the way, a hot-tempered one most of it."""
    step = 0.25 + 0.55 * max(0, min(100, temper)) / 100
    return max(-1.0, min(1.0, mood + step * (reading - mood)))


def tone(score: float | None) -> str:
    if score is None:
        return "ok"
    if score >= 0.25:
        return "good"
    if score <= -0.25:
        return "bad"
    return "ok"


# ── Templates ────────────────────────────────────────────────────────────────
# Fields: {team} (city and name), {budget}, {rival}, {gm}.

PRESEASON_OPEN = (
    "A new season, {gm}. Here's what I expect.",
    "Opening Day's coming. Let me be clear about what I want.",
    "Before we start, here's where I stand.",
    "New year, same standards. Listen up.",
)

# What an owner wants, by dimension, for the preseason memo.
WANTS = {
    "wins": (
        "I want to win ball games. A lot of them.",
        "Win. That's the job.",
        "I expect a winning record. Not a close one.",
    ),
    "postseason": (
        "I want October baseball in this town.",
        "Get us into the playoffs. Anything less is a wasted year.",
        "Rings, {gm}. That's what I'm after.",
    ),
    "profit": (
        "This club has to make money. Don't forget that.",
        "I need us in the black when the books close.",
        "Every dollar you spend comes out of my pocket. Spend like it.",
    ),
    "budget": (
        "You've got {budget} for payroll. Stay under it.",
        "{budget}. That's the payroll. Not a dollar more.",
        "The budget is {budget}, and I mean it.",
    ),
    "attendance": (
        "I want this ballpark full every night.",
        "Empty seats make me sick. Fill them.",
        "Put on a show. I want people in the stands.",
    ),
    "fans": (
        "Give the fans something to cheer about.",
        "This town loves its team. Keep it that way.",
        "The fans are everything. Win them over.",
    ),
    "future": (
        "Don't mortgage the future. I'm in this for the long haul.",
        "Keep the farm stocked. I want to be good for years, not months.",
        "Build something that lasts.",
    ),
    "homegrown": (
        "I want our own kids on the field. Draft well and play them.",
        "Nothing beats a player we raised ourselves.",
        "Grow the talent here. That's how this club does it.",
    ),
    "stars": (
        "Get me a star. Someone people buy tickets to see.",
        "I want names on the marquee.",
        "Stars, {gm}. All-Stars. Award winners.",
    ),
    "icons": (
        "Some players are this franchise. Don't you dare trade them.",
        "Respect the guys who built this club.",
        "Our icons stay. Remember that.",
    ),
    "stability": (
        "No circus. I don't want a new roster every month.",
        "Steady hands. Fewer trades, fewer headlines.",
        "I like a team the fans can recognize from week to week.",
    ),
    "rivalry": (
        "And beat the {rival}. I don't care about anyone else.",
        "Whatever else happens, we beat the {rival}.",
        "Lose to anyone you like. Not the {rival}.",
    ),
}

# Check-ins and the end-of-season review, by dimension and tone.
NOTES = {
    "wins": {
        "good": (
            "We're winning, and I like it.",
            "That record looks good from my box.",
            "Keep stacking wins like this.",
        ),
        "ok": (
            "The record's about what I expected. I expected more, honestly.",
            "We're treading water. I don't pay you to tread water.",
        ),
        "bad": (
            "This losing has to stop.",
            "I've seen enough losses for one year.",
            "What is going on out there? This isn't the team I was promised.",
        ),
    },
    "postseason": {
        "good": (
            "October! This is what it's all about.",
            "Playoff baseball. Now go win some of it.",
        ),
        "ok": (
            "We're on the edge of the race. Get us in.",
            "The playoffs are right there. Don't let them slip.",
        ),
        "bad": (
            "We should be in the race. We're not.",
            "No October again. I'm tired of watching other teams play.",
        ),
    },
    "profit": {
        "good": ("The books look healthy. Good.", "We're making money. Keep it up."),
        "ok": ("The money's fine. Just fine.",),
        "bad": (
            "We're bleeding money. Fix it.",
            "I've looked at the numbers. I don't like them.",
        ),
    },
    "budget": {
        "good": (
            "Payroll's under control. Thank you.",
            "You're living within the budget. Good.",
        ),
        "ok": ("Payroll's right at the line. Watch it.",),
        "bad": (
            "Payroll's over budget. I didn't sign off on that.",
            "You're over the budget I gave you. Not happy.",
            "We are over budget. That ends now.",
        ),
    },
    "attendance": {
        "good": (
            "The park's buzzing. Love it.",
            "Big crowds lately. That's the stuff.",
        ),
        "ok": ("The crowds are OK. OK isn't great.",),
        "bad": ("Too many empty seats.", "Nobody's coming to the ballpark. Why?"),
    },
    "fans": {
        "good": (
            "The town's talking about us again.",
            "The fans are fired up. Keep feeding them.",
        ),
        "ok": ("The fans are waiting for a reason to care.",),
        "bad": (
            "The fans are turning on us.",
            "This town is losing interest. So am I.",
        ),
    },
    "future": {
        "good": (
            "The kids coming up look good. Smart work.",
            "We're set up well for the years ahead.",
        ),
        "ok": ("The future looks... fine. I'd like better than fine.",),
        "bad": (
            "The cupboard's bare. What's the plan for next year?",
            "You're selling off our future. Stop.",
        ),
    },
    "homegrown": {
        "good": (
            "Our own kids are carrying this team. That's what I want.",
            "Love seeing players we drafted out there.",
        ),
        "ok": ("I'd like to see more of our own on the field.",),
        "bad": (
            "Where are our draft picks? I want our own players out there.",
            "This roster could belong to anyone. Where are our kids?",
        ),
    },
    "stars": {
        "good": ("Now that's star power.", "People are coming to see our stars."),
        "ok": ("We could use a real star.",),
        "bad": (
            "Nobody outside this town knows a single player on this team.",
            "Where are the stars? I want names.",
        ),
    },
    "icons": {
        "good": ("Good to see the core still here.",),
        "ok": ("Treat our veterans right.",),
        "bad": (
            "You let one of our icons go. I won't forget that.",
            "Trading a franchise player? Without asking me?",
        ),
    },
    "stability": {
        "good": ("Nice and steady. Just how I like it.",),
        "ok": ("Easy on the trades.",),
        "bad": (
            "Another trade? I can't keep track of who plays for us.",
            "This roster's a revolving door. Enough.",
        ),
    },
    "rivalry": {
        "good": (
            "We own the {rival}. Beautiful.",
            "Beating the {rival} never gets old.",
        ),
        "ok": ("Even with the {rival} isn't good enough.",),
        "bad": (
            "We keep losing to the {rival}. Unacceptable.",
            "The {rival}?! Again?!",
        ),
    },
}

# Check-in openers. Only a few use the GM's name, and a check-in never opens
# the way one of the owner's last few did (checkin's recent).
CHECKIN_OPEN = {
    "good": (
        "Quick note.",
        "Checking in.",
        "Good stuff so far.",
        "I like what I'm seeing.",
        "Keep it rolling.",
        "Nice work, {gm}.",
        "Just a quick one.",
        "Things are looking up.",
    ),
    "ok": (
        "Checking in.",
        "Let's talk.",
        "Got a minute?",
        "Here's where I'm at.",
        "A few thoughts.",
        "So far, so-so.",
        "Quick update from upstairs.",
        "A word, {gm}.",
    ),
    "bad": (
        "We need to talk.",
        "{gm}. My office. Now.",
        "I'm not happy.",
        "This isn't working.",
        "I expected better.",
        "Something has to change.",
        "I've been watching. I don't like it.",
        "Close the door.",
    ),
}

# End-of-season review: the verdict, by job security band.
REVIEW_CLOSE = {
    "safe": (
        "Good year. Keep this up and you'll be here a long time.",
        "You've earned my trust. Don't lose it.",
        "I'm happy with where this is going.",
    ),
    "fine": (
        "We'll go again next year. I expect more.",
        "Not bad. Not good enough, either.",
        "You've got my support. For now.",
    ),
    "warned": (
        "One more like this and we'll be talking about your future.",
        "You're on thin ice. I mean that.",
        "I'm running out of patience with you.",
    ),
}

REVIEW_OPEN = {
    "good": ("What a season.", "Now that's a season.", "Well done this year."),
    "ok": ("The season's over. Here's my take.", "Let's look back at the year."),
    "bad": ("That was not good enough.", "What a disappointment.", "I've seen better."),
}

# A reaction to a move: a trade, or losing an icon.
TRADE_REACTIONS = {
    "icons": (
        "You traded away one of our icons. I hope you know what you're doing.",
        "That player was this franchise. I'm stunned.",
    ),
    "stability": (
        "Another trade. I'd like a roster I recognize.",
        "Easy on the phone, {gm}.",
    ),
    "future": (
        "Did we just give away our future? Explain that to me.",
        "I hope that trade doesn't cost us in three years.",
    ),
    "stars": (
        "Now that's a name. Good move.",
        "Finally, someone people have heard of.",
    ),
}

OVER_BUDGET = (
    "Payroll just went over the budget I gave you. I didn't sign off on that.",
    "We're over budget. I gave you a number for a reason. Fix it.",
    "{budget} was the number. You're past it.",
)


def _fill(text: str, fields: dict) -> str:
    try:
        return text.format(**fields)
    except KeyError, IndexError:
        return text


def _pick(rng: random.Random, options: tuple[str, ...], fields: dict) -> str:
    return _fill(rng.choice(options), fields)


def _speakable(weights: dict, fields: dict, money: bool) -> list[str]:
    """The owner's top dimensions they can talk about here: no money talk
    without budgets, no rival talk without a rival."""
    skip = set() if money else {"profit", "budget", "attendance", "fans"}
    if not fields.get("rival"):
        skip.add("rivalry")
    return [k for k in owners.top_dimensions(weights, 12) if k not in skip]


def preseason(
    weights: dict, fields: dict, rng: random.Random, money: bool = True
) -> str:
    """The preseason memo: the owner's top two or three wants."""
    top = _speakable(weights, fields, money)[:3]
    lines = [_pick(rng, PRESEASON_OPEN, fields)]
    lines += [_pick(rng, WANTS[k], fields) for k in top]
    if money and fields.get("budget") and "budget" not in top:
        lines.append(_fill("Your payroll budget is {budget}.", fields))
    return " ".join(lines)


def _notes(
    scores: dict, weights: dict, fields: dict, rng: random.Random, n: int, money: bool
) -> tuple[str, list[str]]:
    """The overall tone and a line on each of the n dimensions furthest from
    target, among those the owner cares about most."""
    w = owners.clean_weights(weights)
    keys = [
        k for k in _speakable(weights, fields, money)[:6] if scores.get(k) is not None
    ]
    keys.sort(key=lambda k: -abs(scores[k]) * w[k])
    lines = [_pick(rng, NOTES[k][tone(scores[k])], fields) for k in keys[:n]]
    total = sum(w[k] * scores[k] for k in keys) / (sum(w[k] for k in keys) or 1)
    return tone(total), lines


def checkin(
    scores: dict,
    weights: dict,
    fields: dict,
    rng: random.Random,
    money: bool = True,
    recent: list[str] | tuple[str, ...] = (),
) -> str:
    """A mid-season check-in. recent: the owner's last few messages, so the
    opener doesn't repeat one of theirs."""
    feel, lines = _notes(scores, weights, fields, rng, 2, money)
    fresh = tuple(
        o
        for o in CHECKIN_OPEN[feel]
        if not any(r.startswith(_fill(o, fields)) for r in recent)
    )
    return " ".join([_pick(rng, fresh or CHECKIN_OPEN[feel], fields), *lines])


def review(
    scores: dict,
    weights: dict,
    fields: dict,
    band: str,
    rng: random.Random,
    money: bool = True,
) -> str:
    """The end-of-season review: the verdict, the best and worst of what the
    owner cares about, and how safe the GM's job is, all without numbers."""
    feel, lines = _notes(scores, weights, fields, rng, 3, money)
    return " ".join(
        [
            _pick(rng, REVIEW_OPEN[feel], fields),
            *lines,
            _pick(rng, REVIEW_CLOSE[band], fields),
        ]
    )


def trade_reaction(key: str, fields: dict, rng: random.Random) -> str:
    return _pick(rng, TRADE_REACTIONS[key], fields)


def over_budget(fields: dict, rng: random.Random) -> str:
    return _pick(rng, OVER_BUDGET, fields)
