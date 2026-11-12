# src/api/services/fa_offers.py
"""
Making a free agent an offer (Josh, 2026-11-12). Whenever a free agent can
be signed at his asking price (outside the offseason bidding window), a
club can also offer him a salary and a number of seasons. He answers right
away: he signs, or he says what he'd take for those seasons, with a line or
two on where he stands. The rules are in src/player/negotiation.py; this
gathers what they need.

- Other teams calling: AI teams with a hole he fills and room for his
  asking price (src/api/services/ai_free_agents.py best_fit).
- A club makes at most negotiation.OFFERS_PER_WEEK offers a week to one
  player, and his counter stands for the rest of that week.
- A week is a week of the season. Before Opening Day each step (offseason,
  draft, preseason) counts as one (talk_week).
- A club that insults a hot-tempered player can't make him offers for
  negotiation.FREEZE_WEEKS weeks. Signing at his asking price still works.
- AI teams negotiate too (ai_offer): an owner who's a miser has his GM open
  low, one who spends to win opens near the ask; a cautious GM opens lower
  and often walks away from a counter, a gambler opens higher and takes it.
"""

from __future__ import annotations

import math
import random

from src.api.services import ai_free_agents, free_agents, offseason_fa, owners, waivers
from src.api.services.news import moves as move_news
from src.db.locks import league_lock
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.happiness_repo import HappinessRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.league import money_state
from src.player import contracts as ct
from src.player import happiness as hp
from src.player import negotiation as ng
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_value import role_rating

# Grade index (contracts.GRADES) under which he's a star: A- or better.
STAR_GRADE = 3

# AI teams: how close to his ask a GM opens, from the owner's Spending trait
# (0 = miser, 100 = spends to win) and the GM's Risk dial.
AI_OPEN_LOW = 0.8
AI_OPEN_HIGH = 1.0
AI_OPEN_RISK = 0.05  # a gambler opens this much higher, the most cautious lower
# Chance an AI GM takes a counter: cautious to gambler.
AI_TAKE_LOW = 0.3
AI_TAKE_HIGH = 0.9


class OfferError(Exception):
    """An offer that can't be made, with the reason to show."""


# ── The week ─────────────────────────────────────────────────────────────────


