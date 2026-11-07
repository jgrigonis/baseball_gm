# src/api/services/ai_free_agents.py
"""
AI teams and free agency (free agency phase 2, PR 2; Josh 2026-11-05: AI
GMs fill holes only, inside their owner's budget).

A hole is a role where a free agent would be clearly better than the best
the team has healthy: its 5th starter, its 8th reliever, or its starter at a
lineup position, by HOLE_MARGIN rating points or more. Then:

- Waivers: an AI team claims a player on waivers who fills a hole, if his
  deal fits its owner's budget. It looks every game day, since waivers only
  last a few days.
- Free agents: every SIGN_EVERY_DAYS game days, an AI team signs the free
  agent who fills its biggest hole at his asking price, if it fits the
  budget. One signing a team per look.
- Room: with the minors full, it releases its weakest minors player who
  never made the 40-man (free to release) to make room.

The new man then plays where he fits: the team re-picks its 26-man and
40-man (front_office.replan_roster). People's teams are never touched.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from src.api.services import free_agents, front_office, waivers
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.waiver_repo import WaiverRepository
from src.league.offseason.roster_trimmer import MINORS_LIMIT
from src.player import contracts as ct
from src.player.player_evaluator import PlayerEvaluator
from src.team.roster_assigner import BULLPEN, LINEUP_POSITIONS, STARTERS

# How much better (rating points) a free agent must be to fill a hole.
HOLE_MARGIN = 5
# A bargain (asking at most BARGAIN_SHARE of his full price, or the
# minimum) is worth signing when he's this much better.
BARGAIN_MARGIN = 2
BARGAIN_SHARE = 0.6
# AI teams shop for free agents every this many game days.
SIGN_EVERY_DAYS = 7
# Injured this long or more, he doesn't count when looking for holes.
LONG_INJURY_DAYS = 15


def _position_score(r: dict, pos: str) -> float:
    """As RosterAssigner picks a lineup: 35% defense, 65% offense."""
    return r.get(pos, 0) * 0.35 + r.get("overall_offense", 0) * 0.65


def role_values(rated: dict[str, dict]) -> dict[str, float]:
    """What a team has at each role: its 5th starter, its 8th reliever
    (from those not starting), and its best at each lineup position."""
    out = {}
    by_sp = sorted(rated, key=lambda pid: -rated[pid].get("sp", 0))
    starters = by_sp[:STARTERS]
    out["sp"] = rated[starters[-1]].get("sp", 0) if len(starters) == STARTERS else 0
    pen = sorted(
        (rated[pid].get("rp", 0) for pid in rated if pid not in starters),
        reverse=True,
    )
    out["rp"] = pen[BULLPEN - 1] if len(pen) >= BULLPEN else 0
    for pos in LINEUP_POSITIONS:
        out[pos] = max((_position_score(r, pos) for r in rated.values()), default=0)
    return out


def candidate_value(r: dict, role: str) -> float:
    if role in ("sp", "rp"):
        return r.get(role, 0)
    return _position_score(r, role)


def best_fit(
    team: dict[str, float], r: dict, margin: float = HOLE_MARGIN
) -> tuple[str | None, float]:
    """The role a player would fill best, and by how much he beats what the
    team has there (only holes: at least margin)."""
    best, gain = None, 0.0
    for role, have in team.items():
        g = candidate_value(r, role) - have
        if g >= margin and g > gain:
            best, gain = role, g
    return best, gain


# ── A team's situation ────────────────────────────────────────────────────────


def _rated_team(conn, league_id: str, team_id: str) -> dict[str, dict]:
    """Ratings of the team's healthy players."""
    hurt = {
        pid
        for pid, days in InjuryRepository(conn, league_id)
        .get_team_injuries(team_id)
        .items()
        if days is not None and days >= LONG_INJURY_DAYS
    }
    return {
        p.id: PlayerEvaluator.rate_player(p.skills, p.throws)
        for p in PlayerRepository(conn).get_players_by_team(team_id)
        if p.id not in hurt
    }


def _budget_room(conn, league_id: str, team_id: str, year: int) -> float:
    """What the owner's budget has left for payroll. Unlimited without
    budgets (Speed Blitz)."""
    s = BudgetRepository(conn).standing(league_id, team_id, year)
    if s is None:
        return float("inf")
    return s["budget"] - s["spend"]


def _make_room(conn, league_id: str, team_id: str) -> bool:
    """Minors full: let the weakest never-guaranteed minors player go (it
    costs nothing). Returns whether there's room now."""
    minors = set(PlayerStatusRepository(conn).get_by_team_and_status(team_id, "minors"))
    if len(minors) < MINORS_LIMIT:
        return True
    players = [
        p for p in PlayerRepository(conn).get_players_by_team(team_id) if p.id in minors
    ]
    if not players:
        return False
    rows = conn.execute(
        """SELECT DISTINCT player_id FROM player_contracts
           WHERE player_id = ANY(%s) AND guaranteed AND released_year IS NULL""",
        ([p.id for p in players],),
    ).fetchall()
    guaranteed = {r["player_id"] for r in rows}
    cuts = [p for p in players if p.id not in guaranteed]
    if not cuts:
        return False
    worst = min(
        cuts,
        key=lambda p: max(
            PlayerEvaluator.rate_player(p.skills, p.throws).get(k, 0)
            for k in ("sp", "rp", "overall_player")
        ),
    )
    try:
        free_agents.release(conn, league_id, team_id, worst.id)
    except free_agents.FreeAgentError:
        return False
    return True


