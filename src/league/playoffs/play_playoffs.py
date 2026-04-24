# src/league/playoffs/play_playoffs.py
"""
src/league/playoffs/play_playoffs.py

Runs the playoff bracket for a season.

Round 1  (BO5) — 4 series seeded 1v8, 2v7, 3v6, 4v5
Semis    (BO7) — [1,8]v[4,5] and [2,7]v[3,6]
Finals   (BO7) — winners of each semi

Games are pre-generated for Round 1 (setup_playoffs.py).
Semi and Finals games are generated here once the prior round's winners
are known, so home/away assignments are correct.

Usage:
    python -m src.league.playoffs.play_playoffs --season-id S1
"""

import argparse
import logging
import random
import traceback
from datetime import date, timedelta

from src.db.connection import get_connection
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.playoff_repo import PlayoffRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.league.play_season import play_game
from src.league.schedule import ScheduledGame
from src.util.logger import setup_logger

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def log_print(msg: str = "", logger: logging.Logger = None):
    print(msg)
    if logger:
        logger.info(msg)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def get_args():
    p = argparse.ArgumentParser()
    p.add_argument("--season-id", "-i", required=True)
    p.add_argument("--seed", "-s", type=int, help="RNG seed for reproducibility")
    p.add_argument("--logs", action="store_true", help="Write per-game log files")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Series helpers
# ---------------------------------------------------------------------------

_WINS_NEEDED = {5: 3, 7: 4}

_HOME_MAP_BO5 = [True, True, False, False, True]
_HOME_MAP_BO7 = [True, True, False, False, False, True, True]

# Day offsets from playoff start (0-indexed)
# Round 1 Group A (3v6, 4v5): days 1,3,5,7,9 → offsets 0,2,4,6,8
_R1_A_OFFSETS = [0, 2, 4, 6, 8]  # 3v6, 4v5
# Round 1 Group B (1v8, 2v7): days 2,4,6,8,10 → offsets 1,3,5,7,9
_R1_B_OFFSETS = [1, 3, 5, 7, 9]  # 1v8, 2v7
# Semifinals: two series alternate days starting day 7
_SEMI_27_36_OFFSETS = [10, 12, 14, 16, 18, 20, 22]  # [2,7]v[3,6]
_SEMI_18_45_OFFSETS = [11, 13, 15, 17, 19, 21, 23]  # [1,8]v[4,5]
# Finals: consecutive days starting day 22
_FINAL_OFFSETS = [25, 26, 28, 29, 30, 32, 33]


def print_series_result(
    conn, series_id: str, best_of: int, logger: logging.Logger = None
) -> None:
    por = PlayoffRepository(conn)
    winner_id = por.get_series_winner(series_id, best_of)
    rows = por.get_win_count(series_id)

    win_map = {r["winner_id"]: r["wins"] for r in rows}
    series = por.get_series_name(series_id)

    # Get both team names
    game = por.get_teams_in_series(series_id)

    team_repo = TeamRepository(conn)

    team_ids = {game["home_team_id"], game["away_team_id"]}
    winner_name = team_repo.get_name(winner_id)
    loser_id = next(t for t in team_ids if t != winner_id)
    loser_name = team_repo.get_name(loser_id)

    w = win_map.get(winner_id, 0)
    l = win_map.get(loser_id, 0)
    log_print(
        f"  🏆 {series['name']}: {winner_name} defeats {loser_name} {w}-{l}",
        logger=logger,
    )


# ---------------------------------------------------------------------------
# Game generation for later rounds
# ---------------------------------------------------------------------------


def generate_round_games(
    conn,
    season_id: str,
    series_id: str,
    high_seed_id: str,
    low_seed_id: str,
    home_map: list[bool],
    start_date: date,
    offsets: list[int],
) -> None:
    """Insert game records for a series whose teams are now known."""
    games = []
    for i, (offset, high_is_home) in enumerate(zip(offsets, home_map), start=1):
        home_id = high_seed_id if high_is_home else low_seed_id
        away_id = low_seed_id if high_is_home else high_seed_id
        game_date = (start_date + timedelta(days=offset)).isoformat()
        games.append(
            ScheduledGame(
                id=f"{series_id}_g{i}",
                season_id=season_id,
                home_team_id=home_id,
                away_team_id=away_id,
                game_date=game_date,
                series_id=series_id,
            )
        )
    game_repo = GameRepository(conn)
    game_repo.insert_schedule(games)
    conn.commit()


