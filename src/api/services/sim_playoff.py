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
import sqlite3
from dataclasses import dataclass
from datetime import date

from src.db.repositories.games_repo import GameRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.league.playoffs.play_playoffs import (
    _HOME_MAP_BO7,
    _SEMI_OFFSETS,
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
        "SELECT season_id FROM league_seasons WHERE league_id = ? ORDER BY rowid DESC LIMIT 1",
        (league_id,),
    ).fetchone()
    return row["season_id"] if row else None


def _get_playoff_start(conn, season_id: str) -> date:
    row = conn.execute(
        """SELECT g.game_date FROM games g
           JOIN series s ON g.series_id = s.id
           WHERE s.season_id = ? AND s.name IN ('1v8','2v7','3v6','4v5')
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
                "SELECT COUNT(*) FROM games WHERE series_id = ?", (sid,)
            ).fetchone()[0]
            if existing > 0:
                continue
            seed_a = original_seed(seeds, team_a)
            seed_b = original_seed(seeds, team_b)
            high = team_a if seed_a < seed_b else team_b
            low = team_b if seed_a < seed_b else team_a
            generate_round_games(
                conn,
                season_id,
                sid,
                high,
                low,
                _HOME_MAP_BO7,
                playoff_start,
                _SEMI_OFFSETS,
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
                "SELECT COUNT(*) FROM games WHERE series_id = ?", (sid,)
            ).fetchone()[0]
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


def _play_series_to_end(
    conn, season_id, league_id, league_mode, series_id, best_of, rng
) -> list:
    results = []
    while not series_is_decided(conn, series_id, best_of):
        r = _play_one_game(conn, season_id, league_id, league_mode, series_id, rng)
        if r:
            results.append(str(r))
        else:
            break
    return results


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def sim_playoff(
    league_id: str,
    conn: sqlite3.Connection,
    mode: str = "game",
) -> dict:
    """
    Simulate playoff games.
    mode: "game" | "series" | "round" | "all"
    Returns summary dict.
    """
    league = conn.execute("SELECT * FROM leagues WHERE id = ?", (league_id,)).fetchone()
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
        "SELECT team_id FROM gms WHERE league_id = ? AND is_ai = 0 AND team_id IS NOT NULL LIMIT 1",
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
               JOIN team_players tp ON tp.player_id = pi.player_id AND tp.team_id = ?
               WHERE pi.games_remaining > 0 AND (pi.league_id = ? OR pi.league_id = '')""",
            (team_id, league_id),
        ).fetchall()
        return {r["player_id"]: {"name": r["name"], "days": r["games_remaining"]} for r in rows}

    injured_before = _get_injured(gm_team_id)

    for round_idx, round_def in enumerate(ROUND_DEFS):
        # Generate games for this round if needed
        if round_idx > 0:
            _ensure_round_games(conn, season_id, round_idx, seeds)

        # Check if round is already complete
        round_complete = all(
            series_is_decided(
                conn, get_series_id(conn, season_id, sn), round_def["best_of"]
            )
            for sn in round_def["series_names"]
            if get_series_id(conn, season_id, sn)
        )
        if round_complete and round_idx < len(ROUND_DEFS) - 1:
            continue

        current_round = round_def["name"]

        if mode == "game":
            # One game in first undecided series
            for sn in round_def["series_names"]:
                sid = get_series_id(conn, season_id, sn)
                if sid and not series_is_decided(conn, sid, round_def["best_of"]):
                    r = _play_one_game(
                        conn, season_id, league_id, league_mode, sid, rng
                    )
                    if r:
                        games_played += 1
                        results.append({"series": sn, "result": str(r)})
                    break
            break

        elif mode == "series":
            # Play first undecided series to completion
            for sn in round_def["series_names"]:
                sid = get_series_id(conn, season_id, sn)
                if sid and not series_is_decided(conn, sid, round_def["best_of"]):
                    rs = _play_series_to_end(
                        conn,
                        season_id,
                        league_id,
                        league_mode,
                        sid,
                        round_def["best_of"],
                        rng,
                    )
                    games_played += len(rs)
                    results.extend({"series": sn, "result": r} for r in rs)
                    break
            break

        elif mode in ("round", "all"):
            # Play all series in this round to completion
            for sn in round_def["series_names"]:
                sid = get_series_id(conn, season_id, sn)
                if not sid:
                    continue
                rs = _play_series_to_end(
                    conn,
                    season_id,
                    league_id,
                    league_mode,
                    sid,
                    round_def["best_of"],
                    rng,
                )
                games_played += len(rs)
                results.extend({"series": sn, "result": r} for r in rs)

            if mode == "round":
                break
            # else continue to next round

    # Check if Finals decided → crown champion
    finals_sid = get_series_id(conn, season_id, "Finals")
    if finals_sid and series_is_decided(conn, finals_sid, 7):
        champion = get_series_winner(conn, finals_sid, 7)
        conn.execute(
            "UPDATE leagues SET state = 'offseason' WHERE id = ?", (league_id,)
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

    return {
        "games_played": games_played,
        "results": results,
        "current_round": current_round,
        "champion": champion,
        "new_injuries": new_injuries,
        "returned": returned,
    }
