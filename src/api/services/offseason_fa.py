# src/api/services/offseason_fa.py
"""
Offseason free agency (free agency phase 2, PR 3; Josh's decisions
2026-11-05).

1. The re-sign window (league state 'offseason'). Players whose deals end
   with this season either re-sign with their team or go to market:
   - Veterans (MARKET_SEASONS seasons or more under contract in the league)
     and unhappy players (mood "unhappy" or worse) go to market unless their
     team re-signs them now, at their price. An arbitration player stays
     under team control even when unhappy (Josh, 2026-11-09): he can't walk,
     though his team can still let him go.
   - Everyone else is tendered (re-signed) by default unless their GM lets
     them go, as long as the owner's hard limit has room for him next
     season (Josh, 2026-11-07: re-signs answer to the owner; 2026-11-09:
     judged on next season, when the expiring salaries are gone).
   A GM makes the call on the Expiring Deals tab (contract_choices). AI teams
   re-sign the best first while their owner's budget has room (market-bound
   players only from the 40-man) and let fringe players go rather than pay
   them more than the minimum (_keeps). The window closes when the
   offseason runs (close_window): re-signed players get their new deal, and
   the ones let go become free agents.

2. Bidding (from the draft into the preseason, while leagues.fa_bidding is
   set: bidding_open). Free agents can't be signed outright: teams bid a
   salary and a number of seasons (fa_bids). AI teams bid on free agents
   who fill a hole, within their budget, as the bids settle. Bids stay open
   past the draft so a GM can bid knowing who they drafted (Josh,
   2026-11-12).

3. Settling (close_bidding, partway through the preseason: the solo GM's
   Close Bidding step, the first preseason period in a multiplayer league,
   and at the latest just before Opening Day). Each free agent with bids,
   best first, takes the one he likes best: the money against his asking
   price, plus how well the team suits him (winning, home, market, coaching:
   src/player/happiness.py team_fit), as much as he cares about those. He
   won't take less than MIN_BID_SHARE of his asking price. A bid the
   owner's hard limit no longer allows is skipped, and so is one from a
   team whose minors are full. Free agents nobody gets can still be signed
   at their asking price in the rest of the preseason and the season.
"""

from __future__ import annotations

import random
from datetime import date

from src.api.grade_curves import GRADES
from src.api.services import (
    ai_free_agents,
    free_agents,
    front_office,
    owners,
    waivers,
)
from src.api.services.news.moves import shown_grade
from src.api.services.news.names import Names
from src.db.locks import league_lock
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import (
    FORTY_MAN_STATUSES,
    SIGNED_STATUSES,
    ContractRepository,
)
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.happiness_repo import HappinessRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.news_repo import NewsRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_state_repo import TeamStateRepository
from src.league.offseason.roster_trimmer import MINORS_LIMIT
from src.league import money_state
from src.player import contracts as ct
from src.player import happiness as hp
from src.player import negotiation as ng
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_value import role_rating

# Seasons under contract in the league that make a player a free agent when
# his deal ends (MLB's six years of service).
MARKET_SEASONS = 6
# A free agent won't sign for less than this share of his asking price.
MIN_BID_SHARE = 0.8
# How much a perfect fit is worth to a player who cares only about fit, as a
# share of his asking price.
FIT_WEIGHT = 0.3
# Longest deal a team can offer.
MAX_BID_YEARS = 7
# Free agents an AI team bids on in one offseason.
AI_BIDS = 2


class OffseasonFAError(Exception):
    pass


def _league(conn, league_id: str) -> dict:
    league = LeagueRepository(conn).get_by_id(league_id)
    if not league:
        raise OffseasonFAError("No such league.")
    return dict(league)


def _year(conn, league_id: str) -> int:
    year = ContractRepository(conn).current_year(league_id)
    if year is None:
        raise OffseasonFAError("The league has no season.")
    return year


def _league_teams(conn, league_id: str) -> list[str]:
    return [
        r["team_id"]
        for r in conn.execute(
            "SELECT DISTINCT team_id FROM league_season_teams WHERE league_id = %s",
            (league_id,),
        ).fetchall()
    ]


# ── 1. The re-sign window ─────────────────────────────────────────────────────


