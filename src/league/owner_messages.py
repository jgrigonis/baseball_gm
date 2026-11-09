# src/league/owner_messages.py
"""
What owners say, and how they feel (plans/owners.md, "Messages").

GMs only learn what their owner wants from what the owner says, so messages
never show the owner's targets or scores. They do point at public facts (the
record, the trades, payroll against the owner's budget) so the GM knows what
the owner is reacting to. They're built from templates keyed by dimension
and tone, with several wordings each, and picked by what the owner weighs
most and by how far each thing is from what they expected. A check-in opens
in the owner's mood (the word on the owner card) and leads with what explains
it; anything running the other way is one short aside at the end.

Mood is an in-season running read of the same thing the season review
scores: how the season is going for what this owner cares about. Temper sets
how fast it moves. The GM sees it as a word on the owner card.

src/api/services/owner_office.py decides when owners write and stores the
messages.
"""

from __future__ import annotations

import random

from src.league import owners
from src.player.contracts import format_salary

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

# Check-in openers, by the owner's mood word, so a check-in opens the way the
# owner card says they feel. Only a few use the GM's name, and a check-in
# never opens the way one of the owner's last few did (checkin's recent).
CHECKIN_OPEN = {
    "thrilled": (
        "This is the season I've been waiting for.",
        "I couldn't be happier, {gm}.",
        "Now this is fun.",
        "Keep it rolling.",
        "What a year this is turning into.",
    ),
    "pleased": (
        "Good stuff so far.",
        "I like what I'm seeing.",
        "Things are looking up.",
        "Nice work, {gm}.",
        "Quick note. A good one.",
    ),
    "content": (
        "Checking in.",
        "Quick update from upstairs.",
        "Here's where I'm at.",
        "A few thoughts.",
        "Got a minute?",
        "A word, {gm}.",
    ),
    "uneasy": (
        "Something's bothering me.",
        "I've got a few worries.",
        "I'm starting to wonder about this season.",
        "We should talk, {gm}.",
        "I don't love what I'm seeing.",
    ),
    "frustrated": (
        "We need to talk.",
        "I'm not happy.",
        "This isn't working.",
        "I expected better.",
        "I've been watching. I don't like it.",
    ),
    "furious": (
        "{gm}. My office. Now.",
        "Close the door.",
        "Something has to change. Today.",
        "I've had it.",
    ),
}

# When the latest news runs against the mood (mood moves slowly), the opener
# says so instead, so "I'm uneasy" doesn't sit next to nothing but praise.
CHECKIN_TURN = {
    "up": (
        "Better lately. I'm not sold yet.",
        "Things are turning around. Keep going.",
        "You've got my attention again. In a good way, for once.",
    ),
    "down": (
        "I was happy with this team. Lately, less so.",
        "We were rolling. Now I'm not so sure.",
        "Don't let a good start go to waste.",
    ),
}

# How each mood word leans: up, flat or down.
LEAN = {
    "thrilled": 1,
    "pleased": 1,
    "content": 0,
    "uneasy": -1,
    "frustrated": -1,
    "furious": -1,
}

