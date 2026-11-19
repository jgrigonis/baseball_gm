# src/api/services/owner_card.py
#
# The Owner tab's "Your Owner" card for the GM (Josh, 2026-11-16, mockup in
# plans/owner-card): who the boss is (a mood meter, a job security meter,
# how they run things in words, what they want a say in), what they judge
# you on (one bar per weight, longest = matters most, with how it's going),
# and the money (payroll vs the cap, total spending vs their budget and
# limit, and one verdict line). Words and bars only: the numbers behind
# them stay admin-only (owner_debug.py).

from __future__ import annotations

from src.api.services import owner_debug
from src.api.services import owners as owner_service
from src.league import budget as bg
from src.league import owner_messages as om
from src.league import owner_scoring as sc
from src.league import owners
from src.league.league_modes import get_mode
from src.player.contracts import MIN_SALARY, format_salary

# Mood words from worst to best, for the six-step meter.
MOOD_STEPS = tuple(w for _, w in reversed(om.MOODS))
MOOD_TONE = {
    "furious": "red",
    "frustrated": "red",
    "uneasy": "amber",
    "content": "",
    "pleased": "green",
    "thrilled": "green",
}

# Job security, in four steps: (floor, word, tone, what it means).
JOB_STEPS = (
    (0, "Hot seat", "red", "Another bad season could cost you your job."),
    (
        sc.HOT_SEAT,
        "Being watched",
        "amber",
        "Another season like the last could put you on the hot seat.",
    ),
    (55, "Solid", "", "A bad season would hurt, but you'd keep your job."),
    (70, "Safe", "green", "You've earned some rope."),
)

TONE_WORDS = {
    "good": "Going well",
    "ok": "About right",
    "bad": "Falling short",
    None: "Not yet",
}
# Judged only when the league has money (owner_scoring.score_dimensions).
MONEY_KEYS = ("profit", "attendance", "fans")
# A weight under this is shown behind "Show all".
SHOWN_WEIGHT = 30
SHOWN_MIN = 6

# How the owner runs things, in words: (trait, label, [(below, words)]).
TRAIT_WORDS = (
    (
        "patience",
        "Patience",
        (
            (20, "Short: one bad year and you'll hear about it"),
            (40, "Not much"),
            (60, "Average"),
            (80, "Gives a GM time"),
            (101, "Gives a GM years"),
        ),
    ),
    (
        "ambition",
        "Expects",
        (
            (20, "Happy with .500"),
            (40, "A decent season"),
            (60, "A winning team"),
            (80, "A contender"),
            (101, "A winner, every season"),
        ),
    ),
    (
        "horizon",
        "Judges",
        (
            (30, "The long run"),
            (70, "This season and the next few"),
            (101, "This season"),
        ),
    ),
    (
        "spending",
        "Spending",
        (
            (20, "Watches every dollar"),
            (40, "Careful"),
            (60, "Average"),
            (80, "Will pay for a contender"),
            (101, "Spends to win"),
        ),
    ),
    (
        "temper",
        "Temper",
        ((30, "Steady"), (70, "Moves with the season"), (101, "Mood swings fast")),
    ),
    (
        "chattiness",
        "Writes",
        ((25, "Rarely"), (50, "Now and then"), (75, "Often"), (101, "A lot")),
    ),
)

# The owner's messages that move the mood, in words, for the mood tip.
EVENT_WORDS = {
    "trade": "a trade",
    "release": "a release",
    "streak": "a streak",
    "veto": "a release they refused",
    "overpay": "an overpaid player",
    "budget": "the payroll",
}


def _words(value: int, levels) -> str:
    for below, words in levels:
        if value < below:
            return words
    return levels[-1][1]


def _money(n: int) -> str:
    return format_salary(max(0, int(n)))


