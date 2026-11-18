# src/api/services/resign_offers.py
"""
Negotiating a re-sign (Josh, 2026-11-18). On the Expiring Deals tab a GM
can re-sign a player at his asking price, let him go, or make him an offer:
a salary and a number of seasons. He answers right away, like a free agent
(src/api/services/fa_offers.py), with the same rules from his side
(src/player/negotiation.py Stance, home=True):

- His ask is his renewal price, his mood already in it. An agreed deal is
  kept on his contract_choices row and replaces that price when the
  offseason runs, on the room line and in Re-sign All.
- A club makes negotiation.OFFERS_PER_WINDOW offers to a player in the
  window. His counter stands until the window closes.
- A lowball leaves a grudge (HappinessRepository.add_grudge). A big one may
  insult him: talks close for the window. One who could walk (a veteran,
  or an unhappy player) then raises his price or refuses to re-sign; one
  under team control holds a bigger grudge.
- No offers to an arbitration player, a refuser, one asking the minimum, or
  in a league without money (offseason_fa.no_offer).

AI teams negotiate their own re-signs too (Josh, 2026-11-18: ai_negotiate),
when the offseason runs, for the players they mean to keep. The GM opens by
the owner's Spending and the GM's Risk, like a free agent offer
(fa_offers.ai_opening), nearer the ask the more loyal the GM is to his own
players (the Loyalty dial). The player answers by the same rules as for a
person, grudges, insults and refusals included. A GM takes his counter by
Risk and Loyalty; one that walks away loses a player who can walk, and
re-signs one under team control at his asking price.
"""

from __future__ import annotations

import random

from src.api.services import fa_offers, offseason_fa
from src.db.locks import league_lock
from src.db.repositories.happiness_repo import HappinessRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.league.league_modes import has_money
from src.player import contracts as ct
from src.player import happiness as hp
from src.player import negotiation as ng


class ResignOfferError(Exception):
    """An offer that can't be made, with the reason to show."""


def _window(conn, league_id: str) -> tuple[str, int]:
    league = LeagueRepository(conn).get_by_id(league_id)
    if not league or league["state"] != "offseason":
        raise ResignOfferError("Expiring deals are decided in the offseason.")
    if not has_money(league):
        raise ResignOfferError("This league has no contracts to negotiate.")
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    try:
        year = offseason_fa._year(conn, league_id)
    except offseason_fa.OffseasonFAError as e:
        raise ResignOfferError(str(e)) from e
    return season_id, year


def _row(conn, league_id: str, team_id: str, player_id: str, year: int):
    mine = offseason_fa.expiring(conn, league_id, year, [team_id])
    row = next((r for r in mine if r["player_id"] == player_id), None)
    if row is None:
        raise ResignOfferError("His deal isn't ending with this season.")
    return row, mine


def _talks(conn, player_id: str, year: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM resign_talks WHERE player_id = %s AND year = %s",
        (player_id, year),
    ).fetchone()
    return dict(row) if row else None


def _save_talks(conn, league_id, team_id, player_id, year, **fields):
    talks = _talks(conn, player_id, year) or {}
    vals = {
        "offers": talks.get("offers", 0),
        "counter_salary": talks.get("counter_salary"),
        "counter_years": talks.get("counter_years"),
        "closed": talks.get("closed", False),
        "bumped": talks.get("bumped", False),
        "refused": talks.get("refused", False),
    }
    vals.update(fields)
    conn.execute(
        """INSERT INTO resign_talks (league_id, player_id, team_id, year, offers,
                                     counter_salary, counter_years, closed,
                                     bumped, refused)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (player_id, year) DO UPDATE
           SET team_id = excluded.team_id, offers = excluded.offers,
               counter_salary = excluded.counter_salary,
               counter_years = excluded.counter_years,
               closed = excluded.closed, bumped = excluded.bumped,
               refused = excluded.refused""",
        (
            league_id,
            player_id,
            team_id,
            year,
            vals["offers"],
            vals["counter_salary"],
            vals["counter_years"],
            vals["closed"],
            vals["bumped"],
            vals["refused"],
        ),
    )


def _minimum(row: dict) -> int:
    return ct.round_salary(ct.MIN_SALARY * row["scale"], row["scale"])


def _underpaid(conn, league_id: str, player_id: str) -> bool:
    """Whether he thinks he's underpaid (his money satisfaction, last mood)."""
    r = conn.execute(
        """SELECT detail FROM player_moods
           WHERE player_id = %s AND league_id = %s
           ORDER BY updated_on DESC LIMIT 1""",
        (player_id, league_id),
    ).fetchone()
    money = ((r["detail"] or {}).get("drives") or {}).get("money") if r else None
    return bool(money) and money[1] == "under"