def expiring(conn, league_id: str, year: int, team_ids=None) -> list[dict]:
    """Players on the league's teams whose deal ends with `year`, each with
    his new deal from next season, whether he goes to market and why, and
    his team's choice so far."""
    teams = list(team_ids) if team_ids is not None else _league_teams(conn, league_id)
    if not teams:
        return []
    rows = conn.execute(
        """
        SELECT tp.team_id, tp.player_id, ps.status, c.salary AS old_salary,
               cc.choice
        FROM team_players tp
        JOIN player_status ps ON ps.player_id = tp.player_id
        JOIN player_contracts c ON c.player_id = tp.player_id
             AND c.released_year IS NULL
             AND c.start_year <= %s AND c.start_year + c.years - 1 = %s
        LEFT JOIN contract_choices cc ON cc.player_id = tp.player_id
             AND cc.year = %s AND cc.team_id = tp.team_id
        WHERE tp.team_id = ANY(%s) AND ps.status = ANY(%s)
          AND NOT EXISTS (
              SELECT 1 FROM player_contracts n
              WHERE n.player_id = tp.player_id AND n.released_year IS NULL
                AND n.start_year > %s)
        ORDER BY tp.team_id, tp.player_id
        """,
        (year, year, year, teams, list(SIGNED_STATUSES), year),
    ).fetchall()
    if not rows:
        return []
    ids = [r["player_id"] for r in rows]
    contracts = ContractRepository(conn)
    seasons = contracts.seasons_signed(ids, year)
    happy = HappinessRepository(conn, league_id)
    happy.prepare_resign(ids, seasons)
    moods = happy.latest_moods(ids)
    scale = BudgetRepository(conn).salary_scale(league_id, year + 1)
    arb = contracts.arbitration_seasons(ids, year + 1)
    shifts = contracts.price_shifts(league_id, year + 1)
    repo = PlayerRepository(conn)
    out = []
    for r in rows:
        p = repo.look_up(r["player_id"])
        if p is None:
            continue
        deal, wants_out = contracts.renewal(
            p, year + 1, happy, scale, arb.get(p.id), shifts
        )
        arb_season = arb.get(p.id) if deal.kind == "arbitration" else None
        mood = moods.get(p.id)
        if seasons.get(p.id, 0) >= MARKET_SEASONS:
            market = "veteran"
        elif mood is not None and mood < hp.UNHAPPY and arb_season is None:
            market = "unhappy"
        else:
            market = None
        out.append(
            {
                "player_id": p.id,
                "team_id": r["team_id"],
                "status": r["status"],
                "player": p,
                "old_salary": r["old_salary"],
                "deal": deal,
                "wants_out": wants_out,
                "market": market,
                "seasons": seasons.get(p.id, 0),
                "arb_season": arb_season,
                "market_salary": (
                    contracts.market_salary(p, year + 1, scale, shifts)
                    if arb_season
                    else None
                ),
                "choice": r["choice"],
                "scale": scale,
                "shifts": shifts,
            }
        )
    return out


def choose(
    conn, league_id: str, team_id: str, player_id: str, choice: str | None
) -> dict:
    """A GM re-signs an expiring player now ('resign'), lets him go
    ('let_go'), or takes the call back (None)."""
    if choice not in ("resign", "let_go", None):
        raise OffseasonFAError("Pick re-sign or let go.")
    with league_lock(conn, league_id):
        if _league(conn, league_id)["state"] != "offseason":
            raise OffseasonFAError("Expiring deals are decided in the offseason.")
        year = _year(conn, league_id)
        mine = [e for e in expiring(conn, league_id, year, [team_id])]
        row = next((e for e in mine if e["player_id"] == player_id), None)
        if row is None:
            raise OffseasonFAError("His deal isn't ending with this season.")
        if choice is None:
            conn.execute(
                "DELETE FROM contract_choices WHERE player_id = %s AND year = %s",
                (player_id, year),
            )
        else:
            if choice == "resign":
                refusal = _resign_refusal(conn, league_id, team_id, year, mine, row)
                if refusal:
                    raise OffseasonFAError(refusal)
            conn.execute(
                """INSERT INTO contract_choices (league_id, player_id, team_id, year, choice)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (player_id, year) DO UPDATE
                   SET choice = excluded.choice, team_id = excluded.team_id""",
                (league_id, player_id, team_id, year, choice),
            )
        conn.commit()
    return {"choice": choice}


def _room(conn, league_id: str, team_id: str, year: int, human: bool) -> float:
    """How much more payroll a team can carry before its owner balks: up to
    the hard limit for a person, the budget for an AI GM, after the front
    office, the minor leagues and the luxury tax on payroll over the cap.
    Unlimited without budgets."""
    if not human:
        return ai_free_agents._budget_room(conn, league_id, team_id, year)
    s = BudgetRepository(conn).standing(league_id, team_id, year)
    if s is None:
        return float("inf")
    return s["limit_payroll_room"]


def _next_room(
    conn, league_id: str, team_id: str, year: int, human: bool, rows: list[dict]
) -> float:
    """What a team has for re-signs next season (Josh, 2026-11-09): this
    season's room plus every expiring salary, which drops off when the deals
    end. Each re-sign then costs his whole new salary, so letting a player go
    leaves room for another, and a pay cut isn't free."""
    room = _room(conn, league_id, team_id, year, human)
    return room + sum(r["old_salary"] for r in rows if r["team_id"] == team_id)


def _bank(conn, league_id: str, team_id: str) -> int:
    """The owner's bank now, or 0 without one."""
    bank = BudgetRepository(conn).banks(league_id).get(team_id)
    return max(0, bank["balance"]) if bank else 0


