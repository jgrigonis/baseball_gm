# src/api/services/team_states.py
#
# Team states (src/league/team_state.py) for a league: gathering the inputs,
# storing a checkpoint, and reading each team's current state.
#
# Checkpoints: the first time a season's states are needed, every
# CHECKPOINT_DAYS league days in season (from the sim, after a day's games),
# on trade deadline day, and once at the start of the offseason. Each stores a
# row per team in team_states. Before STANDINGS_MIN_GAMES are played, a
# team's first state of the season carries.

from __future__ import annotations

from datetime import date

from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.standings_repo import StandingsRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_state_repo import TeamStateRepository
from src.league import team_state, trade_deadline
from src.league.team_state import Inputs, Previous
from src.league.trades.ai_evaluator import Asset, age_shift, strengths, value

CHECKPOINT_DAYS = 7
# The games-back race is to the last of PLAYOFF_SPOTS.
PLAYOFF_SPOTS = 8
# The players a core is made of, and the age a farm player can be.
CORE_SIZE = 15
FARM_MAX_AGE = 25


def refresh_if_due(conn, league_id: str, game_date: str) -> None:
    """After a day's games: store a checkpoint if one is due."""
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    if not season_id:
        return
    last = TeamStateRepository(conn).last_checkpoint(league_id, season_id)
    deadline = trade_deadline.deadline_date(conn, season_id)
    if (
        last is None
        or _days(last, game_date) >= CHECKPOINT_DAYS
        or (game_date == deadline and last != game_date)
    ):
        refresh(conn, league_id, season_id, game_date)


def current(conn, league_id: str, season_id: str, today: str) -> dict[str, dict]:
    """Each team's latest team_states row ({state, inputs, ...}) by team id,
    storing a checkpoint first if the season has none yet, if a team is
    missing, or if the offseason has begun since the last one."""
    repo = TeamStateRepository(conn)
    rows = repo.latest(league_id, season_id)
    teams = _team_ids(conn, league_id, season_id)
    offseason = _offseason(conn, league_id)
    stale = offseason and any(
        r["inputs"].get("games_back") is not None for r in rows.values()
    )
    if not rows or stale or any(t not in rows for t in teams):
        refresh(conn, league_id, season_id, today)
        rows = repo.latest(league_id, season_id)
    return rows


def states(conn, league_id: str, season_id: str, today: str) -> dict[str, str]:
    """Each team's current state, by team id."""
    return {
        t: r["state"] for t, r in current(conn, league_id, season_id, today).items()
    }


def state_of(conn, league_id: str, season_id: str, team_id: str, today: str) -> str:
    return states(conn, league_id, season_id, today).get(team_id, "retooling")


def in_race(row: dict) -> bool:
    """Whether the standings have had their say: enough games played, in
    season."""
    i = row["inputs"]
    return (
        i.get("games_back") is not None
        and i.get("played", 0) >= team_state.STANDINGS_MIN_GAMES
    )


def refresh(conn, league_id: str, season_id: str, today: str) -> dict[str, str]:
    """Store a checkpoint: every team's state as of today."""
    repo = TeamStateRepository(conn)
    previous = repo.latest(league_id, season_id)
    offseason = _offseason(conn, league_id)
    out = {}
    for team_id, i in gather(conn, league_id, season_id, offseason).items():
        row = previous.get(team_id)
        # The first offseason checkpoint starts fresh: last season's race is
        # over.
        fresh = offseason and row and row["inputs"].get("games_back") is not None
        if row and not fresh and i.games_back is not None and not i.standings_count:
            out[team_id] = row["state"]  # too early in the season to change
            continue
        prev = (
            Previous(row["state"], row["held"], row["candidate"], row["inputs"]["tier"])
            if row and not fresh
            else None
        )
        state, held = team_state.settle(prev, i)
        repo.add(
            league_id,
            season_id,
            team_id,
            today,
            state,
            held,
            team_state.classify(i),
            i.as_dict() | {"tier": i.tier_now},
        )
        out[team_id] = state
    return out


