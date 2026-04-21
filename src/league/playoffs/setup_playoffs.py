# src/league/playoffs/setup_playoffs.py
"""
src/league/playoffs/setup_playoffs.py

One-time setup for the playoff bracket after the regular season ends.

Steps:
  1. Seed top 8 teams by win%
  2. Demote each team's 4th/5th rotation starters to Long bullpen role
  3. Create series records
  4. Pre-generate all possible games with dates and home/away assignments
     (unplayed games in eliminated series are simply skipped at play time)

Usage:
    python -m src.league.setup_playoffs --season-id S1 --start-date 2025-10-01
"""
# from __future__ import annotations
import argparse
import logging
from datetime import date, timedelta
# from typing import TYPE_CHECKING

from src.db.connection import get_connection
from src.db.repositories.bullpen_roles_repo import BullpenRepository
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.playoff_repo import PlayoffRepository
from src.db.repositories.standings_repo import StandingsRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
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
    p.add_argument(
        "--season-id", "-i", required=True, help="Season ID to build playoffs for"
    )
    p.add_argument(
        "--start-date", "-s", required=True, help="First game date (YYYY-MM-DD)"
    )
    p.add_argument(
        "--short-rotation",
        "-r",
        type=int,
        choices=[3, 4, 5],
        default=4,
        help="Keep only this many starters; rest go to Long bullpen (default: 4, drops 5th only)",
    )
    p.add_argument("--logs", action="store_true", help="Write output to log file.")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def get_top_N(conn, season_id: str, num_teams: int = 8) -> list[dict]:
    """Return top N teams sorted by win%, with H2H and RS tiebreakers."""
    return StandingsRepository(conn).get_top_n(season_id, num_teams)


# ---------------------------------------------------------------------------
# Rotation management
# ---------------------------------------------------------------------------


def reset_playoff_rotation_pointers(conn, season_id: str) -> None:
    """Reset all rotation pointers for a season back to order 1."""
    rot_repo = TeamRotationsRepository(conn)
    reset = rot_repo.reset_rotation_pointers(season_id)
    print(f"  Reset rotation pointers to sp1 for {reset} teams")


def demote_extra_starters(
    conn, season_id: str, teams: list[dict], keep: int, logger: logging.Logger = None
) -> None:
    """
    For each team, keep only `keep` rotation slots active.
    Demote remaining starters to Long bullpen role.
    """
    today = date.today().isoformat()
    rot_repo = TeamRotationsRepository(conn)
    bull_repo = BullpenRepository(conn)

    for team in teams:
        team_id = team["team_id"]

        # Get current active rotation ordered by slot
        rotation = rot_repo.get_current_rotation(team_id, season_id, today)

        to_demote = [r["player_id"] for r in rotation if r["rotation_order"] > keep]

        for player_id in to_demote:
            # Close out the rotation slot
            rot_repo.remove_from_rotation(team_id, season_id, player_id, today)

            # Close any existing bullpen role first (idempotent)
            bull_repo.remove_role(team_id, player_id, season_id, today)

            # Insert Long role
            bull_repo.update_role(team_id, player_id, season_id, 'Long', today)

            log_print(
                f"  ↓ {team['team_name']} — player {player_id} demoted to Long relief",
                logger=logger,
            )

    conn.commit()


# ---------------------------------------------------------------------------
# Bracket / series helpers
# ---------------------------------------------------------------------------

# Home-field game map for Round 1 (BO5): True = higher seed is home
_HOME_MAP_BO5 = [True, True, False, False, True]


def _series_games(
    series_id: str,
    season_id: str,
    high_seed_id: str,
    low_seed_id: str,
    home_map: list[bool],
    start_date: date,
    offsets: list[int],
) -> list[dict]:
    """Build the full list of pre-generated game dicts for one series."""
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
    return games


def _insert_games(conn, schedule: list[dict]) -> None:
    game_repo = GameRepository(conn)
    game_repo.insert_schedule(schedule)


# ---------------------------------------------------------------------------
# Main bracket builder
# ---------------------------------------------------------------------------

