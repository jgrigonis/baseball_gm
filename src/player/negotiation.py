# src/player/negotiation.py
"""
Talking a free agent into a deal (Josh, 2026-11-12). Outside the offseason
bidding window a GM can sign a free agent at his asking price, or make him
an offer: a salary and a number of seasons. He answers right away, yes or
with the deal he'd take, and a line or two on why. No numbers about him are
shown, only the hints.

The rules live here, with no database (src/api/services/fa_offers.py does
the looking up).

- What a deal is worth to him: the money against his asking price, plus
  the seasons of security past what he asked for. Each season counts by his
  age in it: a season at 30 or older is worth SENIOR_SEASON of his price, a
  younger one YOUNG_SEASON. So a 27-year-old gives a discount for a 5-year
  deal, which covers his age 30 and 31 seasons. Offseason bids are judged
  the same way (src/api/services/offseason_fa.py bid_value).
- Plus how well the team suits him (winning, home, market, coaching:
  happiness.team_fit), as much as he cares about those.
- His bar: 1.0 (his asking deal at a team that's neither here nor there),
  higher for a big ego, a star, and other teams with a hole he fills
  ("other teams calling"), lower at his old club when he's loyal, and
  higher at the club that released him.
- His floor: he never takes less than FLOOR of his current asking price,
  down to BEST_FLOOR only when everything favors the club (a great fit, no
  ego, nobody else calling, loyal to his old club). Never under the minimum.
- His asking deal itself is always a yes: that's what Sign pays.
- A lowball far under what he'd take (LOWBALL of it) can insult a
  hot-tempered player: he won't take that club's calls for FREEZE_WEEKS.
  An Easygoing player never takes it personally.
- A club gets OFFERS_PER_WEEK offers a week to one player. His counter
  stands for the rest of the week.
- Money (Josh, 2026-11-18): a player driven by money (the money drive past
  MONEY_START) has a higher bar and floor, and a lowball stings him more.

Re-signing his own club's offer (Josh, 2026-11-18, the Expiring Deals tab:
src/api/services/resign_offers.py) uses the same Stance with home=True:

- His ask is his renewal price, his mood already worked in (the hometown
  discount, or an unhappy player's premium). Re-sign pays that.
- Loyalty counts more the longer he's been with the club (HOME_PULL plus
  HOME_PER_SEASON a season). His floor is HOME_FLOOR of his ask, down to
  HOME_BEST_FLOOR, since the ask already carries any hometown discount.
- Only a player who can walk (a veteran or an unhappy player) has other
  teams calling.
- A lowball (under GRUDGE_LINE of what he'd take) leaves a grudge: a mood
  hit carried into next season (grudge). Under HOME_INSULT of it he may be
  insulted (home_insulted): talks close for the window. One who can walk
  then raises his price HOME_BUMP, or refuses to re-sign at all
  (refuses_after_insult), mostly when he's hot-tempered or disloyal.
- An Easygoing player never holds a grudge or takes it personally.
- An arbitration player can't be talked down from his one-season price, but
  he can be offered an extension of EXTENSION_MIN_YEARS seasons or more:
  his ask is what those seasons are worth (contracts.extension_salary), and
  he takes less for the security (extension_security).
- His counter can come back above his ask: his bar counts his ego, a star's
  pride, other teams calling and money, and his ask (the renewal price) is a
  sure yes only for the seasons he asked. When it does, Re-sign pays that
  counter (Josh, 2026-11-19: raised), and his old ask is no longer a yes.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

# A season of security, as a share of his asking salary: worth more once he's
# 30 or older, when he's likely to decline.
SENIOR_AGE = 30
SENIOR_SEASON = 0.04
YOUNG_SEASON = 0.01

# How much the team's fit counts against the money (offseason_fa FIT_WEIGHT).
FIT_WEIGHT = 0.3

# What raises or lowers his bar, as a share of his asking salary.
EGO_PULL = 0.05  # ego 100: +5%, ego 0: -5%
STAR_PULL = 0.04  # an A- or better
CALLER_PULL = 0.03  # each other team with a hole he fills
CALLER_MAX = 3
OLD_CLUB_PULL = 0.06  # times loyalty / 100, at his last club
RELEASED_PULL = 0.05  # plus as much again times temper / 100

FLOOR = 0.8
BEST_FLOOR = 0.7
# How far up the "everything favors you" score has to be before the floor
# starts to drop, and where it reaches BEST_FLOOR.
FAVOR_START = 0.6
FAVOR_FULL = 0.95
# share * fit this big counts as a perfect fit for the floor.
FIT_FULL = 0.6

LOWBALL = 0.8
CALM_TEMPER = 55
HOT_TEMPER = 90
FREEZE_WEEKS = 2
OFFERS_PER_WEEK = 2

# Counters go up in this step of his asking salary, so they read cleanly.
MAX_COUNTER = 1.25

# Money (Josh, 2026-11-18): past MONEY_START on the money drive, his bar
# rises up to MONEY_PULL and his floor up to MONEY_FLOOR (at a drive of 100).
MONEY_START = 50
MONEY_PULL = 0.05
MONEY_FLOOR = 0.05

# Re-signing with his own club.
HOME_PULL = 0.06  # times loyalty / 100, like OLD_CLUB_PULL
HOME_PER_SEASON = 0.01  # more a season with the club, up to HOME_SEASONS
HOME_SEASONS = 6
HOME_FLOOR = 0.85
HOME_BEST_FLOOR = 0.8
OFFERS_PER_WINDOW = 3
# An offer under GRUDGE_LINE of what he'd take leaves a grudge; under
# HOME_INSULT of it he may be insulted.
GRUDGE_LINE = 0.9
HOME_INSULT = 0.75
# The grudge: at most GRUDGE_MAX off his mood (temper 100, loyalty 0, money
# 100), twice that when insulted, GRUDGE_CAP in all. It fades over
# GRUDGE_WEEKS weekly mood updates.
GRUDGE_MAX = 0.15
GRUDGE_CAP = 0.3
GRUDGE_WEEKS = 8
# Insulted at home: the chance he takes it personally, from calm to hot.
HOME_INSULT_LOW = 0.5
HOME_INSULT_TEMPER = 30  # temper where the chance starts to climb
# One who can walk raises his price this much, or refuses to re-sign:
# REFUSE_BASE for anyone, up to REFUSE_TEMPER more for temper over 50 and
# REFUSE_DISLOYAL more for loyalty under 50, REFUSE_MAX at most (Josh,
# 2026-11-18: mainly hot-tempered and/or disloyal players).
HOME_BUMP = 0.10
REFUSE_BASE = 0.05
REFUSE_TEMPER = 0.35
REFUSE_DISLOYAL = 0.35
REFUSE_MAX = 0.6


# Arbitration extensions (Josh, 2026-11-18): a player still under team
# control gives a discount for guaranteed seasons, EXTENSION_SECURITY a
# season past the first, up to EXTENSION_MAX, and never past EXTENSION_FLOOR
# of what the seasons are worth.
EXTENSION_SECURITY = 0.03
EXTENSION_MAX = 0.12
EXTENSION_FLOOR = 0.7
EXTENSION_MIN_YEARS = 2


def extension_security(years: int) -> float:
    return min(EXTENSION_MAX, EXTENSION_SECURITY * max(0, years - 1))


def money_lean(money: int) -> float:
    """0 to 1: how far past MONEY_START his money drive is."""
    return max(0.0, min(1.0, (money - MONEY_START) / (100 - MONEY_START)))


def season_value(age: int, years: int) -> float:
    """The security a deal of this many seasons gives him: each season by
    his age in it."""
    return sum(
        SENIOR_SEASON if age + i >= SENIOR_AGE else YOUNG_SEASON
        for i in range(max(0, years))
    )


def money_value(
    salary: int, years: int, ask_salary: int, ask_years: int, age: int
) -> float:
    """The money against his asking price, plus the seasons of security
    past (or short of) what he asked for."""
    return salary / ask_salary + season_value(age, years) - season_value(age, ask_years)


@dataclass(frozen=True)
class Stance:
    """Where a free agent stands with one club."""

    ask_salary: int
    ask_years: int
    age: int
    fit: float  # -1 to 1: how well the club suits him (happiness.team_fit)
    share: float  # 0 to 1: how much the fit counts for him against money
    ego: int
    temper: int
    loyalty: int
    easygoing: bool = False
    star: bool = False
    callers: int = 0  # other teams with a hole he fills
    old_club: bool = False  # his last club, and it didn't release him
    released_by: bool = False  # this club released him (or he holds a grudge)
    minimum: int = 780_000
    money: int = 0  # his money drive, 0 to 100
    home: bool = False  # re-signing with his own club
    seasons: int = 0  # seasons with the league, for the home pull
    security: float = 0.0  # an extension's guaranteed seasons, off his bar
    # A counter higher than his ask raised his Re-sign price (Josh,
    # 2026-11-19): his old asking deal is no longer a sure yes, nor the cap
    # on a counter for those seasons.
    raised: bool = False

    @property
    def home_pull(self) -> float:
        return (
            (HOME_PULL + HOME_PER_SEASON * min(max(self.seasons, 0), HOME_SEASONS))
            * self.loyalty
            / 100
        )

    @property
    def fit_term(self) -> float:
        return FIT_WEIGHT * self.share * self.fit

    @property
    def bar(self) -> float:
        b = 1.0
        b += EGO_PULL * (self.ego - 50) / 50
        if self.star:
            b += STAR_PULL
        b += CALLER_PULL * min(self.callers, CALLER_MAX)
        if self.home:
            b -= self.home_pull
        elif self.old_club:
            b -= OLD_CLUB_PULL * self.loyalty / 100
        if self.released_by:
            b += RELEASED_PULL * (1 + self.temper / 100)
        b += MONEY_PULL * money_lean(self.money)
        b -= self.security
        return b

    @property
    def favor(self) -> float:
        """0 to 1: how much everything favors the club, for the floor."""
        parts = (
            max(0.0, min(1.0, self.share * self.fit / FIT_FULL)),
            1 - self.ego / 100,
            1.0 if self.callers == 0 else 0.0,
            self.loyalty / 100 if (self.old_club or self.home) else 0.0,
        )
        avg = sum(parts) / len(parts)
        return max(0.0, min(1.0, (avg - FAVOR_START) / (FAVOR_FULL - FAVOR_START)))

    @property
    def floor(self) -> int:
        top, best = (HOME_FLOOR, HOME_BEST_FLOOR) if self.home else (FLOOR, BEST_FLOOR)
        share = top - (top - best) * self.favor
        share += MONEY_FLOOR * money_lean(self.money)
        share = max(EXTENSION_FLOOR, share - self.security)
        return max(self.minimum, math.ceil(self.ask_salary * share))

    def value(self, salary: int, years: int) -> float:
        return (
            money_value(salary, years, self.ask_salary, self.ask_years, self.age)
            + self.fit_term
        )

    def takes(self, salary: int, years: int) -> bool:
        if salary < self.minimum:
            return False
        if not self.raised and salary >= self.ask_salary and years == self.ask_years:
            return True  # his asking deal: what Sign pays
        return salary >= self.floor and self.value(salary, years) >= self.bar - 1e-9

    def counter(self, years: int, round_up) -> int:
        """The least he'd take a season for this many seasons. round_up
        rounds a salary up to a clean amount."""
        need = (
            self.bar
            - self.fit_term
            - season_value(self.age, years)
            + season_value(self.age, self.ask_years)
        ) * self.ask_salary
        salary = max(self.floor, self.minimum, need)
        if years == self.ask_years and not self.raised:
            salary = min(salary, self.ask_salary)
        salary = min(salary, self.ask_salary * MAX_COUNTER)
        out = round_up(salary)
        # Rounding can't take it under what he needs.
        while not self.takes(out, years) and out < self.ask_salary * MAX_COUNTER:
            out = round_up(out + 1)
        return out

    def insulted(self, salary: int, counter: int, seed: str) -> bool:
        """A lowball far under what he'd take: a hot-tempered player stops
        taking the club's calls."""
        if self.easygoing or salary >= LOWBALL * counter:
            return False
        chance = (self.temper - CALM_TEMPER) / (HOT_TEMPER - CALM_TEMPER)
        if chance <= 0:
            return False
        return random.Random(seed).random() < chance

    # ── At home ──────────────────────────────────────────────────────────

    def grudge(self, salary: int, counter: int, insulted: bool = False) -> float:
        """How much a lowball from his own club takes off his mood next
        season: nothing for a fair try (GRUDGE_LINE of what he'd take or
        better) or an Easygoing player; more for temper and money, less for
        loyalty; twice as much when he was insulted."""
        if self.easygoing or salary >= GRUDGE_LINE * counter:
            return 0.0
        g = (
            GRUDGE_MAX
            * self.temper
            / 100
            * (1 - self.loyalty / 200)
            * (0.5 + self.money / 200)
        )
        return min(GRUDGE_CAP, g * (2 if insulted else 1))

    def home_insulted(self, salary: int, counter: int, roll: float) -> bool:
        """A lowball far under what he'd take (HOME_INSULT of it): he may
        take it personally, more likely the hotter his temper. An Easygoing
        player never does."""
        if self.easygoing or salary >= HOME_INSULT * counter:
            return False
        hot = max(
            0.0,
            min(1.0, (self.temper - HOME_INSULT_TEMPER) / (100 - HOME_INSULT_TEMPER)),
        )
        return roll < HOME_INSULT_LOW + (1 - HOME_INSULT_LOW) * hot

    def refuse_chance(self) -> float:
        """Insulted, and free to walk: the chance he won't re-sign at all
        (Josh, 2026-11-18: it can happen to anyone, mainly the hot-tempered
        and the disloyal)."""
        if self.easygoing:
            return REFUSE_BASE
        hot = max(0.0, (self.temper - 50) / 50)
        cold = max(0.0, (50 - self.loyalty) / 50)
        return min(
            REFUSE_MAX, REFUSE_BASE + REFUSE_TEMPER * hot + REFUSE_DISLOYAL * cold
        )