def stance(
    conn,
    league_id: str,
    season_id: str,
    year: int,
    row: dict,
    fits: dict | None = None,
    teams: dict | None = None,
) -> ng.Stance:
    """Where an expiring player stands with his own club. fits: the
    clubs' offseason_fa._fits, and teams: AI rosters for fa_offers.callers,
    when already looked up (the AI teams' talks do them all at once)."""
    p, team_id, ask = row["player"], row["team_id"], row["ask"]
    happy = HappinessRepository(conn, league_id)
    person = happy.personalities([p.id]).get(p.id) or hp.personality_for(p.id)
    home = conn.execute(
        "SELECT home_region FROM players WHERE id = %s", (p.id,)
    ).fetchone()
    if fits is None or team_id not in fits:
        fits = offseason_fa._fits(conn, league_id, season_id, year, [team_id])
    fit, share = offseason_fa.team_fit_for(
        person, p, home["home_region"] if home else None, fits[team_id]
    )
    callers = (
        fa_offers.callers(conn, league_id, p, year, ask, exclude={team_id}, teams=teams)
        if row["market"]
        else 0
    )
    return ng.Stance(
        ask_salary=ask.salary,
        ask_years=ask.years,
        age=p.age,
        fit=fit,
        share=share,
        ego=person.traits["ego"],
        temper=person.traits["temper"],
        loyalty=person.traits["loyalty"],
        easygoing=person.type == "Easygoing",
        star=fa_offers.is_star(conn, league_id, p, year),
        callers=callers,
        minimum=_minimum(row),
        money=person.drives["money"],
        home=True,
        seasons=row["seasons"],
    )


def _counter_view(salary, years) -> dict | None:
    if not salary:
        return None
    return {"salary": salary, "years": years, "salary_text": ct.format_salary(salary)}


def preview(conn, league_id: str, team_id: str, player_id: str) -> dict:
    """For the offer dialog: his ask, hints, the warning about lowballs,
    offers left, and any counter that stands."""
    season_id, year = _window(conn, league_id)
    row, _ = _row(conn, league_id, team_id, player_id, year)
    why = offseason_fa.no_offer(row)
    if why:
        raise ResignOfferError(why)
    s = stance(conn, league_id, season_id, year, row)
    talks = _talks(conn, player_id, year) or {}
    offers = talks.get("offers", 0)
    grudge = HappinessRepository(conn, league_id).grudge(player_id, team_id, year) > 0
    mood = HappinessRepository(conn, league_id).latest_moods([player_id]).get(player_id)
    can_walk = row["market"] is not None
    return {
        "ask_salary": row["ask"].salary,
        "ask_text": ct.format_salary(row["ask"].salary),
        "ask_years": row["ask"].years,
        "min_salary": s.minimum,
        "max_years": offseason_fa.MAX_BID_YEARS,
        "can_walk": can_walk,
        "hints": ng.resign_hints(
            s, mood, _underpaid(conn, league_id, player_id), grudge
        ),
        "warnings": ng.resign_warnings(s, can_walk, grudge),
        "offers_left": max(0, ng.OFFERS_PER_WINDOW - offers),
        "counter": _counter_view(
            talks.get("counter_salary"), talks.get("counter_years")
        ),
        "agreed": (
            _counter_view(row["deal"].salary, row["deal"].years)
            if row["agreed"]
            else None
        ),
    }


