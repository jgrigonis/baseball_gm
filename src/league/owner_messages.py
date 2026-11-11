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
import re

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

# The opener when the owner is writing to a GM for the first time.
PRESEASON_WELCOME = (
    "Welcome to the {team}, {gm}. Here's what I expect.",
    "Glad to have you, {gm}. Let me tell you how this club works.",
    "Welcome aboard, {gm}. Before you do anything, hear me out.",
    "So you're my new GM. Here's what I want from you.",
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
        "ok": (
            "The money's fine. Just fine.",
            "The books are holding steady. Nothing to celebrate.",
        ),
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
        "ok": (
            "The crowds are OK. OK isn't great.",
            "Decent crowds. I want packed ones.",
        ),
        "bad": ("Too many empty seats.", "Nobody's coming to the ballpark. Why?"),
    },
    "fans": {
        "good": (
            "The town's talking about us again.",
            "The fans are fired up. Keep feeding them.",
        ),
        "ok": (
            "The fans are waiting for a reason to care.",
            "The town's lukewarm on us. Give them something.",
        ),
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
        "ok": (
            "The future looks... fine. I'd like better than fine.",
            "The farm's thin in spots. Keep an eye on it.",
        ),
        "bad": (
            "The cupboard's bare. What's the plan for next year?",
            "You're selling off our future. Stop.",
        ),
    },
    "homegrown": {
        "good": (
            "Our own kids are carrying this team. That's what I want.",
            "Love seeing players we drafted out there.",
            "This is a team we built ourselves. I'm proud of that.",
        ),
        "ok": (
            "I'd like to see more of our own on the field.",
            "A few more of our draft picks out there wouldn't hurt.",
        ),
        "bad": (
            "Where are our draft picks? I want our own players out there.",
            "This roster could belong to anyone. Where are our kids?",
        ),
    },
    "stars": {
        "good": ("Now that's star power.", "People are coming to see our stars."),
        "ok": (
            "We could use a real star.",
            "We've got good players. I want a great one.",
        ),
        "bad": (
            "Nobody outside this town knows a single player on this team.",
            "Where are the stars? I want names.",
        ),
    },
    "icons": {
        "good": (
            "Good to see the core still here.",
            "The guys who built this club are still wearing our uniform. Good.",
        ),
        "ok": (
            "Treat our veterans right.",
            "Look after the players who've been here the longest.",
        ),
        "bad": (
            "You let one of our icons go. I won't forget that.",
            "Trading a franchise player? Without asking me?",
        ),
    },
    "stability": {
        "good": (
            "Nice and steady. Just how I like it.",
            "Same faces every week. The fans like that, and so do I.",
        ),
        "ok": (
            "Easy on the trades.",
            "Let this group settle in before you make more moves.",
        ),
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
        "ok": (
            "Even with the {rival} isn't good enough.",
            "Splitting with the {rival} doesn't cut it.",
        ),
        "bad": (
            "We keep losing to the {rival}. Unacceptable.",
            "The {rival}?! Again?!",
        ),
    },
}