def _resign_refusal(
    conn, league_id: str, team_id: str, year: int, mine: list[dict], row: dict
) -> str | None:
    """Why the owner won't let a person re-sign him now, or None: his new
    salary, with the re-signs already called, has to fit next season's room.
    A person re-signing their own player may go past the limit as far as the
    owner's bank reaches (Josh, 2026-11-09, like the NBA's Bird rights): the
    owner pays it from the bank, and the losses show in their mood."""
    room = _next_room(conn, league_id, team_id, year, True, mine)
    if room == float("inf"):
        return None
    called = sum(
        r["deal"].salary
        for r in mine
        if r["choice"] == "resign" and r["player_id"] != row["player_id"]
    )
    left = room - called + _bank(conn, league_id, team_id)
    if row["deal"].salary <= left:
        return None
    have = ct.format_salary(int(left)) if left >= 1 else "nothing"
    return (
        f"Your owner won't allow it: even dipping into their bank, next season "
        f"has {have} left, and he wants "
        f"{ct.format_salary(row['deal'].salary)}. Let someone else go to make room."
    )


def next_season_money(conn, league_id: str, team_id: str) -> dict | None:
    """For the Expiring Deals tab: what's left under the owner's limit next
    season after the re-signs called so far, and how much of their bank is
    left to go past it. None without budgets."""
    year = _year(conn, league_id)
    rows = expiring(conn, league_id, year, [team_id])
    room = _next_room(conn, league_id, team_id, year, True, rows)
    if room == float("inf"):
        return None
    called = sum(r["deal"].salary for r in rows if r["choice"] == "resign")
    left = int(room - called)
    bank = _bank(conn, league_id, team_id)
    # Next season's payroll so far (Josh, 2026-11-11: the Budget tab shows
    # it too, so a Re-sign or Let go shows there right away): the deals that
    # carry over plus the re-signs called.
    payroll = BudgetRepository(conn).contracts.payroll(team_id, year)
    payroll += called - sum(r["old_salary"] for r in rows)
    return {
        "payroll_text": ct.format_salary(max(0, int(payroll))),
        "resigned": sum(1 for r in rows if r["choice"] == "resign"),
        "let_go": sum(1 for r in rows if r["choice"] == "let_go"),
        "bank_text": ct.format_salary(bank),
        "left": left,
        "left_text": ct.format_salary(abs(left)),
        "over": left < 0,
        "bank_left_text": (
            ct.format_salary(bank + min(left, 0)) if bank + min(left, 0) > 0 else "$0"
        ),
    }


def _all_plan(
    conn, league_id: str, team_id: str, year: int, rows: list[dict]
) -> dict | None:
    """Re-signing every expiring deal at once (Josh, 2026-11-09): what it
    costs next season, whether it fits under the owner's hard limit plus their
    bank, and how much of the bank it takes. None when every deal is already
    re-signed or nothing is expiring."""
    if not rows or all(r["choice"] == "resign" for r in rows):
        return None
    cost = sum(r["deal"].salary for r in rows)
    room = _next_room(conn, league_id, team_id, year, True, rows)
    if room == float("inf"):
        return {
            "count": len(rows),
            "cost": cost,
            "fits": True,
            "from_bank": 0,
            "bank": 0,
        }
    bank = _bank(conn, league_id, team_id)
    from_bank = max(0, int(cost - room))
    return {
        "count": len(rows),
        "cost": cost,
        "fits": from_bank <= bank,
        "from_bank": from_bank,
        "bank": bank,
    }


def resign_all_plan(conn, league_id: str, team_id: str) -> dict | None:
    """For the Expiring Deals tab's Re-sign All button: shown only when the plan
    fits. Adds the money as text for the warning."""
    year = _year(conn, league_id)
    plan = _all_plan(
        conn, league_id, team_id, year, expiring(conn, league_id, year, [team_id])
    )
    if plan is None or not plan["fits"]:
        return None
    return plan | {
        "cost_text": ct.format_salary(plan["cost"]),
        "from_bank_text": ct.format_salary(plan["from_bank"]),
        "bank_text": ct.format_salary(plan["bank"]),
    }


def resign_all(conn, league_id: str, team_id: str) -> dict:
    """A GM re-signs every expiring deal at once, if the owner's hard limit
    plus their bank covers all of them."""
    with league_lock(conn, league_id):
        if _league(conn, league_id)["state"] != "offseason":
            raise OffseasonFAError("Expiring deals are decided in the offseason.")
        year = _year(conn, league_id)
        mine = expiring(conn, league_id, year, [team_id])
        plan = _all_plan(conn, league_id, team_id, year, mine)
        if plan is None:
            return {"count": 0}
        if not plan["fits"]:
            raise OffseasonFAError(
                "Your owner won't allow it: even dipping into their bank, next "
                "season can't cover all of them. Re-sign them one at a time."
            )
        for r in mine:
            conn.execute(
                """INSERT INTO contract_choices (league_id, player_id, team_id, year, choice)
                   VALUES (%s, %s, %s, %s, 'resign')
                   ON CONFLICT (player_id, year) DO UPDATE
                   SET choice = excluded.choice, team_id = excluded.team_id""",
                (league_id, r["player_id"], team_id, year),
            )
        conn.commit()
    return {"count": plan["count"]}