def offer(conn, league_id: str, team_id: str, player_id: str, salary, years) -> dict:
    """Offer an expiring player a salary and seasons. He agrees ("signed":
    the deal is kept as the team's re-sign call), says what he'd take
    ("counter"), breaks off talks ("insulted": his price goes up, or a
    player under team control just holds it against you), or won't re-sign
    at all ("refused"). Taking the counter that stands doesn't count as
    another offer."""
    try:
        salary, years = int(salary), int(years)
    except (TypeError, ValueError) as e:
        raise ResignOfferError("Give a salary and a number of seasons.") from e
    with league_lock(conn, league_id):
        season_id, year = _window(conn, league_id)
        row, mine = _row(conn, league_id, team_id, player_id, year)
        why = offseason_fa.no_offer(row)
        if why:
            raise ResignOfferError(why)
        if not 1 <= years <= offseason_fa.MAX_BID_YEARS:
            raise ResignOfferError(f"Offer 1 to {offseason_fa.MAX_BID_YEARS} seasons.")
        low = _minimum(row)
        if salary < low:
            raise ResignOfferError(
                f"Offer at least {ct.format_salary(low)} a season, the minimum."
            )
        if salary > ct.MAX_SALARY * 2:
            raise ResignOfferError("That's more than anyone is paid.")
        refusal = offseason_fa._resign_refusal(
            conn, league_id, team_id, year, mine, row, salary
        )
        if refusal:
            raise ResignOfferError(refusal)
        talks = _talks(conn, player_id, year) or {}
        offers = talks.get("offers", 0)
        counter = talks.get("counter_salary"), talks.get("counter_years")
        taking_counter = (
            bool(counter[0]) and salary >= counter[0] and years == counter[1]
        )
        if not taking_counter and offers >= ng.OFFERS_PER_WINDOW:
            raise ResignOfferError(
                f"That's {ng.OFFERS_PER_WINDOW} offers. Re-sign him at his price"
                + (
                    f", take his answer ({ct.format_salary(counter[0])} a season for {counter[1]}),"
                    if counter[0]
                    else ""
                )
                + " or let him go."
            )
        s = stance(conn, league_id, season_id, year, row)
        if taking_counter or s.takes(salary, years):
            conn.execute(
                """INSERT INTO contract_choices
                       (league_id, player_id, team_id, year, choice, salary, years)
                   VALUES (%s, %s, %s, %s, 'resign', %s, %s)
                   ON CONFLICT (player_id, year) DO UPDATE
                   SET choice = 'resign', team_id = excluded.team_id,
                       salary = excluded.salary, years = excluded.years""",
                (league_id, player_id, team_id, year, salary, years),
            )
            conn.commit()
            return {
                "result": "signed",
                "name": row["player"].name,
                "salary": salary,
                "salary_text": ct.format_salary(salary),
                "years": years,
            }
        offers += 1
        want = s.counter(years, fa_offers.round_up)
        happy = HappinessRepository(conn, league_id)
        roll = random.Random(
            f"resign-insult:{league_id}:{player_id}:{year}:{offers}"
        ).random()
        if s.home_insulted(salary, want, roll):
            happy.add_grudge(player_id, team_id, year, s.grudge(salary, want, True))
            # Back to no call: his old price is gone.
            conn.execute(
                "DELETE FROM contract_choices WHERE player_id = %s AND year = %s",
                (player_id, year),
            )
            can_walk = row["market"] is not None
            refused = (
                can_walk
                and random.Random(
                    f"resign-refuse:{league_id}:{player_id}:{year}"
                ).random()
                < s.refuse_chance()
            )
            _save_talks(
                conn,
                league_id,
                team_id,
                player_id,
                year,
                offers=offers,
                closed=True,
                bumped=can_walk and not refused,
                refused=refused,
            )
            conn.commit()
            name = row["player"].name
            if refused:
                return {
                    "result": "refused",
                    "name": name,
                    "line": "He's insulted, and he won't re-sign with you. He'll test the market.",
                }
            if can_walk:
                bumped = ct.round_salary(
                    row["ask"].salary * (1 + ng.HOME_BUMP), row["scale"]
                )
                return {
                    "result": "insulted",
                    "name": name,
                    "line": (
                        "He's insulted and done talking. He'll still re-sign, "
                        f"but his price is up to {ct.format_salary(bumped)} a season."
                    ),
                }
            return {
                "result": "insulted",
                "name": name,
                "line": (
                    "He's insulted and done talking. He can't leave, but he'll "
                    "carry it into next season."
                ),
            }
        happy.add_grudge(player_id, team_id, year, s.grudge(salary, want))
        _save_talks(
            conn,
            league_id,
            team_id,
            player_id,
            year,
            offers=offers,
            counter_salary=want,
            counter_years=years,
        )
        conn.commit()
        stung = salary < ng.GRUDGE_LINE * want and not s.easygoing
        # This offer's sting has its own line; an older grudge gets the hint.
        grudge = not stung and happy.grudge(player_id, team_id, year) > 0
        mood = happy.latest_moods([player_id]).get(player_id)
        return {
            "result": "counter",
            "name": row["player"].name,
            "counter": _counter_view(want, years),
            "hints": ng.resign_hints(
                s, mood, _underpaid(conn, league_id, player_id), grudge
            ),
            "stung": stung,
            "offers_left": max(0, ng.OFFERS_PER_WINDOW - offers),
            "blocked": offseason_fa._resign_refusal(
                conn, league_id, team_id, year, mine, row, want
            ),
        }


# ── AI teams ─────────────────────────────────────────────────────────────────

# A loyal GM (Loyalty dial 100) opens this much nearer the ask, and is this
# much likelier to take the counter; one who cuts bait fast, less.
AI_LOYAL_OPEN = 0.05
AI_LOYAL_TAKE = 0.15