# Day offsets relative to playoff start (every other day, 0-indexed)
# Round 1: two groups on alternating days
_R1_A_OFFSETS = [0, 2, 4, 6, 8]  # 3v6, 4v5  (days 1,3,5,7,9)
_R1_B_OFFSETS = [1, 3, 5, 7, 9]  # 1v8, 2v7  (days 2,4,6,8,10)


def build_bracket(
    conn,
    season_id: str,
    seeds: list[dict],
    start_date: date,
    logger: logging.Logger = None,
) -> None:
    """
    Create all series and pre-generate all possible games.
    seeds is a list of 8 dicts ordered [1st, 2nd, ..., 8th].
    """
    sid = season_id  # shorthand
    pr = PlayoffRepository(conn)

    # Seed index helpers (0-based list → 1-based seed)
    def team(seed: int) -> str:
        return seeds[seed - 1]["team_id"]

    # ------------------------------------------------------------------
    # Round 1  (BO5)
    # ------------------------------------------------------------------
    # Group A plays on odd playoff days (1,3,5,7,9), Group B on even (2,4,6,8,10)
    r1_matchups = [
        ("3v6", 3, 6, _R1_A_OFFSETS),
        ("4v5", 4, 5, _R1_A_OFFSETS),
        ("1v8", 1, 8, _R1_B_OFFSETS),
        ("2v7", 2, 7, _R1_B_OFFSETS),
    ]

    for name, hi, lo, offsets in r1_matchups:
        series_id = f"{sid}_{name}"
        pr.create_series(series_id, sid, name)
        games = _series_games(
            series_id=series_id,
            season_id=sid,
            high_seed_id=team(hi),
            low_seed_id=team(lo),
            home_map=_HOME_MAP_BO5,
            start_date=start_date,
            offsets=offsets,
        )
        _insert_games(conn, games)
        log_print(
            f"  📋 Series {name}: {seeds[hi-1]['team_name']} vs {seeds[lo-1]['team_name']} ({len(games)} games)",
            logger=logger,
        )

    # ------------------------------------------------------------------
    # Semifinals + Finals — create series records only.
    # Games are generated by play_playoffs.py once Round 1 winners are known,
    # so home/away assignments can be set correctly.
    # ------------------------------------------------------------------
    for name in ("[1,8]v[4,5]", "[2,7]v[3,6]", "Finals"):
        pr.create_series(f"{sid}_{name}", sid, name)
        log_print(
            f"  📋 Series {name}: record created (games generated after Round 1)",
            logger=logger,
        )

    conn.commit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    args = get_args()
    start_date = date.fromisoformat(args.start_date)
    logger = None
    if args.logs:
        logger = setup_logger(
            name="setup_playoffs",
            level=logging.INFO,
            console_level=logging.WARNING,
            log_id="setup_playoffs",
            log_to_file=True,
        )
    conn = get_connection()
    lines = []
    lines.append(f"\n🏆 Setting up playoffs for season {args.season_id}")
    lines.append(f"   Start date : {start_date}")
    lines.append(f"   Rotation   : keeping top {args.short_rotation} starters\n")

    # 1. Seed teams
    seeds = get_top_N(conn, args.season_id)
    lines.append("Playoff seeds:")
    for i, s in enumerate(seeds, 1):
        lines.append(
            f"  {i}. {s['team_name']}  ({s['wins']}-{s['losses']}, {s['win_pct']:.3f})"
        )

    # 2. Demote extra starters
    lines.append("\nAdjusting rotations...")
    demote_extra_starters(
        conn, args.season_id, seeds, keep=args.short_rotation, logger=logger
    )

    # 2.5 Reset rotation pointers
    lines.append("\nResetting rotation pointers...")
    reset_playoff_rotation_pointers(conn, args.season_id)

    # 3. Build bracket + pre-generate games
    lines.append("\nBuilding bracket...")
    build_bracket(conn, args.season_id, seeds, start_date, logger=logger)

    conn.commit()

    lines.append("\n✅ Playoff bracket ready.")
    output = "\n".join(lines)
    log_print(output, logger)


if __name__ == "__main__":
    main()