def wants_a_say(weights: dict, traits: dict) -> list[str]:
    """What this owner steps in on, from the same rules the owner's office
    reacts by (owner_office: trades, releases, vetoes, streaks)."""
    w = owners.clean_weights(weights)
    t = owners.clean_traits(traits)
    meddles = t["meddling"] >= om.MEDDLES
    out = []
    if meddles:
        out.append("Every trade: they'll tell you what they think of each one")
        out.append(
            "Releases: they can refuse to let you release a B- or better"
            " player or a franchise icon"
        )
    else:
        if w["stability"] >= owners.STRONG:
            out.append("Trades: they like a steady roster, and each trade gets a word")
        if w["icons"] >= owners.STRONG:
            out.append("Trading or releasing a franchise icon")
        if w["stars"] >= owners.STRONG:
            out.append("Stars: releasing an A player, or trading for an All-Star")
    if w["profit"] >= owners.STRONG or meddles:
        out.append(
            "Releases that leave " + format_salary(2_000_000) + " or more of dead money"
        )
    if meddles or t["temper"] >= owners.STRONG or w["wins"] >= owners.STRONG:
        out.append("Streaks: expect a word after 8 losses in a row, or 10 wins")
    return out


def _job(conn, gm_id: str, league_id: str, archetype: str | None) -> dict:
    row = conn.execute(
        """SELECT e.job_security FROM gm_season_evaluations e
           JOIN seasons s ON s.id = e.season_id
           WHERE e.gm_id = %s AND e.job_security IS NOT NULL
           ORDER BY s.year DESC LIMIT 1""",
        (gm_id,),
    ).fetchone()
    firing = conn.execute(
        "SELECT owner_firing FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    security = float(row["job_security"]) if row else sc.MIDDLE
    step = 0
    for i, (floor, *_rest) in enumerate(JOB_STEPS):
        if security >= floor:
            step = i
    _, word, tone, tip = JOB_STEPS[step]
    rules = sc.firing_rules(archetype)
    if not row:
        tip = "Your first review comes at the end of the season."
    extra = []
    if firing and not firing["owner_firing"]:
        extra.append("Owner firing is off in this league, so it's only their opinion.")
    else:
        extra.append(
            f"They give a new GM {rules.honeymoon} season"
            f"{'' if rules.honeymoon == 1 else 's'} before they can fire you"
            + (
                ", and they warn you first (the hot seat) before they do."
                if rules.warn_first
                else ", and they don't always warn you first."
            )
        )
    return {
        "step": step,
        "steps": len(JOB_STEPS),
        "word": word,
        "tone": tone,
        "tip": " ".join([tip, *extra]),
        "reviewed": bool(row),
    }


def _mood(conn, league_id: str, team_id: str, d: dict, temper: int) -> dict:
    word = d["mood_word"]
    swing = (
        "This owner's mood swings fast."
        if temper >= owners.STRONG
        else "This owner is steady: it moves slowly."
        if temper < 30
        else ""
    )
    last = next((e for e in d["events"] if e["kind"] in EVENT_WORDS), None)
    lines = [
        "Their mood moves a little each week toward how the season is going.",
    ]
    if last:
        lines.append(f"The last thing that moved it was {EVENT_WORDS[last['kind']]}.")
    if swing:
        lines.append(swing)
    return {
        "word": word.capitalize(),
        "step": MOOD_STEPS.index(word),
        "steps": len(MOOD_STEPS),
        "tone": MOOD_TONE.get(word, ""),
        "tip": " ".join(lines),
    }


def _judged(d: dict, money: bool) -> dict:
    rows = []
    for r in d["rows"]:
        if not r["weight"] or (not money and r["key"] in MONEY_KEYS):
            continue
        tone = r["tone"] if r["score"] is not None else None
        rows.append(
            {
                "label": r["label"],
                "width": r["weight"],
                "less": r["weight"] < 50,
                "tone": tone or "none",
                "word": TONE_WORDS[tone],
            }
        )
    cut = max(SHOWN_MIN, sum(1 for r in rows if r["width"] >= SHOWN_WEIGHT))
    shown, more = rows[:cut], rows[cut:]
    worst = [r["label"].lower() for r in rows if r["tone"] == "bad"][:2]
    return {
        "rows": shown,
        "more": more,
        "worst": worst,
        "season": d["state"] in ("season", "playoffs"),
    }


def money(standing: dict, state: str, year: int) -> dict:
    """The two money bars and the verdict line, from BudgetRepository
    .standing(). Positions are percentages of each bar."""
    pay, cap = standing["payroll"], standing["cap"]
    fo, minors, tax = standing["front_office"], standing["minors"], standing["tax"]
    spend, budget, limit = standing["spend"], standing["budget"], standing["limit"]

    scale1 = max(pay, cap) * 1.15 or 1

    def p1(x):
        return round(100 * x / scale1, 2)

    payroll_bar = {
        "pay": p1(min(pay, cap)),
        "over": p1(max(0, pay - cap)),
        "cap": p1(cap),
        "under_text": _money(min(pay, cap)),
    }

    scale2 = max(spend, limit) * 1.08 or 1

    def p2(x):
        return round(100 * x / scale2, 2)

    over_limit = max(0, spend - limit)
    spend_bar = {
        "fo": p2(fo),
        "minors": p2(minors),
        "pay": p2(pay),
        "tax": p2(tax),
        "budget": p2(budget),
        "limit": p2(limit),
        "past": p2(over_limit),
        # Where a label sits, kept inside the bar.
        "past_mid": min(96.0, p2(limit + over_limit / 2)),
        "budget_label": min(92.0, p2(budget)),
        "limit_label": min(94.0, p2(limit)),
    }
    # Labels on the budget and limit ticks would overlap when close.
    if spend_bar["limit_label"] - spend_bar["budget_label"] < 14:
        spend_bar["budget_label"] = max(6.0, spend_bar["limit_label"] - 14)

    front_office_open = state in ("draft", "preseason")
    if standing["over_limit_text"]:
        # Payroll it takes to get back under, with the tax it carries.
        cut = min(pay, max(0, -standing["limit_payroll_room"]))
        if cut and _money(cut) != _money(over_limit):
            how = (
                f"Cutting {_money(cut)} of payroll cuts {_money(over_limit)} of"
                " spending, since the tax on it goes too, and gets you back under."
            )
        else:
            how = f"Cutting {_money(over_limit)} of payroll gets you back under."
        if front_office_open:
            how += (
                " Or trim coaching, facilities or analytics on the Budget tab,"
                " where each $1 is $1 of spending."
            )
        verdict = {
            "tone": "bad",
            "head": "They won't approve moves that add money.",
            "text": f"You're {_money(over_limit)} past their limit. {how}",
        }
    elif spend > budget:
        verdict = {
            "tone": "warn",
            "head": "Past their budget, inside their limit.",
            "text": (
                f"{_money(limit - spend)} more before they stop approving moves."
                " Every dollar past the budget comes out of their profit."
            ),
        }
    else:
        verdict = {
            "tone": "ok",
            "head": "Under their budget.",
            "text": (
                f"{_money(budget - spend)} of room before you cut into their"
                f" profit, {_money(limit - spend)} before they stop approving moves."
            ),
        }
    return {
        "year": year,
        "payroll_text": standing["payroll_text"],
        "cap_text": standing["cap_text"],
        "over_text": standing["over_text"],
        "room_text": standing["room_text"],
        "tax_text": standing["tax_text"],
        "tax_pct": round(bg.LUXURY_TAX_RATE * 100),
        "spend_text": standing["spend_text"],
        "budget_text": standing["budget_text"],
        "limit_text": standing["limit_text"],
        "front_office_text": standing["front_office_text"],
        "minors_text": standing["minors_text"],
        "over_limit_text": _money(over_limit) if standing["over_limit_text"] else None,
        "over_budget_text": standing["over_budget_text"],
        "front_office_open": front_office_open,
        "payroll_bar": payroll_bar,
        "spend_bar": spend_bar,
        "verdict": verdict,
    }


def boss(conn, league_id: str, team_id: str, gm_id: str) -> dict | None:
    """The boss half of the card: mood, job, how they run things, what they
    want a say in, and what they judge you on. None without an owner."""
    d = owner_debug.explain(conn, league_id, team_id)
    if not d:
        return None
    row = owner_service.ensure(conn, league_id).get(team_id)
    weights = row["weights"] if row else {}
    traits = owners.clean_traits(row["traits"] if row else {})
    mode = conn.execute(
        "SELECT mode FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    has_money = get_mode(mode["mode"] if mode else None).budgets
    return {
        "mood": _mood(conn, league_id, team_id, d, traits["temper"]),
        "job": _job(conn, gm_id, league_id, d["archetype"]),
        "traits": [
            {"label": label, "words": _words(traits[key], levels)}
            for key, label, levels in TRAIT_WORDS
        ],
        "say": wants_a_say(weights, traits),
        "judge": _judged(d, has_money),
    }


# ── The Free Agents tab: what a new deal really costs ──────────────────────


def cost_now(standing: dict, salary: int, share: float = 1.0) -> int:
    """What signing him adds to this season's spending: the part of his
    salary still to pay (share) and the luxury tax it adds."""
    return bg.added_cost(standing["payroll"], standing["cap"], round(salary * share))


def cost_note(standing: dict, salary: int | None, share: float = 1.0) -> str | None:
    """The line under his price, when this season's cost isn't simply his
    salary: prorated in season, and/or with tax."""
    if not salary:
        return None
    paid = round(salary * share)
    cost = cost_now(standing, salary, share)
    taxed = cost > paid
    if not taxed and share >= 0.999:
        return None
    when = "this season" if share < 0.999 else ""
    return " ".join(x for x in (_money(cost), when, "with tax" if taxed else "") if x)


def fa_room(standing: dict, share: float = 1.0) -> dict:
    """One line for the Free Agents header (Josh, 2026-11-16: the estimate
    of how much you can spend on free agents): under the cap, a deal that
    would cross it, already over it, or past the owner's limit. Amounts are
    salaries a season; mid-season a new deal only pays the rest of it."""
    share = max(0.05, share)
    rate = 1 + bg.LUXURY_TAX_RATE
    times = f"${rate:.2f}"
    if standing["over_limit_text"] or standing["limit_payroll_room"] <= 0:
        return {
            "tone": "bad",
            "head": "Your owner won't approve a signing.",
            "text": (
                f"You're {_money(standing['spend'] - standing['limit'])} past"
                f" their limit. Cut {_money(-standing['limit_payroll_room'])} of"
                " payroll to get back under."
                if standing["over_limit_text"]
                else "You're at their limit."
            ),
        }
    room = standing["limit_payroll_room"]
    salary = room / share
    if salary < MIN_SALARY:
        fits = (
            f"No free agent fits under your owner's limit: {_money(salary)} of"
            f" salary, and the minimum is {_money(MIN_SALARY)}."
        )
    else:
        fits = f"{_money(salary)} of salary fits under your owner's limit."
    tip = None
    if share < 0.999:
        # Josh, 2026-11-17: the proration note read as if the tax were
        # prorated. Keep the line short and say it here.
        tip = (
            "Mid-season, a player you sign is paid only the part of his"
            f" salary left this season (about {round(share * 100)}%). So a"
            f" {_money(salary)} salary uses {_money(room)} of the room"
            " under your owner's limit this year."
        )
    cap_room = standing["cap"] - standing["payroll"]
    if cap_room <= 0:
        return {
            "tone": "warn",
            "head": f"{standing['over_text'] or '$0'} over the cap.",
            "text": f"Every dollar of a new deal costs {times} with tax.",
            "fits": fits,
            "tip": tip,
        }
    under = _money(cap_room / share)
    if room <= cap_room:
        return {
            "tone": "ok",
            "head": f"{standing['room_text']} under the cap.",
            "text": "A deal up to that costs just its salary.",
            "fits": fits,
            "tip": tip,
        }
    return {
        "tone": "warn",
        "head": f"{standing['room_text']} under the cap.",
        "text": (
            f"A deal up to {under} a season costs just its salary; past that, each dollar"
            f" costs {times} with tax."
        ),
        "fits": fits,
        "tip": tip,
    }