def ai_opening(spending: int, risk: int, loyalty: int) -> float:
    """How close to his ask an AI GM opens with his own player."""
    share = fa_offers.ai_opening(spending, risk) + AI_LOYAL_OPEN * (loyalty - 50) / 50
    low = fa_offers.AI_OPEN_LOW - fa_offers.AI_OPEN_RISK - AI_LOYAL_OPEN
    return max(low, min(1.0, share))


def ai_takes(risk: int, loyalty: int, roll: float) -> bool:
    """Whether an AI GM takes his own player's counter."""
    chance = fa_offers.AI_TAKE_LOW + (
        fa_offers.AI_TAKE_HIGH - fa_offers.AI_TAKE_LOW
    ) * (risk / 100)
    chance += AI_LOYAL_TAKE * (loyalty - 50) / 50
    return roll < chance


def _ai_dials(conn, league_id: str) -> dict[str, tuple[int, int, int]]:
    """Each team's (owner Spending, GM Risk, GM Loyalty), 50 where unknown."""
    from src.api.services import owners, personas

    lean = personas.leanings(conn, league_id)
    seats = owners.ensure(conn, league_id)
    out = {}
    for team_id in set(lean) | set(seats):
        traits = (seats.get(team_id) or {}).get("traits") or {}
        gm = lean.get(team_id)
        out[team_id] = (
            int(traits.get("spending", 50)),
            gm.risk if gm else 50,
            gm.loyalty if gm else 50,
        )
    return out


def ai_negotiate(
    conn, league_id: str, year: int, rows: list[dict], keep: set[str], humans
) -> tuple[dict[str, ct.Deal | None], set[str]]:
    """AI teams talk with the expiring players they mean to keep (keep).
    Returns ({player: the deal he signs, or None if he goes to market},
    players who refused after an insult). Players not in it re-sign at their
    asking price, as before."""
    talks = [
        r
        for r in rows
        if r["team_id"] not in humans
        and r["player_id"] in keep
        and not offseason_fa.no_offer(r)
    ]
    if not talks:
        return {}, set()
    from src.api.services import ai_free_agents

    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    dials = _ai_dials(conn, league_id)
    fits = offseason_fa._fits(
        conn, league_id, season_id, year, sorted({r["team_id"] for r in talks})
    )
    teams = None
    if any(r["market"] for r in talks):
        teams = {
            t["team_id"]: ai_free_agents.role_values(
                ai_free_agents._rated_team(conn, league_id, t["team_id"])
            )
            for t in conn.execute(
                "SELECT DISTINCT team_id FROM league_season_teams WHERE league_id = %s",
                (league_id,),
            ).fetchall()
            if t["team_id"] not in humans
        }
    happy = HappinessRepository(conn, league_id)
    deals: dict[str, ct.Deal | None] = {}
    refused: set[str] = set()
    for r in talks:
        pid, ask = r["player_id"], r["ask"]
        spending, risk, loyalty = dials.get(r["team_id"], (50, 50, 50))
        opening = max(
            _minimum(r),
            ct.round_salary(
                ask.salary * ai_opening(spending, risk, loyalty), r["scale"]
            ),
        )
        if opening >= ask.salary:
            continue
        s = stance(conn, league_id, season_id, year, r, fits, teams)
        if s.takes(opening, ask.years):
            deals[pid] = ct.Deal(opening, ask.years, ask.kind)
            continue
        want = min(ask.salary, s.counter(ask.years, fa_offers.round_up))
        rng = random.Random(f"ai-resign:{league_id}:{pid}:{year}")
        can_walk = r["market"] is not None
        if s.home_insulted(opening, want, rng.random()):
            happy.add_grudge(pid, r["team_id"], year, s.grudge(opening, want, True))
            if not can_walk:
                continue  # he can't leave: tendered at his price
            if rng.random() < s.refuse_chance():
                deals[pid] = None
                refused.add(pid)
            elif ai_takes(risk, loyalty, rng.random()):
                bumped = ct.round_salary(ask.salary * (1 + ng.HOME_BUMP), r["scale"])
                deals[pid] = ct.Deal(bumped, ask.years, ask.kind)
            else:
                deals[pid] = None
            continue
        happy.add_grudge(pid, r["team_id"], year, s.grudge(opening, want))
        if ai_takes(risk, loyalty, rng.random()):
            deals[pid] = ct.Deal(want, ask.years, ask.kind)
        elif can_walk:
            deals[pid] = None
        # Under team control and the GM won't meet him: tendered at his ask.
    return deals, refused