def week_of(year: int | None, state: str | None, days: int = 0) -> int:
    """A number that goes up one a week: weeks of the season, with each step
    before Opening Day (the draft, the preseason) counted as one. The
    offseason belongs to the season just played (its year)."""
    year = year or 0
    if state == "offseason":
        return year * 100 + 90
    if state == "draft":
        return year * 100 + 1
    if state == "preseason":
        return year * 100 + 2
    return year * 100 + 10 + min(79, max(0, days) // 7)


def talk_week(conn, league_id: str) -> int:
    league = LeagueRepository(conn).get_by_id(league_id)
    year = ContractRepository(conn).current_year(league_id)
    state = league["state"] if league else None
    if state not in ("season", "playoffs"):
        return week_of(year, state)
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    row = conn.execute(
        """SELECT MIN(game_date) AS first,
                  MAX(game_date) FILTER (WHERE completed = 1) AS last
           FROM games WHERE season_id = %s""",
        (season_id,),
    ).fetchone()
    days = 0
    if row and row["first"] and row["last"]:
        from datetime import date

        days = (
            date.fromisoformat(str(row["last"])) - date.fromisoformat(str(row["first"]))
        ).days
    return week_of(year, state, days)


def _talks(conn, league_id: str, team_id: str, player_id: str) -> dict | None:
    row = conn.execute(
        """SELECT * FROM fa_talks
           WHERE league_id = %s AND team_id = %s AND player_id = %s""",
        (league_id, team_id, player_id),
    ).fetchone()
    return dict(row) if row else None


def _save_talks(conn, league_id, team_id, player_id, week, offers, counter, frozen):
    conn.execute(
        """INSERT INTO fa_talks (league_id, team_id, player_id, week, offers,
                                 counter_salary, counter_years, frozen_until)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (league_id, team_id, player_id) DO UPDATE
           SET week = excluded.week, offers = excluded.offers,
               counter_salary = excluded.counter_salary,
               counter_years = excluded.counter_years,
               frozen_until = excluded.frozen_until""",
        (
            league_id,
            team_id,
            player_id,
            week,
            offers,
            counter[0] if counter else None,
            counter[1] if counter else None,
            frozen,
        ),
    )


def _this_week(
    talks: dict | None, week: int
) -> tuple[int, tuple[int, int] | None, int | None]:
    """(offers made this week, the counter that stands, frozen until)."""
    if not talks:
        return 0, None, None
    frozen = talks["frozen_until"] if (talks["frozen_until"] or 0) > week else None
    if talks["week"] != week:
        return 0, None, frozen
    counter = (
        (talks["counter_salary"], talks["counter_years"])
        if talks["counter_salary"]
        else None
    )
    return talks["offers"], counter, frozen


# ── Where he stands ──────────────────────────────────────────────────────────


def _free_agent(conn, league_id: str, player_id: str):
    p = PlayerRepository(conn).look_up(player_id)
    if (
        p is None
        or not free_agents._in_league(conn, league_id, player_id)
        or PlayerStatusRepository(conn).get_status(player_id) != "free_agent"
    ):
        raise OfferError("He isn't a free agent.")
    if waivers.on_waivers(conn, player_id):
        raise OfferError("He's on waivers. Claim him instead.")
    return p


def _open(conn, league_id: str) -> tuple[dict, str, int]:
    league = LeagueRepository(conn).get_by_id(league_id)
    if not league or league["state"] not in free_agents.OPEN_STATES:
        raise OfferError("Free agents can't be signed right now.")
    if offseason_fa.bidding_open_for(league):
        raise OfferError("Free agents take bids until bidding closes. Make him a bid.")
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    year = ContractRepository(conn).current_year(league_id)
    if not season_id or year is None:
        raise OfferError("Free agents can't be signed right now.")
    return league, season_id, year


def asking(conn, league_id: str, player, year: int) -> ct.Deal:
    """His asking deal right now (what Sign pays)."""
    return free_agents.asking_deal(
        player,
        year,
        free_agents.price_scale(conn, league_id, year),
        free_agents.market_discount(conn, league_id),
        free_agents.price_shifts(conn, league_id, year),
    )


def minimum(conn, league_id: str, year: int) -> int:
    scale = free_agents.price_scale(conn, league_id, year)
    return ct.round_salary(ct.MIN_SALARY * scale, scale)


def round_up(amount: float) -> int:
    """Up to $10K under $1M, $50K above."""
    step = 10_000 if amount < 1_000_000 else 50_000
    return int(math.ceil(amount / step - 1e-9) * step)


def is_star(conn, league_id: str, player, year: int) -> bool:
    shifts = free_agents.price_shifts(conn, league_id, year)
    kind = "pitcher" if player.is_pitcher() else "hitter"
    value = ct.shifted(role_rating(player), kind, shifts)
    return ct.grade_position(value, kind) < STAR_GRADE


def callers(
    conn, league_id: str, player, year: int, ask: ct.Deal, exclude=(), teams=None
) -> int:
    """AI teams with a hole he fills and room for his asking price. teams:
    {team_id: role_values} to use instead of rating every AI roster."""
    if teams is None:
        humans = GMRepository(conn).get_human_team_ids(league_id)
        season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
        teams = {
            t["id"]: ai_free_agents.role_values(
                ai_free_agents._rated_team(conn, league_id, t["id"])
            )
            for t in TeamRepository(conn).get_teams_in_league_season(
                league_id, season_id
            )
            if t["id"] not in humans
        }
    r = PlayerEvaluator.rate_player(player.skills, player.throws)
    money = owners.money_states(conn, league_id, year)
    n = 0
    for team_id, roles in teams.items():
        if team_id in exclude:
            continue
        margin = money_state.hole_margin(money.get(team_id), ai_free_agents.HOLE_MARGIN)
        role, _ = ai_free_agents.best_fit(roles, r, margin)
        if not role:
            continue
        if ai_free_agents._budget_room(conn, league_id, team_id, year) < ask.salary:
            continue
        n += 1
    return n


def stance(
    conn,
    league_id: str,
    season_id: str,
    year: int,
    team_id: str,
    player,
    ask: ct.Deal,
    n_callers: int | None = None,
) -> ng.Stance:
    """Where he stands with this club."""
    person = HappinessRepository(conn, league_id).personalities([player.id]).get(
        player.id
    ) or hp.personality_for(player.id)
    row = conn.execute(
        "SELECT home_region FROM players WHERE id = %s", (player.id,)
    ).fetchone()
    home = row["home_region"] if row else None
    fits = offseason_fa._fits(conn, league_id, season_id, year, [team_id])
    fit, share = offseason_fa.team_fit_for(person, player, home, fits[team_id])
    released = move_news.last_released_by(conn, league_id, player.id)
    last = offseason_fa._last_team(conn, league_id, player.id)
    if n_callers is None:
        n_callers = callers(conn, league_id, player, year, ask, exclude={team_id})
    return ng.Stance(
        ask_salary=ask.salary,
        ask_years=ask.years,
        age=player.age,
        fit=fit,
        share=share,
        ego=person.traits["ego"],
        temper=person.traits["temper"],
        loyalty=person.traits["loyalty"],
        easygoing=person.type == "Easygoing",
        star=is_star(conn, league_id, player, year),
        callers=n_callers,
        old_club=last == team_id and released != team_id,
        released_by=released == team_id,
        minimum=minimum(conn, league_id, year),
    )


def _frozen_text(frozen: int, week: int) -> str:
    left = frozen - week
    if left <= 1:
        return "He won't take your calls until next week."
    return f"He won't take your calls for {left} weeks."


def preview(conn, league_id: str, team_id: str, player_id: str) -> dict:
    """For the offer dialog: his asking deal, the lowest salary allowed, a
    hint or two on where he stands, offers left this week, any counter that
    stands, and the owner warning at his asking price."""
    _, season_id, year = _open(conn, league_id)
    p = _free_agent(conn, league_id, player_id)
    ask = asking(conn, league_id, p, year)
    s = stance(conn, league_id, season_id, year, team_id, p, ask)
    week = talk_week(conn, league_id)
    offers, counter, frozen = _this_week(
        _talks(conn, league_id, team_id, player_id), week
    )
    return {
        "ask_salary": ask.salary,
        "ask_text": ct.format_salary(ask.salary),
        "ask_years": ask.years,
        "min_salary": s.minimum,
        "max_years": offseason_fa.MAX_BID_YEARS,
        "hints": ng.hints(s),
        "offers_left": max(0, ng.OFFERS_PER_WEEK - offers),
        "counter": _counter_view(counter),
        "frozen": _frozen_text(frozen, week) if frozen else None,
        "warning": free_agents.budget_warning(
            conn, league_id, team_id, year, ask.salary
        ),
    }


def _counter_view(counter) -> dict | None:
    if not counter:
        return None
    return {
        "salary": counter[0],
        "years": counter[1],
        "salary_text": ct.format_salary(counter[0]),
    }


# ── Making an offer ──────────────────────────────────────────────────────────


def offer(
    conn,
    league_id: str,
    team_id: str,
    player_id: str,
    salary,
    years,
    n_callers: int | None = None,
    before_sign=None,
) -> dict:
    """Offer him a salary and seasons. He signs ("signed"), says what he'd
    take ("counter"), or stops taking the club's calls ("insulted"). Taking
    the counter that stands this week doesn't count as another offer."""
    try:
        salary, years = int(salary), int(years)
    except (TypeError, ValueError) as e:
        raise OfferError("Give a salary and a number of seasons.") from e
    with league_lock(conn, league_id, wait=free_agents.MOVE_WAIT):
        league, season_id, year = _open(conn, league_id)
        p = _free_agent(conn, league_id, player_id)
        if not 1 <= years <= offseason_fa.MAX_BID_YEARS:
            raise OfferError(f"Offer 1 to {offseason_fa.MAX_BID_YEARS} seasons.")
        low = minimum(conn, league_id, year)
        if salary < low:
            raise OfferError(
                f"Offer at least {ct.format_salary(low)} a season, the minimum."
            )
        if salary > ct.MAX_SALARY * 2:
            raise OfferError("That's more than anyone is paid.")
        week = talk_week(conn, league_id)
        offers, counter, frozen = _this_week(
            _talks(conn, league_id, team_id, player_id), week
        )
        if frozen:
            raise OfferError(_frozen_text(frozen, week))
        refusal = BudgetRepository(conn).refusal(league_id, team_id, year, salary)
        if refusal:
            raise OfferError(refusal)
        ask = asking(conn, league_id, p, year)
        s = stance(conn, league_id, season_id, year, team_id, p, ask, n_callers)
        taking_counter = (
            counter is not None and salary >= counter[0] and years == counter[1]
        )
        if not taking_counter and offers >= ng.OFFERS_PER_WEEK:
            raise OfferError(
                f"That's {ng.OFFERS_PER_WEEK} offers this week. He'll listen again next week."
                + (
                    f" His answer stands: {ct.format_salary(counter[0])} a season for {counter[1]}."
                    if counter
                    else ""
                )
            )
        if taking_counter or s.takes(salary, years):
            if before_sign and not before_sign():
                return {"result": "no room", "name": p.name}
            result = free_agents.sign(
                conn, league_id, team_id, player_id, ct.Deal(salary, years, "standard")
            )
            conn.execute(
                "DELETE FROM fa_talks WHERE league_id = %s AND player_id = %s",
                (league_id, player_id),
            )
            conn.commit()
            return {"result": "signed", **result}
        offers += 1
        want = s.counter(years, round_up)
        seed = f"insult:{league_id}:{team_id}:{player_id}:{week}:{offers}"
        if s.insulted(salary, want, seed):
            _save_talks(
                conn,
                league_id,
                team_id,
                player_id,
                week,
                offers,
                None,
                week + ng.FREEZE_WEEKS,
            )
            conn.commit()
            return {
                "result": "insulted",
                "name": p.name,
                "line": f"He's insulted. He won't take your calls for {ng.FREEZE_WEEKS} weeks.",
            }
        _save_talks(
            conn, league_id, team_id, player_id, week, offers, (want, years), None
        )
        conn.commit()
        return {
            "result": "counter",
            "name": p.name,
            "counter": _counter_view((want, years)),
            "hints": ng.hints(s),
            "offers_left": max(0, ng.OFFERS_PER_WEEK - offers),
            "warning": free_agents.budget_warning(conn, league_id, team_id, year, want),
            "blocked": BudgetRepository(conn).refusal(league_id, team_id, year, want),
        }


# ── AI teams ─────────────────────────────────────────────────────────────────


def ai_opening(spending: int, risk: int) -> float:
    """How close to his ask an AI GM opens: a miser's GM low, a spender's
    near the ask; a gambler a little higher, a cautious GM lower."""
    share = AI_OPEN_LOW + (AI_OPEN_HIGH - AI_OPEN_LOW) * spending / 100
    share += AI_OPEN_RISK * (risk - 50) / 50
    return max(AI_OPEN_LOW - AI_OPEN_RISK, min(AI_OPEN_HIGH, share))


def ai_takes_counter(risk: int, roll: float) -> bool:
    return roll < AI_TAKE_LOW + (AI_TAKE_HIGH - AI_TAKE_LOW) * risk / 100


def ai_offer(
    conn,
    league_id: str,
    team_id: str,
    player,
    ask: ct.Deal,
    room: float,
    spending: int,
    risk: int,
    rng: random.Random,
    n_callers: int,
    before_sign=None,
) -> bool:
    """An AI team tries to sign him for less than his ask: it opens by its
    owner and GM, and takes his counter if the GM's nerve and the budget
    allow (never more than his ask: it could just sign him at that).
    before_sign makes room in the minors once he's said yes. Returns
    whether he signed."""

    def go(salary: int) -> dict | None:
        try:
            return offer(
                conn,
                league_id,
                team_id,
                player.id,
                salary,
                ask.years,
                n_callers,
                before_sign,
            )
        except OfferError:
            return None

    year = ContractRepository(conn).current_year(league_id)
    low = minimum(conn, league_id, year)
    opening = ask.salary
    if ask.salary > low:
        opening = max(low, ct.round_salary(ask.salary * ai_opening(spending, risk)))
    result = go(opening)
    if not result or result["result"] != "counter":
        return bool(result) and result["result"] == "signed"
    want = min(result["counter"]["salary"], ask.salary)
    if want > room or result.get("blocked") or not ai_takes_counter(risk, rng.random()):
        return False
    result = go(want)
    return bool(result) and result["result"] == "signed"


def ai_leanings(conn, league_id: str) -> dict[str, tuple[int, int]]:
    """Each team's (owner Spending, GM Risk), 50 where unknown."""
    from src.api.services import personas

    lean = personas.leanings(conn, league_id)
    seats = owners.ensure(conn, league_id)
    out = {}
    for team_id in set(lean) | set(seats):
        traits = (seats.get(team_id) or {}).get("traits") or {}
        out[team_id] = (
            int(traits.get("spending", 50)),
            lean[team_id].risk if team_id in lean else 50,
        )
    return out
