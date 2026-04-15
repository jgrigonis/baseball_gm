# src/api/services/sim_playoff.py
"""
Simulate playoff games in four modes:
  game   — one game in the current undecided series
  series — play out the current undecided series to completion
  round  — play all series in the current round to completion
  all    — play all remaining playoff games
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from src.db.repositories.games_repo import GameRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.league.offseason.build_season_stats import build_season
from src.league.playoffs.play_playoffs import (
    _HOME_MAP_BO7,
    _SEMI_27_36_OFFSETS,
    _SEMI_18_45_OFFSETS,
    _FINAL_OFFSETS,
    generate_round_games,
    get_seeds,
    get_series_id,
    get_series_games,
    get_series_winner,
    original_seed,
    series_is_decided,
)
from src.league.play_season import play_game

# ---------------------------------------------------------------------------
# Round definitions — fixed bracket structure
# ---------------------------------------------------------------------------

ROUND_DEFS = [
    {"name": "Round 1", "series_names": ["1v8", "2v7", "3v6", "4v5"], "best_of": 5},
    {
        "name": "Semifinals",
        "series_names": ["[1,8]v[4,5]", "[2,7]v[3,6]"],
        "best_of": 7,
    },
    {"name": "Finals", "series_names": ["Finals"], "best_of": 7},
]

SERIES_BEST_OF = {
    "1v8": 5,
    "2v7": 5,
    "3v6": 5,
    "4v5": 5,
    "[1,8]v[4,5]": 7,
    "[2,7]v[3,6]": 7,
    "Finals": 7,
}


@dataclass
class SimConfig:
    logs: bool = False
    force: bool = False
    seed: int | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_season_id(conn, league_id: str) -> str | None:
    row = conn.execute(
        "SELECT season_id FROM league_seasons ls JOIN seasons s ON s.id = ls.season_id WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1",
        (league_id,),
    ).fetchone()
    return row["season_id"] if row else None


def _get_playoff_start(conn, season_id: str) -> date:
    row = conn.execute(
        """SELECT g.game_date FROM games g
           JOIN series s ON g.series_id = s.id
           WHERE s.season_id = %s AND s.name IN ('1v8','2v7','3v6','4v5')
           ORDER BY g.game_date LIMIT 1""",
        (season_id,),
    ).fetchone()
    return date.fromisoformat(row["game_date"]) if row else date.today()


def _ensure_round_games(
    conn, season_id: str, round_idx: int, seeds: list[dict]
) -> None:
    """Generate games for semis or finals once prior round is decided."""
    playoff_start = _get_playoff_start(conn, season_id)

    if round_idx == 1:  # Semifinals
        r1_winners = {}
        for name in ["1v8", "2v7", "3v6", "4v5"]:
            sid = get_series_id(conn, season_id, name)
            r1_winners[name] = get_series_winner(conn, sid, 5)

        for name, team_a, team_b in [
            ("[1,8]v[4,5]", r1_winners["1v8"], r1_winners["4v5"]),
            ("[2,7]v[3,6]", r1_winners["2v7"], r1_winners["3v6"]),
        ]:
            if not team_a or not team_b:
                continue
            sid = get_series_id(conn, season_id, name)
            if not sid:
                continue
            existing = conn.execute(
                "SELECT COUNT(*) FROM games WHERE series_id = %s", (sid,)
            ).fetchone()["count"]
            if existing > 0:
                continue
            seed_a = original_seed(seeds, team_a)
            seed_b = original_seed(seeds, team_b)
            high = team_a if seed_a < seed_b else team_b
            low = team_b if seed_a < seed_b else team_a
            # Each semi series gets its own offset schedule
            semi_offsets = (
                _SEMI_18_45_OFFSETS if name == "[1,8]v[4,5]" else _SEMI_27_36_OFFSETS
            )
            generate_round_games(
                conn,
                season_id,
                sid,
                high,
                low,
                _HOME_MAP_BO7,
                playoff_start,
                semi_offsets,
            )

    elif round_idx == 2:  # Finals
        semi_winners = []
        for name in ["[1,8]v[4,5]", "[2,7]v[3,6]"]:
            sid = get_series_id(conn, season_id, name)
            w = get_series_winner(conn, sid, 7)
            if w:
                semi_winners.append((w, original_seed(seeds, w)))

        if len(semi_winners) == 2:
            sid = get_series_id(conn, season_id, "Finals")
            if not sid:
                return
            existing = conn.execute(
                "SELECT COUNT(*) FROM games WHERE series_id = %s", (sid,)
            ).fetchone()["count"]
            if existing > 0:
                return
            a, sa = semi_winners[0]
            b, sb = semi_winners[1]
            high = a if sa < sb else b
            low = b if sa < sb else a
            generate_round_games(
                conn,
                season_id,
                sid,
                high,
                low,
                _HOME_MAP_BO7,
                playoff_start,
                _FINAL_OFFSETS,
            )


def _play_one_game(
    conn,
    season_id: str,
    league_id: str,
    league_mode: str,
    series_id: str,
    rng: random.Random,
) -> object | None:
    """Play the next unplayed game in a series. Returns result or None."""
    game_repo = GameRepository(conn)
    team_repo = TeamRepository(conn)
    team_game_repo = TeamGameRepository(conn)
    rotations_repo = TeamRotationsRepository(conn)
    args = SimConfig()

    for g in get_series_games(conn, series_id):
        if not g["completed"]:
            return play_game(
                conn=conn,
                args=args,
                team_repo=team_repo,
                game_repo=game_repo,
                team_game_repo=team_game_repo,
                rotations_repo=rotations_repo,
                season_id=season_id,
                game_info={
                    "game_id": g["id"],
                    "home_team_id": g["home_team_id"],
                    "away_team_id": g["away_team_id"],
                    "completed": g["completed"],
                },
                rng=rng,
                league_id=league_id,
                league_mode=league_mode,
            )
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def sim_playoff(
    league_id: str,
    conn,
    mode: str = "game",
) -> dict:
    """
    Simulate playoff games.
    mode: "game" (1 day) | "round" (1 round) | "all" (entire playoffs)
    Returns summary dict.
    """
    league = conn.execute(
        "SELECT * FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if not league:
        raise ValueError(f"League {league_id} not found")
    if league["state"] != "playoffs":
        raise ValueError(f"League is in state '{league['state']}' — not in playoffs")

    season_id = _get_season_id(conn, league_id)
    league_mode = dict(league).get("mode", "blitz") or "blitz"
    seeds = get_seeds(conn, season_id)
    rng = random.Random()

    games_played = 0
    results = []
    current_round = None
    champion = None

    # Track injuries for the GM's team so we can report new injuries / returns
    gm_row = conn.execute(
        "SELECT team_id FROM gms WHERE league_id = %s AND is_ai = 0 AND team_id IS NOT NULL LIMIT 1",
        (league_id,),
    ).fetchone()
    gm_team_id = gm_row["team_id"] if gm_row else None

    def _get_injured(team_id):
        if not team_id:
            return {}
        rows = conn.execute(
            """SELECT pi.player_id, pi.games_remaining,
                      p.first_name || ' ' || p.last_name as name
               FROM player_injuries pi
               JOIN players p ON p.id = pi.player_id
               JOIN team_players tp ON tp.player_id = pi.player_id AND tp.team_id = %s
               WHERE pi.games_remaining > 0 AND (pi.league_id = %s OR pi.league_id = '')""",
            (team_id, league_id),
        ).fetchall()
        return {
            r["player_id"]: {"name": r["name"], "days": r["games_remaining"]}
            for r in rows
        }

    injured_before = _get_injured(gm_team_id)

    def _get_next_day_games() -> list[dict]:
        """Return all unplayed games on the earliest unplayed game_date,
        ignoring games in series that are already decided."""
        # Build set of decided series IDs so we can exclude their unplayed games
        decided_sids = set()
        for rd in ROUND_DEFS:
            for sn in rd["series_names"]:
                sid = get_series_id(conn, season_id, sn)
                if sid and series_is_decided(conn, sid, rd["best_of"]):
                    decided_sids.add(sid)

        row = conn.execute(
            """SELECT MIN(g.game_date) as next_date
               FROM games g
               JOIN series s ON g.series_id = s.id
               WHERE s.season_id = %s AND g.completed = 0""",
            (season_id,),
        ).fetchone()
        if not row or not row["next_date"]:
            return []
        next_date = row["next_date"]

        rows = conn.execute(
            """SELECT g.id, g.game_date, g.home_team_id, g.away_team_id,
                      g.completed, s.name as series_name, g.series_id
               FROM games g
               JOIN series s ON g.series_id = s.id
               WHERE s.season_id = %s AND g.game_date = %s AND g.completed = 0
               ORDER BY s.name""",
            (season_id, next_date),
        ).fetchall()

        # Filter out games in decided series, then if nothing left advance to next date
        active = [dict(r) for r in rows if r["series_id"] not in decided_sids]
        if active:
            return active

        # All games on next_date belong to decided series — skip ahead
        # This handles leftover pre-generated games (e.g. game 4&5 when series swept)
        rows2 = conn.execute(
            """SELECT g.id, g.game_date, g.home_team_id, g.away_team_id,
                      g.completed, s.name as series_name, g.series_id
               FROM games g
               JOIN series s ON g.series_id = s.id
               WHERE s.season_id = %s AND g.completed = 0 AND g.game_date::date > %s
               ORDER BY g.game_date, s.name""",
            (season_id, next_date),
        ).fetchall()
        if not rows2:
            return []
        # Find first date with at least one undecided series game
        from itertools import groupby

        for date_key, group in groupby(rows2, key=lambda r: r["game_date"]):
            day = [dict(r) for r in group if r["series_id"] not in decided_sids]
            if day:
                return day
        return []

    def _ensure_later_rounds():
        """Generate semi/finals games if their prior round is decided."""
        for round_idx in range(1, len(ROUND_DEFS)):
            _ensure_round_games(conn, season_id, round_idx, seeds)

    def _current_round_name() -> str:
        """Return the name of the round currently being played."""
        for rd in ROUND_DEFS:
            for sn in rd["series_names"]:
                sid = get_series_id(conn, season_id, sn)
                if sid and not series_is_decided(conn, sid, rd["best_of"]):
                    return rd["name"]
        return ROUND_DEFS[-1]["name"]

    def _play_day() -> int:
        """Play all games on the next unplayed day. Returns games played."""
        _ensure_later_rounds()
        day_games = _get_next_day_games()
        count = 0
        for g in day_games:
            best_of = SERIES_BEST_OF.get(g["series_name"], 7)
            # Skip if series already decided (early exit)
            if series_is_decided(conn, g["series_id"], best_of):
                continue
            r = _play_one_game(
                conn, season_id, league_id, league_mode, g["series_id"], rng
            )
            if r:
                results.append({"series": g["series_name"], "result": str(r)})
                count += 1
        # Rollup game stats into player_season_stats after each day
        if results:
            try:
                build_season(conn, season_id)
            except Exception as _bs_err:
                try:
                    conn.rollback()
                except Exception:
                    pass
                print(f"build_season non-fatal error (will retry next day): {_bs_err}")
        return count

    if mode == "game":
        # "Sim 1 Day" — play all games scheduled for the next playoff day
        games_played += _play_day()

    elif mode == "round":
        # Play until all series in the current round are decided
        current_round_def = None
        for rd in ROUND_DEFS:
            for sn in rd["series_names"]:
                sid = get_series_id(conn, season_id, sn)
                if sid and not series_is_decided(conn, sid, rd["best_of"]):
                    current_round_def = rd
                    break
            if current_round_def:
                break
        if current_round_def:
            while not all(
                series_is_decided(
                    conn,
                    get_series_id(conn, season_id, sn),
                    current_round_def["best_of"],
                )
                for sn in current_round_def["series_names"]
                if get_series_id(conn, season_id, sn)
            ):
                n = _play_day()
                if n == 0:
                    break
                games_played += n

    elif mode == "all":
        # Play all remaining games
        while True:
            n = _play_day()
            if n == 0:
                break
            games_played += n

    current_round = _current_round_name()

    # Check if Finals decided → crown champion
    finals_sid = get_series_id(conn, season_id, "Finals")
    if finals_sid and series_is_decided(conn, finals_sid, 7):
        champion = get_series_winner(conn, finals_sid, 7)
        conn.execute(
            "UPDATE leagues SET state = 'offseason' WHERE id = %s", (league_id,)
        )
        conn.commit()

    # Diff injuries to find new injuries and returns for GM's team
    injured_after = _get_injured(gm_team_id)
    new_injuries = [
        {"name": v["name"], "days": v["days"]}
        for pid, v in injured_after.items()
        if pid not in injured_before
    ]
    returned = [
        {"name": v["name"]}
        for pid, v in injured_before.items()
        if pid not in injured_after
    ]

    # Most recently played game date
    last_game = conn.execute(
        """SELECT MAX(g.game_date) as d FROM games g
           JOIN series s ON g.series_id = s.id
           WHERE s.season_id = %s AND g.completed = 1""",
        (season_id,),
    ).fetchone()
    current_date = last_game["d"] if last_game and last_game["d"] else None

    return {
        "games_played": games_played,
        "results": results,
        "current_round": current_round,
        "champion": champion,
        "new_injuries": new_injuries,
        "returned": returned,
        "current_date": current_date,
    }
