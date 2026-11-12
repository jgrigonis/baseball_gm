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
    released_by: bool = False  # this club released him
    minimum: int = 780_000

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
        if self.old_club:
            b -= OLD_CLUB_PULL * self.loyalty / 100
        if self.released_by:
            b += RELEASED_PULL * (1 + self.temper / 100)
        return b

    @property
    def favor(self) -> float:
        """0 to 1: how much everything favors the club, for the floor."""
        parts = (
            max(0.0, min(1.0, self.share * self.fit / FIT_FULL)),
            1 - self.ego / 100,
            1.0 if self.callers == 0 else 0.0,
            self.loyalty / 100 if self.old_club else 0.0,
        )
        avg = sum(parts) / len(parts)
        return max(0.0, min(1.0, (avg - FAVOR_START) / (FAVOR_FULL - FAVOR_START)))

    @property
    def floor(self) -> int:
        share = FLOOR - (FLOOR - BEST_FLOOR) * self.favor
        return max(self.minimum, math.ceil(self.ask_salary * share))

    def value(self, salary: int, years: int) -> float:
        return (
            money_value(salary, years, self.ask_salary, self.ask_years, self.age)
            + self.fit_term
        )

    def takes(self, salary: int, years: int) -> bool:
        if salary < self.minimum:
            return False
        if salary >= self.ask_salary and years == self.ask_years:
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
        if years == self.ask_years:
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


def hints(s: Stance) -> list[str]:
    """A line or two on where he stands, never a number."""
    out = []
    if s.released_by:
        out.append("Hasn't forgotten you released him.")
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
    return out[:3]