# ── Waivers: every game day ───────────────────────────────────────────────────


def claim_waivers(conn, league_id: str, ai_teams: list[str], year: int) -> int:
    """AI teams claim players on waivers who fill a hole and fit the budget.
    Returns how many claims they made."""
    open_ = WaiverRepository(conn).open_for(league_id)
    if not open_ or not ai_teams:
        return 0
    players = {
        p.id: p
        for p in (PlayerRepository(conn).look_up(w["player_id"]) for w in open_)
        if p
    }
    made = 0
    for team_id in ai_teams:
        team = None
        for w in open_:
            pid = w["player_id"]
            if w["from_team_id"] == team_id or pid not in players:
                continue
            if pid in WaiverRepository(conn).claims_by(league_id, team_id):
                continue
            if team is None:
                team = role_values(_rated_team(conn, league_id, team_id))
            p = players[pid]
            role, _ = best_fit(team, PlayerEvaluator.rate_player(p.skills, p.throws))
            if not role:
                continue
            deal = ContractRepository(conn).released_deal(pid, w["from_team_id"])
            salary = waivers.deal_view(deal, year).get("salary") or 0
            if salary > _budget_room(conn, league_id, team_id, year):
                continue
            try:
                waivers.claim(conn, league_id, team_id, pid, year)
            except waivers.WaiverError:
                continue
            made += 1
    return made


# ── Free agents: every week or so ─────────────────────────────────────────────


def sign_free_agents(
    conn, league_id: str, season_id: str, ai_teams: list[str], year: int, today: str
) -> list[tuple[str, str]]:
    """Each AI team signs at most one free agent who fills a hole, or who
    beats what it has by a little when he's a bargain. Returns
    [(team_id, player_id)]."""
    on_waivers = {w["player_id"] for w in WaiverRepository(conn).open_for(league_id)}
    repo = PlayerRepository(conn)
    pool = []
    for row in repo.get_free_agents_with_skills(league_id):
        if row["id"] in on_waivers:
            continue
        rec = repo.record_from_row(row)
        pool.append((rec, PlayerEvaluator.rate_player(rec.skills, rec.throws)))
    if not pool:
        return []
    scale = free_agents.price_scale(conn, league_id, year)
    discount = free_agents.market_discount(conn, league_id)
    minimum = ct.round_salary(ct.MIN_SALARY * scale, scale)
    asks, bargain = {}, {}
    signed = []
    outlooks = front_office.outlooks(conn, league_id, season_id, today)
    effective = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
    taken: set[str] = set()
    for team_id in ai_teams:
        team = role_values(_rated_team(conn, league_id, team_id))
        room = _budget_room(conn, league_id, team_id, year)
        best = None
        for rec, r in pool:
            if rec.id in taken:
                continue
            if rec.id not in asks:
                ask = free_agents.asking_deal(rec, year, scale, discount)
                full = free_agents.asking_deal(rec, year, scale)
                asks[rec.id] = ask
                bargain[rec.id] = (
                    ask.salary <= minimum or ask.salary <= BARGAIN_SHARE * full.salary
                )
            margin = BARGAIN_MARGIN if bargain[rec.id] else HOLE_MARGIN
            role, gain = best_fit(team, r, margin)
            if not role or (best and gain <= best[1]):
                continue
            if asks[rec.id].salary > room:
                continue
            best = (rec, gain)
        if not best:
            continue
        rec = best[0]
        if not _make_room(conn, league_id, team_id):
            continue
        try:
            free_agents.sign(conn, league_id, team_id, rec.id)
        except free_agents.FreeAgentError:
            continue
        taken.add(rec.id)
        signed.append((team_id, rec.id))
        front_office.replan_roster(
            conn, league_id, season_id, team_id, outlooks.get(team_id), effective
        )
    return signed


# ── The sim's hook ────────────────────────────────────────────────────────────


def _ai_teams(conn, league_id: str, season_id: str, rng: random.Random) -> list[str]:
    humans = GMRepository(conn).get_human_team_ids(league_id)
    teams = [
        t["id"]
        for t in TeamRepository(conn).get_teams_in_league_season(league_id, season_id)
        if t["id"] not in humans
    ]
    rng.shuffle(teams)
    return teams


def after_day(conn, league_id: str, game_date: str) -> dict:
    """After a day's games, before waivers clear: AI teams claim off
    waivers, and every SIGN_EVERY_DAYS days sign free agents."""
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    year = ContractRepository(conn).current_year(league_id)
    if not season_id or year is None:
        return {"claims": 0, "signed": 0}
    rng = random.Random(f"ai-fa:{league_id}:{game_date}")
    teams = _ai_teams(conn, league_id, season_id, rng)
    claims = claim_waivers(conn, league_id, teams, year)
    signed = []
    if date.fromisoformat(game_date).toordinal() % SIGN_EVERY_DAYS == 0:
        signed = sign_free_agents(conn, league_id, season_id, teams, year, game_date)
    return {"claims": claims, "signed": len(signed)}