def _keeps(
    conn, league_id: str, year: int, rows: list[dict], humans: set[str]
) -> set[str]:
    """Who re-signs (Josh, 2026-11-07: re-signs answer to the owner). Every
    expiring deal is decided here; nothing re-signs on its own later.

    - A person's call stands. Without one, a veteran or unhappy player goes
      to market, and anyone else is tendered by default if the owner's hard
      limit still has room for his raise (best players first).
    - An AI GM keeps the best first while the owner's budget has room,
      market-bound players only from the 40-man, and lets a fringe player
      (C- or worse) go rather than pay him more than the minimum.

    Each is judged on next season (Josh, 2026-11-09): the expiring salaries
    drop off, and a re-sign costs his whole new salary (_next_room)."""
    keep: set[str] = set()
    room: dict[str, float] = {}

    def fits(r: dict, force: bool = False) -> bool:
        t = r["team_id"]
        if t not in room:
            room[t] = _next_room(conn, league_id, t, year, t in humans, rows)
        cost = r["deal"].salary
        if cost > room[t] and not force:
            return False
        room[t] -= cost
        return True

    by_value = sorted(rows, key=lambda r: -role_rating(r["player"]))
    # A person's own re-sign calls stand, and come off the room first.
    for r in by_value:
        if r["team_id"] in humans and r["choice"] == "resign":
            keep.add(r["player_id"])
            fits(r, force=True)
    for r in by_value:
        if r["player_id"] in keep or r["choice"] == "let_go":
            continue
        if r["team_id"] in humans:
            if r["choice"] is None and not r["market"] and fits(r):
                keep.add(r["player_id"])
            continue
        if r["market"] and r["status"] not in FORTY_MAN_STATUSES:
            continue
        minimum = ct.round_salary(ct.MIN_SALARY * r["scale"], r["scale"])
        fringe = free_agents.is_fringe(r["player"], r.get("shifts"))
        if fringe and r["deal"].salary > minimum:
            continue
        if fits(r):
            keep.add(r["player_id"])
    return keep


def close_window(conn, league_id: str) -> dict:
    """The offseason runs: re-signed players get their new deal from next
    season, and those going to market become free agents. Returns counts."""
    year = _year(conn, league_id)
    rows = expiring(conn, league_id, year)
    humans = set(GMRepository(conn).get_human_team_ids(league_id))
    keep = _keeps(conn, league_id, year, rows, humans)
    contracts = ContractRepository(conn)
    status = PlayerStatusRepository(conn)
    teams = TeamRepository(conn)
    happy = HappinessRepository(conn, league_id)
    resigned, gone, unhappy_out, leaving = 0, [], [], []
    for r in rows:
        pid, team = r["player_id"], r["team_id"]
        action = "resign" if pid in keep else "go"
        if action == "resign":
            contracts.insert_deal(
                pid,
                league_id,
                team,
                r["deal"],
                year + 1,
                guaranteed=r["status"] in FORTY_MAN_STATUSES,
            )
            if r["wants_out"]:
                unhappy_out.append((pid, team))
            resigned += 1
        elif action == "go":
            teams.remove_player(team, pid)
            status.set_status(pid, "free_agent")
            gone.append((pid, team))
            leaving.append(r)
    for pid, team in gone:
        conn.execute(
            """DELETE FROM gm_lineup_preferences
               WHERE player_id = %s
                 AND gm_id IN (SELECT id FROM gms WHERE team_id = %s)""",
            (pid, team),
        )
    if unhappy_out:
        happy.request_trades(unhappy_out, year + 1)
    _news_market(conn, league_id, year, gone)
    _news_departures(conn, league_id, year, leaving, humans)
    conn.execute(
        "DELETE FROM contract_choices WHERE league_id = %s AND year <= %s",
        (league_id, year),
    )
    return {"resigned": resigned, "to_market": len(gone)}


def _news_market(conn, league_id: str, year: int, gone: list[tuple[str, str]]):
    """One story: who hit the market, the best few by name."""
    if not gone:
        return
    repo = PlayerRepository(conn)
    players = [p for p in (repo.look_up(pid) for pid, _ in gone) if p]
    players.sort(key=lambda p: -role_rating(p))
    names = ", ".join(f"{p.first_name} {p.last_name}" for p in players[:4])
    more = len(players) - 4
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    NewsRepository(conn).add(
        league_id,
        season_id,
        f"{year}-11-01",
        "free_agency",
        f"fa-market:{year}",
        f"{len(players)} players hit free agency",
        names
        + (f" and {more} more" if more > 0 else "")
        + ". Teams bid from the draft into the preseason; players choose when bidding closes.",
        weight=2,
        player_ids=[p.id for p in players[:4]],
    )