def hints(s: Stance) -> list[str]:
    """A line or two on where he stands, never a number."""
    out = []
    if s.released_by:
        out.append("Hasn't forgotten how you treated him.")
    elif s.old_club and s.loyalty >= 60:
        out.append("Glad to hear from his old club.")
    if s.fit_term >= 0.06:
        out.append("Likes your club.")
    elif s.fit_term <= -0.04:
        out.append("Isn't sold on your club.")
    if s.callers >= 2:
        out.append("Has other teams calling.")
    elif s.callers == 1:
        out.append("Has another team interested.")
    else:
        out.append("Nobody else is calling yet.")
    if s.star and s.ego >= 65:
        out.append("Wants to be paid like a star.")
    elif money_lean(s.money) >= 0.5:
        out.append("Money talks with him.")
    return out[:3]


def resign_hints(
    s: Stance, mood: float | None, underpaid: bool, grudge: bool
) -> list[str]:
    """Where a player stands with his own club, a line or two, never a
    number. mood is his latest mood (happiness.py), underpaid whether his
    money satisfaction is under (he thinks he's underpaid)."""
    out = []
    if grudge:
        out.append("Remembers the lowball offer.")
    if mood is None:
        out.append("Open to staying, at the right price.")
    else:
        if mood >= 0.25 and s.loyalty >= 60:
            out.append("Wants to stay.")
        elif mood >= 0.25:
            out.append("Likes it here.")
        elif mood >= -0.15:
            out.append("Open to staying, at the right price.")
        else:
            out.append("Isn't sure he wants to stay.")
    if underpaid:
        out.append("Feels underpaid.")
    if s.callers >= 1:
        out.append("Knows other teams want him.")
    if s.star and s.ego >= 65:
        out.append("Wants to be paid like a star.")
    return out[:3]


def resign_warnings(s: Stance, can_walk: bool, grudge: bool) -> list[str]:
    """The warning on the re-sign offer dialog (Josh, 2026-11-18): what a
    lowball can do, in words only."""
    if s.easygoing:
        first = "A lowball won't upset him much. He's hard to upset."
        return [first] + (["He still remembers your last offer."] if grudge else [])
    if can_walk:
        first = "A lowball can anger him. He may raise his price, or refuse to re-sign."
    else:
        first = (
            "He's under your control and can't leave, but a lowball can anger "
            "him, and he'll carry it into next season."
        )
    out = [first]
    extra = []
    if s.temper >= 70:
        extra.append("He has a short fuse.")
    if s.loyalty < 35:
        extra.append("He doesn't owe you any loyalty.")
    if grudge:
        extra.append("He still remembers your last offer.")
    return out + extra[:2]