def gather(
    conn, league_id: str, season_id: str, offseason: bool = False
) -> dict[str, Inputs]:
    """Every team's inputs: strength now and in a couple of years, the age of
    its core, its farm, and (in season) the standings."""
    team_ids = _team_ids(conn, league_id, season_id)
    if not team_ids:
        return {}
    player_repo = PlayerRepository(conn)
    statuses = _statuses(conn, team_ids)
    now, future, farm, core = {}, {}, {}, {}
    for t in team_ids:
        assets = [Asset.from_record(p) for p in player_repo.get_players_by_team(t)]
        now[t], future[t] = strengths(assets, days_left=1)
        farm[t] = sum(
            value(a.rating + age_shift(a.age))
            for a in assets
            if statuses.get(a.id) != "26man" and a.age <= FARM_MAX_AGE
        )
        core[t] = _core(assets)

    standings = {} if offseason else _games_back(conn, league_id, season_id)
    n = len(team_ids)
    rank_now, rank_future, rank_farm = (
        _ranks(now, n),
        _ranks(future, n),
        _ranks(farm, n),
    )
    league_age = round(sum(age for age, _ in core.values()) / n, 1)
    out = {}
    for t in team_ids:
        played, gb = standings.get(t, (0, None))
        age, old_share = core[t]
        out[t] = Inputs(
            teams=n,
            rank_now=rank_now[t],
            rank_future=rank_future[t],
            core_age=age,
            league_core_age=league_age,
            old_share=old_share,
            farm_rank=rank_farm[t],
            played=played,
            games_back=gb,
        )
    return out


def _core(assets: list[Asset]) -> tuple[float, float]:
    """Average age of the CORE_SIZE most valuable players, and the share of
    their value from players past OLD_AGE."""
    valued = sorted(
        ((value(a.rating), a) for a in assets),
        key=lambda x: x[0],
        reverse=True,
    )[:CORE_SIZE]
    if not valued:
        return 0.0, 0.0
    age = sum(a.age for _, a in valued) / len(valued)
    total = sum(v for v, _ in valued)
    old = sum(v for v, a in valued if a.age >= team_state.OLD_AGE)
    return round(age, 1), round(old / total, 3) if total else 0.0


def _ranks(scores: dict[str, float], n: int) -> dict[str, float]:
    """0 for the best, 1 for the worst."""
    ordered = sorted(scores, key=lambda t: (-scores[t], t))
    return {t: (i / (n - 1) if n > 1 else 0.5) for i, t in enumerate(ordered)}


def _games_back(conn, league_id: str, season_id: str) -> dict[str, tuple[int, float]]:
    """(games played, games back from the last playoff spot) by team. A team
    in a playoff spot is 0 back."""
    rows = StandingsRepository(conn).get_records(league_id, season_id)
    if not rows:
        return {}
    ranked = sorted(rows, key=lambda r: (r["losses"] - r["wins"], r["team_id"]))
    last = ranked[min(PLAYOFF_SPOTS, len(ranked)) - 1]
    out = {}
    for i, r in enumerate(ranked):
        gb = ((last["wins"] - r["wins"]) + (r["losses"] - last["losses"])) / 2
        out[r["team_id"]] = (r["wins"] + r["losses"], 0.0 if i < PLAYOFF_SPOTS else gb)
    return out


def _team_ids(conn, league_id: str, season_id: str) -> list[str]:
    return [
        t["id"]
        for t in TeamRepository(conn).get_teams_in_league_season(league_id, season_id)
    ]


def _statuses(conn, team_ids) -> dict[str, str]:
    rows = conn.execute(
        """SELECT tp.player_id, s.status FROM team_players tp
           JOIN player_status s ON s.player_id = tp.player_id
           WHERE tp.team_id = ANY(%s)""",
        (list(team_ids),),
    ).fetchall()
    return {r["player_id"]: r["status"] for r in rows}


def _offseason(conn, league_id: str) -> bool:
    league = LeagueRepository(conn).get_by_id(league_id)
    return bool(league and league["state"] in trade_deadline.OFFSEASON_STATES)


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days