# A player who leaves his team at this grade or better gets his own story
# (Josh, 2026-11-09); the rest from a person's team share one.
DEPARTURE_STORY_GRADE = "B-"


def _why_gone(r: dict, human: bool) -> str:
    """Why an expiring player didn't re-sign, as the story tells it."""
    if r["choice"] == "let_go":
        return "let him go" if human else "declined to re-sign him"
    if r["market"] == "veteran":
        return (
            f"didn't re-sign him after {r['seasons']} seasons, so he tests the market"
        )
    if r["market"] == "unhappy":
        return "couldn't keep him; he's unhappy and wants a fresh start"
    if human:
        return "couldn't fit him under the owner's limit next season"
    return "passed on him at his new price"


def _news_departures(
    conn, league_id: str, year: int, leaving: list[dict], humans: set[str]
) -> None:
    """Players who left their team for free agency: a story each for the
    good ones (DEPARTURE_STORY_GRADE or better), and one roundup per
    person's team for the rest."""
    if not leaving:
        return
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    nm = Names(conn, league_id)
    nm.load_players([r["player_id"] for r in leaving])
    news = NewsRepository(conn)
    cutoff = GRADES.index(DEPARTURE_STORY_GRADE)
    rest: dict[str, list] = {}
    told: set[str] = set()
    for r in sorted(leaving, key=lambda r: -role_rating(r["player"])):
        p, team = r["player"], r["team_id"]
        human = team in humans
        grade = shown_grade(p)
        if GRADES.index(grade) > cutoff:
            if human:
                rest.setdefault(team, []).append(p)
            continue
        told.add(team)
        club = nm.team(team)
        name = nm.player(p.id)
        news.add(
            league_id,
            season_id,
            f"{year}-11-01",
            "free_agency",
            f"fa-leave:{year}:{p.id}",
            f"{name} leaves the {club} for free agency",
            f"The {club} {_why_gone(r, human)}. {grade} {p.position}, age {p.age}, "
            f"was making {ct.format_salary(r['old_salary'])} and asks "
            f"{ct.format_salary(r['deal'].salary)}. Teams bid from the draft into the preseason.",
            weight=3 if human or grade.startswith("A") else 2,
            team_ids=[team],
            player_ids=[p.id],
        )
    for team, players in rest.items():
        club = nm.team(team)
        listed = ", ".join(
            f"{nm.player(p.id)} ({shown_grade(p)} {p.position})" for p in players[:6]
        )
        more = len(players) - 6
        n = len(players)
        news.add(
            league_id,
            season_id,
            f"{year}-11-01",
            "free_agency",
            f"fa-leave-rest:{year}:{team}",
            f"{n}{' more' if team in told else ''} player{'s' if n != 1 else ''} "
            f"leave{'' if n != 1 else 's'} "
            f"the {club} for free agency",
            listed + (f" and {more} more." if more > 0 else "."),
            weight=1,
            team_ids=[team],
            player_ids=[p.id for p in players[:6]],
        )


def expiring_view(conn, league_id: str, team_id: str) -> list[dict]:
    """A GM's expiring deals for the Expiring Deals tab."""
    year = _year(conn, league_id)
    out = []
    rows = expiring(conn, league_id, year, [team_id])
    keep = _keeps(conn, league_id, year, rows, {team_id})
    for r in rows:
        d = r["deal"]
        if r["choice"] == "resign":
            fate = "resign"
        elif r["choice"] == "let_go" or r["market"]:
            fate = "go"
        elif r["player_id"] in keep:
            fate = "auto"
        else:
            fate = "no_room"
        out.append(
            {
                "player_id": r["player_id"],
                "status": r["status"],
                "salary": d.salary,
                "salary_text": ct.format_salary(d.salary),
                "years": d.years,
                "kind": d.kind,
                "old_salary_text": ct.format_salary(r["old_salary"]),
                "market": r["market"],
                "seasons": r["seasons"],
                # Arbitration (Josh, 2026-11-09): which season of the
                # MARKET_SEASONS before the market his new deal is for, and
                # his market price the arbitration share is taken from.
                "arb_season": r["arb_season"],
                "arb_of": MARKET_SEASONS,
                "arb_share": (
                    round(ct.ARBITRATION_SHARE[r["arb_season"]] * 100)
                    if r["arb_season"]
                    else None
                ),
                "market_salary_text": (
                    ct.format_salary(r["market_salary"]) if r["market_salary"] else None
                ),
                "choice": r["choice"],
                "fate": fate,
                "wants_out": r["wants_out"],
            }
        )
    return out


# ── 2. Bidding ────────────────────────────────────────────────────────────────


def bidding_open_for(league: dict | None) -> bool:
    """Bids are open: from the draft into the preseason, until they settle."""
    return bool(
        league
        and league.get("state") in ("draft", "preseason")
        and league.get("fa_bidding")
    )


def bidding_open(conn, league_id: str) -> bool:
    return bidding_open_for(LeagueRepository(conn).get_by_id(league_id))