# A topic the owner already raised this season, when nothing about it has
# changed but it's still what explains their mood: a short callback, without
# saying the same fact again.
AGAIN = {
    "wins": {
        "good": (
            "Still winning. Still happy about it.",
            "The wins keep coming.",
            "Keep that record pointed up.",
        ),
        "ok": ("Still a middling record.", "Still treading water."),
        "bad": ("Still losing too much.", "The losing hasn't stopped."),
    },
    "postseason": {
        "good": ("Still in the playoff picture.", "Keep us in the October hunt."),
        "ok": ("Still on the edge of the race.", "The race is still right there."),
        "bad": ("Still not in the race.", "October's still slipping away."),
    },
    "profit": {
        "good": ("The books still look good.", "Still making money. Good."),
        "ok": ("The money's still fine.", "Books are still about even."),
        "bad": ("The money still worries me.", "I haven't forgotten the books."),
    },
    "attendance": {
        "good": ("The crowds are still great.", "Still a full house most nights."),
        "ok": ("The crowds are still just OK.", "Still room in the stands."),
        "bad": ("Still too many empty seats.", "The seats are still empty."),
    },
    "fans": {
        "good": ("The fans are still with us.", "This town's still buzzing."),
        "ok": ("The fans are still waiting on us.", "The town's still lukewarm."),
        "bad": ("The fans are still cool on us.", "We're still losing the town."),
    },
    "future": {
        "good": ("The farm still looks good.", "The kids are still coming along."),
        "ok": ("The farm's still just fine.", "The farm could still use help."),
        "bad": (
            "I'm still worried about the next few years.",
            "The farm's still thin.",
        ),
    },
    "homegrown": {
        "good": (
            "Still love how many of our own kids are out there.",
            "Our homegrown core is still the heart of this team.",
            "Still a roster full of our own draft picks. Keep it that way.",
        ),
        "ok": (
            "I'd still like a few more of our own out there.",
            "Still room for more of our draft picks.",
        ),
        "bad": (
            "Still not enough of our own players on this roster.",
            "I'm still waiting to see more of our draft picks.",
        ),
    },
    "stars": {
        "good": (
            "Our stars are still drawing people in.",
            "Still love the star power.",
            "People still come to see our big names.",
        ),
        "ok": ("We still need a real star.", "Still waiting on a star."),
        "bad": ("Still no stars on this team.", "Still no names people know."),
    },
    "icons": {
        "good": ("The core's still here. Good.", "Glad the old guard's still here."),
        "ok": (
            "Keep treating the veterans right.",
            "Remember who built this club.",
        ),
        "bad": (
            "I still haven't forgotten that icon you let go.",
            "I'm still sore about losing that icon.",
        ),
    },
    "stability": {
        "good": ("Still nice and steady.", "Still the same faces. Good."),
        "ok": ("Still easy on the trades, please.", "Keep the trades to a minimum."),
        "bad": ("Still too many trades.", "The trades still haven't stopped."),
    },
    "rivalry": {
        "good": (
            "Still handling the {rival}. Good.",
            "The {rival} still can't beat us.",
        ),
        "ok": (
            "Still even with the {rival}. Not good enough.",
            "I still want more against the {rival}.",
        ),
        "bad": ("Still losing to the {rival}.", "The {rival} still have our number."),
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
        "bad": "But I'd like to see more players we drafted on this roster.",
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


def _pick(rng: random.Random, options: tuple[str, ...], fields: dict, avoid=()) -> str:
    """One of the options, filled. avoid: earlier messages; a wording one of
    them already used is picked only when every wording has been."""
    fresh = tuple(o for o in options if not any(_fill(o, fields) in b for b in avoid))
    return _fill(rng.choice(fresh or options), fields)


def _speakable(weights: dict, fields: dict, money: bool) -> list[str]:
    """The owner's top dimensions they can talk about here: no money talk
    without budgets, no rival talk without a rival."""
    skip = set() if money else {"profit", "attendance", "fans"}
    if not fields.get("rival"):
        skip.add("rivalry")
    return [k for k in owners.top_dimensions(weights, 12) if k not in skip]


def preseason(
    weights: dict,
    fields: dict,
    rng: random.Random,
    money: bool = True,
    first: bool = False,
) -> str:
    """The preseason memo: the owner's top two or three wants. first: the
    owner's first word to this GM, so it opens with a welcome."""
    top = _speakable(weights, fields, money)[:3]
    lines = [_pick(rng, PRESEASON_WELCOME if first else PRESEASON_OPEN, fields)]
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
    whether the books are in the red, how many players on the 40-man roster
    came through the team's own draft (and what most teams have). Public
    facts, never the owner's own targets or scores. season: a TeamSeason
    as a dict (owner_scoring)."""
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
    if s.get("roster_players"):
        mine, n = s.get("homegrown_players") or 0, s["roster_players"]
        out["homegrown"] = mine
        out["roster"] = n
        if s.get("league_homegrown") is not None:
            out["homegrown_avg"] = round(s["league_homegrown"] * n)
    if payroll is not None and payroll_budget and payroll > payroll_budget:
        out["over_budget"] = True
        out["payroll"] = format_salary(payroll)
        out["payroll_budget"] = format_salary(payroll_budget)
    return out


def _word(n: int) -> str:
    return _COUNTS[n].lower() if n < len(_COUNTS) else str(n)


def _homegrown(f: dict, t: str = "bad") -> str:
    """How many of the 40-man roster the team drafted itself, against what
    most teams have: "Only two of our 39 players came through our own
    draft. Most teams have about seven." t: the line's tone. "Only" is for
    a real shortfall (a bad line); within a player or two of most teams it
    says so instead of sounding short."""
    mine, n, avg = f["homegrown"], f["roster"], f.get("homegrown_avg")
    if not mine:
        return "Not one player on our 40-man roster came through our own draft."
    if avg is not None and abs(mine - avg) <= max(1, n // 20):
        return (
            f"{_word(mine).capitalize()} of our {n} players came through our own"
            " draft, about what most teams have."
        )
    if avg is not None and mine < avg and t == "bad":
        text = f"Only {_word(mine)} of our {n} players came through our own draft."
    else:
        text = (
            f"{_word(mine).capitalize()} of our {n} players came through our own draft."
        )
    if avg is not None and avg != mine:
        text += f" Most teams have about {_word(avg)}."
    return text


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
    if key == "homegrown" and f.get("roster") and "homegrown" not in used:
        used.add("homegrown")
        return _homegrown(f, t)
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


def _number(word: str) -> int | None:
    if word.isdigit():
        return int(word)
    words = [c.lower() for c in _COUNTS]
    return words.index(word.lower()) if word.lower() in words else None


def _games(record: str | None) -> int | None:
    if not record:
        return None
    w, l = record.split("-")
    return int(w) + int(l)


def _said_tone(key: str, body: str, fields: dict) -> str | None:
    """The tone of the line this message said on this dimension, or None if
    it didn't talk about it."""
    for t in ("good", "ok", "bad"):
        lines = NOTES[key].get(t, ()) + AGAIN[key].get(t, ())
        aside = ASIDES[key].get(t)
        if aside:
            lines += (aside,)
        if any(_fill(line, fields) in body for line in lines):
            return t
    return None


def _old_fact(key: str, f: dict, fields: dict, earlier):
    """The newest earlier value of the fact behind this dimension, or None
    if no earlier message said it."""
    for body in earlier:
        if key in ("wins", "postseason"):
            m = re.search(r"We're (\d+-\d+)\.", body)
            old = _games(m[1]) if m else None
        elif key == "homegrown":
            m = re.search(r"(\w+) of our \d+ players came through our own draft", body)
            old = _number(m[1]) if m else None
            if "Not one player on our 40-man roster" in body:
                old = 0
        elif key == "stability":
            m = re.search(r"(\w+) trades? so far", body)
            old = _number(m[1]) if m else None
        elif key == "rivalry":
            m = re.search(r"We are (\d+-\d+) against", body)
            old = _games(m[1]) if m else None
        elif key == "profit":
            m = re.search(r"Payroll's at (\S+)\. I gave you", body)
            old = m[1] if m else None
        else:
            return None
        if old is not None:
            return old
    return None


def _moved(key: str, f: dict, fields: dict, earlier) -> bool:
    """Whether the fact behind this dimension changed enough since the owner
    last said it to be worth saying again."""
    old = _old_fact(key, f, fields, earlier)
    if old is None:
        return False
    if key in ("wins", "postseason"):
        now = _games(f.get("record"))
        return now is not None and now - old >= 10
    if key == "homegrown" and f.get("roster"):
        avg = f.get("homegrown_avg")
        crossed = avg is not None and (old < avg) != (f["homegrown"] < avg)
        return crossed or abs(f["homegrown"] - old) >= 2
    if key == "stability" and f.get("trades") is not None:
        return old != f["trades"]
    if key == "rivalry" and f.get("rival_record"):
        return _games(f["rival_record"]) - old >= 3
    if key == "profit" and f.get("over_budget"):
        return old != f["payroll"]
    return False


def _stale(keys: list[str], scores: dict, f: dict, fields: dict, earlier) -> set[str]:
    """The dimensions the owner already talked about this season (earlier:
    their earlier check-ins, newest first) in the same tone, with nothing
    about them changed enough since to say again."""
    out = {}
    for k in keys:
        for i, body in enumerate(earlier):
            said = _said_tone(k, body, fields)
            if said is None:
                continue
            if said == tone(scores[k]) and not _moved(k, f, fields, earlier):
                out[k] = i
            break
    return out


def _rotate(keys: list[str], scores: dict, stale: dict, n: int) -> list[str]:
    """The n dimensions to talk about: fresh ones before ones the owner
    already raised, and of those, the one raised longest ago first (stale:
    how many check-ins back each was last said). The lead still explains
    the mood: a dimension in the same tone takes it, fresh before stale."""
    if not keys or not stale:
        return keys[:n]

    def order(k):
        return (k in stale, -stale.get(k, 0))

    want = tone(scores[keys[0]])
    same = sorted((k for k in keys if tone(scores[k]) == want), key=order)
    lead = same[0]
    rest = sorted((k for k in keys if k != lead), key=order)
    return [lead, *rest][:n]


def _choose(
    scores: dict, weights: dict, fields: dict, money: bool, lean: int | None
) -> tuple[str, int, list[str]]:
    """The overall tone, the way the message leans, and the dimensions to
    talk about, in order, among the six the owner weighs most. The first is what most
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
    return feel, lean, keys


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
    earlier: list[str] | tuple[str, ...] = (),
) -> tuple[str, list[str], list[str]]:
    """The overall tone, up to n lines on what the owner cares about most,
    and their tones, told so they agree with each other and with how the
    owner feels (_choose). Each line says the fact it's about when there is
    one (season: facts()). A line that runs against the message's direction
    becomes one short aside ("At least...", "But..."), said last.

    earlier: the owner's earlier check-ins this season, newest first. The
    message rotates away from what those already said, and a dimension it
    comes back to without news is a short callback (AGAIN), not the same
    fact again."""
    feel, lean, keys = _choose(scores, weights, fields, money, lean)
    f = season or {}
    stale = _stale(keys, scores, f, fields, earlier) if earlier else {}
    keys = _rotate(keys, scores, stale, n)
    if not keys:
        return feel, [], []
    # The message's direction: the lead line's, or the mood's when the lead
    # is middling. (Mood runs behind the news, so the lead can run against
    # it when everything does; checkin's opener then says things turned.)
    way = _LEAN_OF_TONE[tone(scores[keys[0]])] or lean
    against = "good" if way < 0 else "bad" if way > 0 else None
    used: set = set()
    lines, asides, tones = [], [], []
    for i, k in enumerate(keys):
        t = tone(scores[k])
        if i and t == against:
            if not asides:
                aside = _fill(ASIDES[k][t], fields)
                # Homegrown talk is vague without the count, so the aside
                # says it too (unless it said it already this season).
                if k == "homegrown" and k not in stale:
                    said = _context(k, t, f, fields, used)
                    aside = f"{aside} {said}" if said else aside
                asides.append(aside)
                tones.append(t)
            continue
        if k in stale:
            lines.append(_pick(rng, AGAIN[k][t], fields, earlier))
            tones.insert(len(lines) - 1, t)
            continue
        line = _pick(rng, NOTES[k][t], fields, earlier)
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
    earlier: list[str] | tuple[str, ...] = (),
) -> str:
    """A mid-season check-in. mood: the owner's mood now, so the opener
    matches the word on the owner card (None: read from these scores).
    season: facts() for the lines to point at. recent: the owner's last few
    messages, so the opener doesn't repeat one of theirs. earlier: the
    owner's earlier check-ins this season, so it doesn't say the same
    things again (_notes)."""
    word = mood_word(mood) if mood is not None else None
    lean = LEAN[word] if word else None
    feel, lines, tones = _notes(
        scores, weights, fields, rng, 2, money, lean, season, earlier
    )
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