# A short word on something that runs against the owner's overall feeling:
# "good" for the bright spot in a bad stretch, "bad" for the worry in a good
# one. Said last, so the message still lands where the mood is.
ASIDES = {
    "wins": {
        "good": "At least we're winning games.",
        "bad": "But we have to win more than this.",
    },
    "postseason": {
        "good": "At least we're in the playoff picture.",
        "bad": "But I want October, and we're not on track for it.",
    },
    "profit": {
        "good": "At least the books look fine.",
        "bad": "But watch the money. We're spending more than we make.",
    },
    "attendance": {
        "good": "At least people are coming to the park.",
        "bad": "But I'd like more people in the seats.",
    },
    "fans": {
        "good": "At least the fans are with us.",
        "bad": "But the fans are cooling on us.",
    },
    "future": {
        "good": "At least the kids coming up look good.",
        "bad": "But I worry about the next few years.",
    },
    "homegrown": {
        "good": "At least our own kids are getting their chance.",
        "bad": "But I'd like to see more of our own players.",
    },
    "stars": {
        "good": "At least we've got names people know.",
        "bad": "But we could use a real star.",
    },
    "icons": {
        "good": "At least the core's still here.",
        "bad": "But I haven't forgotten the icon you let go.",
    },
    "stability": {
        "good": "At least you've kept the roster steady.",
        "bad": "But go easy on the trades.",
    },
    "rivalry": {
        "good": "At least we're handling the {rival}.",
        "bad": "But I'm sick of losing to the {rival}.",
    },
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
    # The owner fires the GM (src/api/services/firing.py).
    "fired": (
        "I'm making a change. Thank you for your work, {gm}, but you're done here.",
        "We're going in a different direction. Clean out your desk.",
        "This was your last season as GM of the {team}.",
        "I've run out of patience. You're fired.",
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
    "Payroll's at {payroll}. I gave you {budget} for players. I didn't sign off on that.",
    "We're over budget: {payroll} in payroll against the {budget} I gave you. Fix it.",
    "{budget} was the number for payroll. You're at {payroll}.",
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
    skip = set() if money else {"profit", "attendance", "fans"}
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
    if money and fields.get("budget"):
        lines.append(_fill("Your payroll budget is {budget}.", fields))
    return " ".join(lines)


_COUNTS = ("No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight")


def _count(n: int, thing: str) -> str:
    word = _COUNTS[n] if n < len(_COUNTS) else str(n)
    return f"{word} {thing}{'' if n == 1 else 's'}"


def facts(
    season: dict | None,
    payroll: int | None = None,
    payroll_budget: int | None = None,
    final: bool = False,
) -> dict:
    """What an owner can point at when they talk: the record, the trades,
    the series with the rival, payroll against what they gave for it, and
    whether the books are in the red. Public facts, never the owner's own
    targets or scores. season: a TeamSeason as a dict (owner_scoring)."""
    s = season or {}
    out: dict = {"final": final}
    w, l = s.get("wins") or 0, s.get("losses") or 0
    if w or l:
        out["record"] = f"{w}-{l}"
    out["trades"] = s.get("trades")
    rw, rl = s.get("rival_wins") or 0, s.get("rival_losses") or 0
    if rw or rl:
        out["rival_record"] = f"{rw}-{rl}"
    out["profit"] = s.get("profit")
    if payroll is not None and payroll_budget and payroll > payroll_budget:
        out["over_budget"] = True
        out["payroll"] = format_salary(payroll)
        out["payroll_budget"] = format_salary(payroll_budget)
    return out


def _context(key: str, t: str, f: dict, fields: dict, used: set) -> str:
    """The fact a line on this dimension is about, to say before it, or "".
    used: facts already said in this message."""
    final = f.get("final")
    if key in ("wins", "postseason") and f.get("record") and "record" not in used:
        used.add("record")
        return f"We finished {f['record']}." if final else f"We're {f['record']}."
    if key == "stability" and f.get("trades") is not None:
        n = f["trades"]
        if final:
            return f"{_count(n, 'trade')} this year."
        return f"{_count(n, 'trade')} so far." if n else "No trades so far."
    if key == "rivalry" and f.get("rival_record") and fields.get("rival"):
        verb = "went" if final else "are"
        return f"We {verb} {f['rival_record']} against the {fields['rival']}."
    if key == "profit":
        if f.get("over_budget") and not final:
            return (
                f"Payroll's at {f['payroll']}. I gave you {f['payroll_budget']} "
                "for players."
            )
        profit = f.get("profit")
        if profit is not None and profit < 0:
            return (
                "We lost money this year."
                if final
                else "At this payroll, we lose money this year."
            )
        if profit is not None and profit > 0 and t == "good":
            return (
                "We made money this year."
                if final
                else "We're on pace to turn a profit."
            )
    return ""


def _choose(
    scores: dict, weights: dict, fields: dict, n: int, money: bool, lean: int | None
) -> tuple[str, int, list[str]]:
    """The overall tone, the way the message leans, and the n dimensions to
    talk about, among the six the owner weighs most. The first is what most
    explains the owner's feeling: the worst of it when they lean down, the
    best when they lean up, the biggest either way when flat (lean None:
    read the lean from these scores)."""
    w = owners.clean_weights(weights)
    keys = [
        k for k in _speakable(weights, fields, money)[:6] if scores.get(k) is not None
    ]
    total = sum(w[k] * scores[k] for k in keys) / (sum(w[k] for k in keys) or 1)
    feel = tone(total)
    if lean is None:
        lean = _LEAN_OF_TONE[feel]

    def impact(k):
        return scores[k] * w[k]

    if lean < 0:
        keys.sort(key=impact)
    elif lean > 0:
        keys.sort(key=lambda k: -impact(k))
    else:
        keys.sort(key=lambda k: -abs(impact(k)))
    return feel, lean, keys[:n]


_LEAN_OF_TONE = {"good": 1, "ok": 0, "bad": -1}


def _notes(
    scores: dict,
    weights: dict,
    fields: dict,
    rng: random.Random,
    n: int,
    money: bool,
    lean: int | None = None,
    season: dict | None = None,
) -> tuple[str, list[str], list[str]]:
    """The overall tone, up to n lines on what the owner cares about most,
    and their tones, told so they agree with each other and with how the
    owner feels (_choose). Each line says the fact it's about when there is
    one (season: facts()). A line that runs against the message's direction
    becomes one short aside ("At least...", "But..."), said last."""
    feel, lean, keys = _choose(scores, weights, fields, n, money, lean)
    if not keys:
        return feel, [], []
    # The message's direction: the lead line's, or the mood's when the lead
    # is middling. (Mood runs behind the news, so the lead can run against
    # it when everything does; checkin's opener then says things turned.)
    way = _LEAN_OF_TONE[tone(scores[keys[0]])] or lean
    against = "good" if way < 0 else "bad" if way > 0 else None
    f = season or {}
    used: set = set()
    lines, asides, tones = [], [], []
    for i, k in enumerate(keys):
        t = tone(scores[k])
        if i and t == against:
            if not asides:
                asides.append(_fill(ASIDES[k][t], fields))
                tones.append(t)
            continue
        line = _pick(rng, NOTES[k][t], fields)
        said = _context(k, t, f, fields, used)
        lines.append(f"{said} {line}" if said else line)
        tones.insert(len(lines) - 1, t)
    return feel, lines + asides, tones


def checkin(
    scores: dict,
    weights: dict,
    fields: dict,
    rng: random.Random,
    money: bool = True,
    recent: list[str] | tuple[str, ...] = (),
    mood: float | None = None,
    season: dict | None = None,
) -> str:
    """A mid-season check-in. mood: the owner's mood now, so the opener
    matches the word on the owner card (None: read from these scores).
    season: facts() for the lines to point at. recent: the owner's last few
    messages, so the opener doesn't repeat one of theirs."""
    word = mood_word(mood) if mood is not None else None
    lean = LEAN[word] if word else None
    feel, lines, tones = _notes(scores, weights, fields, rng, 2, money, lean, season)
    if word is None:
        word = {"good": "pleased", "ok": "content", "bad": "frustrated"}[feel]
    openers = CHECKIN_OPEN[word]
    # Mood runs behind the news. When nothing said runs the mood's way, the
    # opener says things have turned instead.
    if lean and lean < 0 and "good" in tones and "bad" not in tones:
        openers = CHECKIN_TURN["up"]
    elif lean and lean > 0 and "bad" in tones and "good" not in tones:
        openers = CHECKIN_TURN["down"]
    fresh = tuple(
        o for o in openers if not any(r.startswith(_fill(o, fields)) for r in recent)
    )
    return " ".join([_pick(rng, fresh or openers, fields), *lines])


def review(
    scores: dict,
    weights: dict,
    fields: dict,
    band: str,
    rng: random.Random,
    money: bool = True,
    season: dict | None = None,
) -> str:
    """The end-of-season review: the verdict, the best and worst of what the
    owner cares about, and how safe the GM's job is, without the owner's
    targets or scores. season: facts(final=True) for the lines to point at."""
    feel, lines, _ = _notes(scores, weights, fields, rng, 3, money, None, season)
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