CLOSED = "Free agent bidding is closed. Sign him at his asking price."


def _biddable(conn, league_id: str, player_id: str) -> object:
    p = PlayerRepository(conn).look_up(player_id)
    if (
        p is None
        or not free_agents._in_league(conn, league_id, player_id)
        or PlayerStatusRepository(conn).get_status(player_id) != "free_agent"
    ):
        raise OffseasonFAError("He isn't a free agent.")
    if waivers.on_waivers(conn, player_id):
        raise OffseasonFAError("He's on waivers. Claim him instead.")
    return p


def asking(conn, league_id: str, player, year: int) -> ct.Deal:
    return free_agents.asking_deal(
        player,
        year,
        free_agents.price_scale(conn, league_id, year),
        shifts=free_agents.price_shifts(conn, league_id, year),
    )


def bid_preview(conn, league_id: str, team_id: str, player_id: str) -> dict:
    """His asking deal, the team's bid so far, and how many bids he has."""
    if not bidding_open_for(_league(conn, league_id)):
        raise OffseasonFAError(CLOSED)
    year = _year(conn, league_id)
    p = _biddable(conn, league_id, player_id)
    ask = asking(conn, league_id, p, year)
    mine = conn.execute(
        "SELECT salary, years FROM fa_bids WHERE player_id = %s AND team_id = %s AND year = %s",
        (player_id, team_id, year),
    ).fetchone()
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM fa_bids WHERE player_id = %s AND year = %s",
        (player_id, year),
    ).fetchone()["n"]
    return {
        "ask_salary": ask.salary,
        "ask_text": ct.format_salary(ask.salary),
        "ask_years": ask.years,
        "min_salary": ct.MIN_SALARY,
        "max_years": MAX_BID_YEARS,
        "bid": dict(mine) if mine else None,
        "bids": count,
        "warning": free_agents.budget_warning(
            conn, league_id, team_id, year, ask.salary
        ),
    }


def place_bid(
    conn, league_id: str, team_id: str, player_id: str, salary: int, years: int
) -> dict:
    with league_lock(conn, league_id):
        if not bidding_open_for(_league(conn, league_id)):
            raise OffseasonFAError(CLOSED)
        year = _year(conn, league_id)
        _biddable(conn, league_id, player_id)
        try:
            salary, years = int(salary), int(years)
        except (TypeError, ValueError) as e:
            raise OffseasonFAError("Give a salary and a number of seasons.") from e
        if not 1 <= years <= MAX_BID_YEARS:
            raise OffseasonFAError(f"Offer 1 to {MAX_BID_YEARS} seasons.")
        if salary < ct.MIN_SALARY or salary > ct.MAX_SALARY * 2:
            raise OffseasonFAError(
                f"Offer at least {ct.format_salary(ct.MIN_SALARY)} a season."
            )
        refusal = BudgetRepository(conn).refusal(league_id, team_id, year, salary)
        if refusal:
            raise OffseasonFAError(refusal)
        conn.execute(
            """INSERT INTO fa_bids (league_id, player_id, team_id, year, salary, years)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (player_id, team_id, year) DO UPDATE
               SET salary = excluded.salary, years = excluded.years""",
            (league_id, player_id, team_id, year, salary, years),
        )
        conn.commit()
    return {"salary_text": ct.format_salary(salary), "years": years}


def withdraw_bid(conn, league_id: str, team_id: str, player_id: str) -> None:
    with league_lock(conn, league_id):
        conn.execute(
            "DELETE FROM fa_bids WHERE league_id = %s AND player_id = %s AND team_id = %s",
            (league_id, player_id, team_id),
        )
        conn.commit()


def bids_by(conn, league_id: str, team_id: str, year: int) -> dict[str, dict]:
    rows = conn.execute(
        "SELECT player_id, salary, years FROM fa_bids WHERE league_id = %s AND team_id = %s AND year = %s",
        (league_id, team_id, year),
    ).fetchall()
    return {r["player_id"]: dict(r) for r in rows}


def bid_counts(conn, league_id: str, year: int) -> dict[str, int]:
    rows = conn.execute(
        """SELECT player_id, COUNT(*) AS n FROM fa_bids
           WHERE league_id = %s AND year = %s GROUP BY player_id""",
        (league_id, year),
    ).fetchall()
    return {r["player_id"]: r["n"] for r in rows}


