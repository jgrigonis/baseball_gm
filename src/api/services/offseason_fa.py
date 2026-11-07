# src/api/services/offseason_fa.py
"""
Offseason free agency (free agency phase 2, PR 3; Josh's decisions
2026-11-05).

1. The re-sign window (league state 'offseason'). Players whose deals end
   with this season either re-sign with their team or go to market:
   - Veterans (MARKET_SEASONS seasons or more under contract in the league)
     and unhappy players (mood "unhappy" or worse) go to market unless their
     team re-signs them now, at their price.
   - Everyone else is tendered (re-signed) by default unless their GM lets
     them go, as long as the owner's hard limit has room for the raise
     (Josh, 2026-11-07: re-signs answer to the owner).
   A GM makes the call on the Free Agents tab (contract_choices). AI teams
   re-sign the best first while their owner's budget has room (market-bound
   players only from the 40-man) and let fringe players go rather than pay
   them more than the minimum (_keeps). The window closes when the
   offseason runs (close_window): re-signed players get their new deal, and
   the ones let go become free agents.

2. Bidding (league state 'draft'). Free agents can't be signed outright:
   teams bid a salary and a number of seasons (fa_bids). AI teams bid on
   free agents who fill a hole, within their budget.

3. Settling (as the preseason starts, settle). Each free agent with bids,
   best first, takes the one he likes best: the money against his asking
   price, plus how well the team suits him (winning, home, market, coaching:
   src/player/happiness.py team_fit), as much as he cares about those. He
   won't take less than MIN_BID_SHARE of his asking price. A bid the
   owner's hard limit no longer allows is skipped. Free agents nobody gets
   can still be signed at their asking price in the preseason and season.
"""

from __future__ import annotations

import random
from datetime import date

from src.api.services import ai_free_agents, free_agents, waivers
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
from src.player import contracts as ct
from src.player import happiness as hp
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
    happy.prepare_resign(ids)
    moods = happy.latest_moods(ids)
    scale = BudgetRepository(conn).salary_scale(league_id, year + 1)
    arb = contracts.arbitration_seasons(ids, year + 1)
    repo = PlayerRepository(conn)
    out = []
    for r in rows:
        p = repo.look_up(r["player_id"])
        if p is None:
            continue
        deal, wants_out = contracts.renewal(p, year + 1, happy, scale, arb.get(p.id))
        mood = moods.get(p.id)
        if seasons.get(p.id, 0) >= MARKET_SEASONS:
            market = "veteran"
        elif mood is not None and mood < hp.UNHAPPY:
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
                "choice": r["choice"],
                "scale": scale,
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
                refusal = BudgetRepository(conn).refusal(
                    league_id, team_id, year, row["deal"].salary - row["old_salary"]
                )
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
    """What a team can add before its owner balks: up to the hard limit for
    a person, the budget for an AI GM. Unlimited without budgets."""
    if not human:
        return ai_free_agents._budget_room(conn, league_id, team_id, year)
    s = BudgetRepository(conn).standing(league_id, team_id, year)
    if s is None:
        return float("inf")
    return s["limit"] - s["spend"]


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

    A raise is the new salary less the old one, which comes off."""
    keep: set[str] = set()
    room: dict[str, float] = {}

    def fits(r: dict, force: bool = False) -> bool:
        t = r["team_id"]
        if t not in room:
            room[t] = _room(conn, league_id, t, year, t in humans)
        cost = r["deal"].salary - r["old_salary"]
        if cost > room[t] and not force:
            return False
        room[t] -= max(0, cost)
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
        if free_agents.is_fringe(r["player"]) and r["deal"].salary > minimum:
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
    resigned, gone, unhappy_out = 0, [], []
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
        + ". Teams bid during the draft; players choose as the preseason starts.",
        weight=2,
        player_ids=[p.id for p in players[:4]],
    )


def expiring_view(conn, league_id: str, team_id: str) -> list[dict]:
    """A GM's expiring deals for the Free Agents tab."""
    year = _year(conn, league_id)
    out = []
    for r in expiring(conn, league_id, year, [team_id]):
        d = r["deal"]
        if r["choice"] == "resign":
            fate = "resign"
        elif r["choice"] == "let_go" or r["market"]:
            fate = "go"
        else:
            fate = "auto"
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
                "choice": r["choice"],
                "fate": fate,
                "wants_out": r["wants_out"],
            }
        )
    return out


# ── 2. Bidding ────────────────────────────────────────────────────────────────


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
        player, year, free_agents.price_scale(conn, league_id, year)
    )


def bid_preview(conn, league_id: str, team_id: str, player_id: str) -> dict:
    """His asking deal, the team's bid so far, and how many bids he has."""
    if _league(conn, league_id)["state"] != "draft":
        raise OffseasonFAError("Bidding is open during the draft.")
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
        if _league(conn, league_id)["state"] != "draft":
            raise OffseasonFAError("Bidding is open during the draft.")
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
    for team_id in teams:
        team = ai_free_agents.role_values(
            ai_free_agents._rated_team(conn, league_id, team_id)
        )
        room = ai_free_agents._budget_room(conn, league_id, team_id, year)
        picks = []
        for rec, r in pool:
            role, gain = ai_free_agents.best_fit(team, r)
            if role:
                picks.append((gain, rec, role))
        picks.sort(key=lambda x: -x[0])
        roles_taken = set()
        for gain, rec, role in picks:
            if len(roles_taken) >= AI_BIDS:
                break
            if role in roles_taken:
                continue
            if rec.id not in asks:
                asks[rec.id] = asking(conn, league_id, rec, year)
            ask = asks[rec.id]
            salary = ct.round_salary(ask.salary * rng.uniform(0.92, 1.12))
            if salary > room:
                continue
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
    """How much a player likes a bid: the money against his asking price
    (an older player values the extra years), plus the team's fit as much as
    he cares about it."""
    per_year = 0.04 if age >= 30 else 0.01
    money = salary / ask.salary + per_year * (years - ask.years)
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


def settle(conn, league_id: str) -> list[dict]:
    """The preseason starts: AI teams bid, then each free agent with bids
    signs with the one he likes best. Returns the signings."""
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
    signed = []
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
            fit, share = team_fit_for(person, p, homes.get(pid), fits[b["team_id"]])
            value = bid_value(b["salary"], b["years"], ask, p.age, fit, share)
            value += random.Random(f"fa-tie:{pid}:{b['team_id']}").random() * 1e-6
            if best is None or value > best[0]:
                best = (value, b)
        if best is None:
            continue
        b = best[1]
        deal = ct.Deal(b["salary"], b["years"], "standard")
        team_repo.add_player(b["team_id"], pid)
        status.set_status(pid, "minors")
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
            ),
            weight=2 if role_rating(p) >= 60 else 1,
            team_ids=[b["team_id"]],
            player_ids=[pid],
        )
    conn.execute(
        "DELETE FROM fa_bids WHERE league_id = %s AND year <= %s", (league_id, year)
    )
    return signed