# ---------------------------------------------------------------------------
# Home-field for later rounds
# ---------------------------------------------------------------------------


def original_seed(seeds: list[dict], team_id: str) -> int:
    """Return 1-based seed of team_id from the initial seeding list."""
    for i, s in enumerate(seeds, 1):
        if s["team_id"] == team_id:
            return i
    raise ValueError(f"Team {team_id} not found in seeds")


# ---------------------------------------------------------------------------
# Play a full series
# ---------------------------------------------------------------------------


def play_series(
    conn,
    args,
    team_repo,
    game_repo,
    team_game_repo,
    rotations_repo,
    series_id: str,
    series_name: str,
    best_of: int,
    rng: random.Random,
    logger: logging.Logger = None,
    league_id: str = "",
    league_mode: str = "blitz",
) -> str:
    """
    Play all undecided games in a series. Returns the winning team_id.
    """
    # wins_needed = _WINS_NEEDED[best_of]
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"  {series_name}  (Best of {best_of})")
    lines.append(f"{'='*60}")
    output = "\n".join(lines)
    log_print(output, logger)

    game_repo = GameRepository(conn)
    games = game_repo.get_series_games(series_id)
    por = PlayoffRepository(conn)

    for i, game_info in enumerate(games, 1):
        # Check if series already decided before this game
        if por.is_decided(series_id, best_of):
            log_print(f"  Game {i}: Series decided — skipping", logger=logger)
            continue

        if game_info["completed"]:
            # Already played (e.g. on a resume run)
            winner = game_info["winner_id"]
            log_print(f"  Game {i}: Already played — skipping", logger=logger)
            continue

        log_print(f"\n  Game {i}:", logger=logger)
        try:
            result = play_game(
                conn=conn,
                args=args,
                team_repo=team_repo,
                game_repo=game_repo,
                team_game_repo=team_game_repo,
                rotations_repo=rotations_repo,
                season_id=args.season_id,
                game_info={
                    "game_id": game_info["id"],
                    "home_team_id": game_info["home_team_id"],
                    "away_team_id": game_info["away_team_id"],
                    "completed": game_info["completed"],
                },
                rng=rng,
                league_id=league_id,
                league_mode=league_mode,
            )
            log_print(f"    {result}", logger=logger)
        except Exception as e:
            log_print(f"    ❌ Error: {e}", logger=logger)
            log_print(traceback.format_exc(), logger=logger)
            raise

    game_repo.void_remaining_series_games(series_id)
    print_series_result(conn, series_id, best_of, logger)
    por = PlayoffRepository(conn)
    winner = por.get_series_winner(series_id, best_of)
    if winner is None:
        raise RuntimeError(
            f"Series {series_name} ended without a winner — check game results"
        )
    return winner


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    args = get_args()
    conn = get_connection()
    logger = None
    if args.logs:
        logger = setup_logger(
            name="play_playoffs",
            level=logging.INFO,
            console_level=logging.WARNING,
            log_id="play_playoffs",
            log_to_file=True,
        )
    rng = random.Random(args.seed) if args.seed else random.Random()

    team_repo = TeamRepository(conn)
    game_repo = GameRepository(conn)
    team_game_repo = TeamGameRepository(conn)
    rotations_repo = TeamRotationsRepository(conn)
    league_repo = LeagueRepository(conn)

    sid = args.season_id
    log_print(f"\n🏆 Playing playoffs for season {sid}", logger=logger)

    # Recover seeds from R1 series
    por = PlayoffRepository(conn)
    seeds = por.get_seeds(sid)
    # seeds = get_seeds(conn, sid)

    league_id = league_repo.get_league_id_from_season_id(sid)
    league_mode = league_repo.get_league_mode(league_id)

    # Infer playoff start date from first R1 game
    first_game = por.get_first_game(sid)
    playoff_start = date.fromisoformat(first_game["game_date"])

    # ------------------------------------------------------------------
    # Round 1  (BO5)
    # ------------------------------------------------------------------
    log_print("\n📋 ROUND 1", logger=logger)
    r1_matchups = [("1v8", 1, 8), ("2v7", 2, 7), ("3v6", 3, 6), ("4v5", 4, 5)]
    r1_winners = {}  # name -> winning team_id

    for name, hi, lo in r1_matchups:
        series_id = por.get_series_id(sid, name)
        # series_id = get_series_id(conn, sid, name)
        winner = play_series(
            conn,
            args,
            team_repo,
            game_repo,
            team_game_repo,
            rotations_repo,
            series_id,
            name,
            best_of=5,
            rng=rng,
            logger=logger,
            league_id=league_id,
            league_mode=league_mode,
        )
        r1_winners[name] = winner

    # ------------------------------------------------------------------
    # Semifinals  (BO7)
    # Winner of 1v8 vs Winner of 4v5 → [1,8]v[4,5]
    # Winner of 2v7 vs Winner of 3v6 → [2,7]v[3,6]
    # ------------------------------------------------------------------
    log_print("\n📋 SEMIFINALS", logger=logger)

    semi_matchups = [
        ("[1,8]v[4,5]", r1_winners["1v8"], r1_winners["4v5"]),
        ("[2,7]v[3,6]", r1_winners["2v7"], r1_winners["3v6"]),
    ]
    semi_winners = []

    for name, team_a, team_b in semi_matchups:
        series_id = por.get_series_id(sid, name)
        # series_id = get_series_id(conn, sid, name)

        # Determine home/away by original seeding
        seed_a = original_seed(seeds, team_a)
        seed_b = original_seed(seeds, team_b)
        high_seed_id = team_a if seed_a < seed_b else team_b
        low_seed_id = team_b if seed_a < seed_b else team_a

        # Each semi series has its own offset schedule (alternating days)
        semi_offsets = (
            _SEMI_18_45_OFFSETS if name == "[1,8]v[4,5]" else _SEMI_27_36_OFFSETS
        )

        # Generate games now that teams are known
        generate_round_games(
            conn,
            sid,
            series_id,
            high_seed_id,
            low_seed_id,
            _HOME_MAP_BO7,
            playoff_start,
            semi_offsets,
        )

        winner = play_series(
            conn,
            args,
            team_repo,
            game_repo,
            team_game_repo,
            rotations_repo,
            series_id,
            name,
            best_of=7,
            rng=rng,
            league_id=league_id,
            league_mode=league_mode,
        )
        semi_winners.append((winner, original_seed(seeds, winner)))

    # ------------------------------------------------------------------
    # Finals  (BO7)
    # ------------------------------------------------------------------
    log_print("\n📋 FINALS", logger=logger)

    finalist_a, seed_a = semi_winners[0]
    finalist_b, seed_b = semi_winners[1]
    high_seed_id = finalist_a if seed_a < seed_b else finalist_b
    low_seed_id = finalist_b if seed_a < seed_b else finalist_a

    finals_id = por.get_series_id(sid, "Finals")
    # finals_id = get_series_id(conn, sid, "Finals")
    generate_round_games(
        conn,
        sid,
        finals_id,
        high_seed_id,
        low_seed_id,
        _HOME_MAP_BO7,
        playoff_start,
        _FINAL_OFFSETS,
    )

    champion = play_series(
        conn,
        args,
        team_repo,
        game_repo,
        team_game_repo,
        rotations_repo,
        finals_id,
        "Finals",
        best_of=7,
        rng=rng,
        league_id=league_id,
        league_mode=league_mode,
    )

    champ_name = team_repo.get_name(champion)

    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"  🎉 CHAMPION: {champ_name}")
    lines.append(f"{'='*60}\n")
    output = "\n".join(lines)
    log_print(output, logger)


if __name__ == "__main__":
    main()