def _ai_bids(conn, league_id: str, season_id: str, year: int, rng) -> int:
    """AI teams bid on free agents who fill a hole, within their budget:
    near his asking price, for the years he asks."""
    humans = GMRepository(conn).get_human_team_ids(league_id)
    teams = [t for t in _league_teams(conn, league_id) if t not in humans]
    rng.shuffle(teams)
    repo = PlayerRepository(conn)
    pool = []
    for row in repo.get_free_agents_with_skills(league_id):
        if waivers.on_waivers(conn, row["id"]):
            continue
        rec = repo.record_from_row(row)
        pool.append((rec, PlayerEvaluator.rate_player(rec.skills, rec.throws)))
    if not pool:
        return 0
    asks = {}
    made = 0
    money = owners.money_states(conn, league_id, year)
    scale = free_agents.price_scale(conn, league_id, year)
    minimum = ct.round_salary(ct.MIN_SALARY * scale, scale)
    for team_id in teams:
        team = ai_free_agents.role_values(
            ai_free_agents._rated_team(conn, league_id, team_id)
        )
        room = ai_free_agents._budget_room(conn, league_id, team_id, year)
        mstate = money.get(team_id)
        margin = money_state.hole_margin(mstate, ai_free_agents.HOLE_MARGIN)
        # A capped-out team makes one bid; one cutting costs only bids the
        # minimum (src/league/money_state.py).
        bids = 1 if mstate == "capped-out" else AI_BIDS
        picks = []
        for rec, r in pool:
            role, gain = ai_free_agents.best_fit(team, r, margin)
            if role:
                picks.append((gain, rec, role))
        picks.sort(key=lambda x: -x[0])
        roles_taken = set()
        for gain, rec, role in picks:
            if len(roles_taken) >= bids:
                break
            if role in roles_taken:
                continue
            if rec.id not in asks:
                asks[rec.id] = asking(conn, league_id, rec, year)
            ask = asks[rec.id]
            salary = ct.round_salary(ask.salary * rng.uniform(0.92, 1.12))
            if salary > room:
                continue
            if mstate == "cutting-costs" and ask.salary > minimum:
                continue
            salary = min(salary, minimum) if mstate == "cutting-costs" else salary
            conn.execute(
                """INSERT INTO fa_bids (league_id, player_id, team_id, year, salary, years)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (player_id, team_id, year) DO NOTHING""",
                (league_id, rec.id, team_id, year, salary, ask.years),
            )
            roles_taken.add(role)
            room -= salary
            made += 1
    return made


# ── 3. Settling ───────────────────────────────────────────────────────────────


def _fits(conn, league_id: str, season_id: str, year: int, team_ids) -> dict:
    """What each team offers besides money, for team_fit."""
    happy = HappinessRepository(conn, league_id)
    info = happy._teams(season_id)
    shares = waivers._records(conn, league_id, season_id)
    states = {
        t: r["state"]
        for t, r in TeamStateRepository(conn).latest(league_id, season_id).items()
    }
    coaching = BudgetRepository(conn).department(league_id, year, "coaching", team_ids)
    regions = {t["region"] for t in info.values() if t["region"]}
    out = {}
    for t in team_ids:
        share = shares.get(t)
        wins = round(share * 100) if share is not None else 0
        out[t] = {
            "info": info.get(t, {"region": None, "climate": None, "market": 3}),
            "record": (wins, 100 - wins if share is not None else 0),
            "state": states.get(t),
            "coaching": coaching.get(t),
            "regions": regions,
        }
    return out


def bid_value(
    salary: int, years: int, ask: ct.Deal, age: int, fit: float, share: float
) -> float:
    """How much a player likes a bid: the money against his asking price,
    plus the seasons of security past what he asked for, each by his age in
    it (src/player/negotiation.py: a 27-year-old values a 5-year deal for
    its age 30 and 31 seasons), plus the team's fit as much as he cares
    about it."""
    money = ng.money_value(salary, years, ask.salary, ask.years, age)
    return money + FIT_WEIGHT * share * fit


def team_fit_for(person, player, home: str | None, team: dict) -> tuple[float, float]:
    info = team["info"]
    wins, losses = team["record"]
    sats = {
        "winning": hp.winning(wins, losses, team["state"])[0],
        "location": hp.location(
            home,
            info["region"],
            info["climate"],
            team["regions"],
            person.climate,
        )[0]
        if info["region"]
        else 0.0,
        "fame": hp.fame(info["market"], False)[0],
    }
    return hp.team_fit(
        person, player.age, sats, hp.coaching_lift(team["coaching"], player.age)
    )


def _last_team(conn, league_id: str, player_id: str) -> str | None:
    """The team on a free agent's most recent deal in the league, if any."""
    row = conn.execute(
        """SELECT team_id FROM player_contracts
           WHERE player_id = %s AND league_id = %s AND team_id IS NOT NULL
           ORDER BY start_year DESC, id DESC LIMIT 1""",
        (player_id, league_id),
    ).fetchone()
    return row["team_id"] if row else None


def close_bidding(conn, league_id: str) -> list[dict]:
    """Bids settle (settle) and bidding closes for the year. AI teams that
    signed someone re-pick their rosters around him; a GM who did gets the
    Roster tab in their preseason next moves again. The caller holds the
    league lock and commits. Returns the signings."""
    league = LeagueRepository(conn).get_by_id(league_id)
    if not bidding_open_for(league):
        return []
    signed = settle(conn, league_id)
    conn.execute("UPDATE leagues SET fa_bidding = FALSE WHERE id = %s", (league_id,))
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    year = ContractRepository(conn).current_year(league_id)
    teams = {s["team_id"] for s in signed}
    if not teams or not season_id or year is None:
        return signed
    humans = GMRepository(conn).get_human_team_ids(league_id)
    ai = teams - humans
    outlooks = front_office.outlooks(conn, league_id, season_id) if ai else {}
    for team_id in sorted(ai):
        front_office.replan_roster(
            conn, league_id, season_id, team_id, outlooks.get(team_id), f"{year}-04-01"
        )
    conn.execute(
        """UPDATE gms SET roster_seen_season_id = NULL
           WHERE league_id = %s AND team_id = ANY(%s)""",
        (league_id, sorted(teams & humans)),
    )
    return signed


def settle(conn, league_id: str) -> list[dict]:
    """Bidding closes: AI teams bid, then each free agent with bids signs
    with the one he likes best. Returns the signings."""
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    year = ContractRepository(conn).current_year(league_id)
    if not season_id or year is None:
        return []
    rng = random.Random(f"fa-bids:{league_id}:{year}")
    _ai_bids(conn, league_id, season_id, year, rng)
    bids = conn.execute(
        "SELECT * FROM fa_bids WHERE league_id = %s AND year = %s",
        (league_id, year),
    ).fetchall()
    by_player: dict[str, list[dict]] = {}
    for b in bids:
        by_player.setdefault(b["player_id"], []).append(dict(b))
    if not by_player:
        return []
    repo = PlayerRepository(conn)
    players = {pid: repo.look_up(pid) for pid in by_player}
    homes = {
        r["id"]: r["home_region"]
        for r in conn.execute(
            "SELECT id, home_region FROM players WHERE id = ANY(%s)",
            (list(by_player),),
        ).fetchall()
    }
    pers = HappinessRepository(conn, league_id).personalities(list(by_player))
    teams = sorted({b["team_id"] for b in bids})
    fits = _fits(conn, league_id, season_id, year, teams)
    budgets = BudgetRepository(conn)
    contracts = ContractRepository(conn)
    status = PlayerStatusRepository(conn)
    team_repo = TeamRepository(conn)
    names = TeamRepository(conn).get_names(teams)
    nm = Names(conn, league_id)
    signed = []
    minors = {t: len(status.get_by_team_and_status(t, "minors")) for t in teams}
    order = sorted(
        (pid for pid in by_player if players.get(pid)),
        key=lambda pid: -role_rating(players[pid]),
    )
    for pid in order:
        p = players[pid]
        if status.get_status(pid) != "free_agent":
            continue
        person = pers.get(pid) or hp.personality_for(pid)
        ask = asking(conn, league_id, p, year)
        best = None
        for b in by_player[pid]:
            if b["salary"] < MIN_BID_SHARE * ask.salary:
                continue
            if budgets.refusal(league_id, b["team_id"], year, b["salary"]):
                continue
            if minors.get(b["team_id"], 0) >= MINORS_LIMIT:
                continue
            fit, share = team_fit_for(person, p, homes.get(pid), fits[b["team_id"]])
            value = bid_value(b["salary"], b["years"], ask, p.age, fit, share)
            value += random.Random(f"fa-tie:{pid}:{b['team_id']}").random() * 1e-6
            if best is None or value > best[0]:
                best = (value, b)
        if best is None:
            continue
        b = best[1]
        deal = ct.Deal(b["salary"], b["years"], "standard")
        was = _last_team(conn, league_id, pid)
        team_repo.add_player(b["team_id"], pid)
        status.set_status(pid, "minors")
        minors[b["team_id"]] = minors.get(b["team_id"], 0) + 1
        contracts.sign_free_agent(pid, league_id, b["team_id"], deal, year)
        contracts.apply_offset(pid, year, deal.salary, year + deal.years - 1)
        signed.append(
            {
                "player_id": pid,
                "team_id": b["team_id"],
                "salary": deal.salary,
                "years": deal.years,
                "bids": len(by_player[pid]),
            }
        )
        if was == b["team_id"]:
            former = f" He's back with the {nm.team(was)}."
        elif was:
            former = f" He leaves the {nm.team(was)}."
        else:
            former = ""
        NewsRepository(conn).add(
            league_id,
            season_id,
            date(year, 3, 31).isoformat(),
            "free_agency",
            f"fa-sign:{year}:{pid}",
            f"{p.first_name} {p.last_name} signs with {names.get(b['team_id'], 'a new team')}",
            f"{ct.format_salary(deal.salary)} a season for {deal.years} "
            f"season{'s' if deal.years != 1 else ''}"
            + (
                f", picked from {len(by_player[pid])} offers."
                if len(by_player[pid]) > 1
                else "."
            )
            + former,
            weight=2 if role_rating(p) >= 60 else 1,
            team_ids=[b["team_id"]] + ([was] if was and was != b["team_id"] else []),
            player_ids=[pid],
        )
    conn.execute(
        "DELETE FROM fa_bids WHERE league_id = %s AND year <= %s", (league_id, year)
    )
    return signed
