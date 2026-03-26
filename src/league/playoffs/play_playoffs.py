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
    python -m src.league.play_playoffs --db league.db --season-id S1
"""

import argparse
import logging
import random
import traceback
from datetime import date, timedelta

from src.db.connection import get_connection
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.league.play_season import play_game
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
    p.add_argument("--db", "-d", default="league.db")
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

_R1_OFFSETS = [0, 2, 4, 6, 8]
_SEMI_OFFSETS = [11, 13, 15, 17, 19, 21, 23]
_FINAL_OFFSETS = [26, 28, 30, 32, 34, 36, 38]


def get_series_id(conn, season_id: str, name: str) -> str | None:
    row = conn.execute(
        "SELECT id FROM series WHERE season_id = ? AND name = ?",
        (season_id, name),
    ).fetchone()
    return row["id"] if row else None


def get_series_games(conn, series_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, game_date, home_team_id, away_team_id, completed,
               home_score, away_score, winner_id
        FROM games
        WHERE series_id = ?
        ORDER BY game_date
        """,
        (series_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_series_winner(conn, series_id: str, best_of: int) -> str | None:
    """
    Return the winning team_id if the series is decided, else None.
    """
    wins_needed = _WINS_NEEDED[best_of]
    rows = conn.execute(
        """
        SELECT winner_id, COUNT(*) AS wins
        FROM games
        WHERE series_id = ? AND completed = 1
        GROUP BY winner_id
        """,
        (series_id,),
    ).fetchall()

    for row in rows:
        if row["wins"] >= wins_needed:
            return row["winner_id"]
    return None


def series_is_decided(conn, series_id: str, best_of: int) -> bool:
    return get_series_winner(conn, series_id, best_of) is not None


def print_series_result(
    conn, series_id: str, best_of: int, logger: logging.Logger = None
) -> None:
    winner_id = get_series_winner(conn, series_id, best_of)
    rows = conn.execute(
        """
        SELECT winner_id, COUNT(*) AS wins
        FROM games
        WHERE series_id = ? AND completed = 1
        GROUP BY winner_id
        ORDER BY wins DESC
        """,
        (series_id,),
    ).fetchall()

    win_map = {r["winner_id"]: r["wins"] for r in rows}
    series = conn.execute(
        "SELECT name FROM series WHERE id = ?", (series_id,)
    ).fetchone()

    # Get both team names
    game = conn.execute(
        "SELECT home_team_id, away_team_id FROM games WHERE series_id = ? LIMIT 1",
        (series_id,),
    ).fetchone()

    def team_name(tid):
        row = conn.execute(
            "SELECT city || ' ' || mascot AS name FROM teams WHERE id = ?", (tid,)
        ).fetchone()
        return row["name"] if row else tid

    team_ids = {game["home_team_id"], game["away_team_id"]}
    winner_name = team_name(winner_id)
    loser_id = next(t for t in team_ids if t != winner_id)
    loser_name = team_name(loser_id)

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
            {
                "id": f"{series_id}_g{i}",
                "game_date": game_date,
                "season_id": season_id,
                "series_id": series_id,
                "home_team_id": home_id,
                "away_team_id": away_id,
            }
        )

    conn.executemany(
        """
        INSERT OR IGNORE INTO games
            (id, game_date, season_id, series_id, home_team_id, away_team_id)
        VALUES (:id, :game_date, :season_id, :series_id, :home_team_id, :away_team_id)
        """,
        games,
    )
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

    games = get_series_games(conn, series_id)

    for i, game_info in enumerate(games, 1):
        # Check if series already decided before this game
        if series_is_decided(conn, series_id, best_of):
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
            )
            log_print(f"    {result}", logger=logger)
        except Exception as e:
            log_print(f"    ❌ Error: {e}", logger=logger)
            log_print(traceback.format_exc(), logger=logger)
            raise

    print_series_result(conn, series_id, best_of, logger)
    winner = get_series_winner(conn, series_id, best_of)
    if winner is None:
        raise RuntimeError(
            f"Series {series_name} ended without a winner — check game results"
        )
    return winner


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def get_seeds(conn, season_id: str) -> list[dict]:
    """Reconstruct original seeds from R1 series ordering."""
    # Seeds are recoverable from the series names created in setup_playoffs
    # e.g. "1v8" tells us which team was seed 1 vs seed 8
    # We query each R1 series and figure out which team was the high seed
    # (home team in game 1 = high seed, since home map starts True)
    result = {}

    for name, hi, lo in [("1v8", 1, 8), ("2v7", 2, 7), ("3v6", 3, 6), ("4v5", 4, 5)]:
        series_id = get_series_id(conn, season_id, name)
        if not series_id:
            raise ValueError(f"Series {name} not found for season {season_id}")

        # Game 1 home = high seed (home_map[0] = True)
        game = conn.execute(
            "SELECT home_team_id, away_team_id FROM games WHERE series_id = ? ORDER BY game_date LIMIT 1",
            (series_id,),
        ).fetchone()

        result[hi] = game["home_team_id"]
        result[lo] = game["away_team_id"]

    return [{"team_id": result[i], "seed": i} for i in range(1, 9)]


def main():
    args = get_args()
    conn = get_connection(args.db)
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

    sid = args.season_id
    log_print(f"\n🏆 Playing playoffs for season {sid}", logger=logger)

    # Recover seeds from R1 series
    seeds = get_seeds(conn, sid)

    # Infer playoff start date from first R1 game
    first_game = conn.execute(
        """
        SELECT g.game_date FROM games g
        JOIN series s ON g.series_id = s.id
        WHERE s.season_id = ? AND s.name IN ('1v8','2v7','3v6','4v5')
        ORDER BY g.game_date LIMIT 1
        """,
        (sid,),
    ).fetchone()
    playoff_start = date.fromisoformat(first_game["game_date"])

    # ------------------------------------------------------------------
    # Round 1  (BO5)
    # ------------------------------------------------------------------
    log_print("\n📋 ROUND 1", logger=logger)
    r1_matchups = [("1v8", 1, 8), ("2v7", 2, 7), ("3v6", 3, 6), ("4v5", 4, 5)]
    r1_winners = {}  # name -> winning team_id

    for name, hi, lo in r1_matchups:
        series_id = get_series_id(conn, sid, name)
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
        series_id = get_series_id(conn, sid, name)

        # Determine home/away by original seeding
        seed_a = original_seed(seeds, team_a)
        seed_b = original_seed(seeds, team_b)
        high_seed_id = team_a if seed_a < seed_b else team_b
        low_seed_id = team_b if seed_a < seed_b else team_a

        # Generate games now that teams are known
        generate_round_games(
            conn,
            sid,
            series_id,
            high_seed_id,
            low_seed_id,
            _HOME_MAP_BO7,
            playoff_start,
            _SEMI_OFFSETS,
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

    finals_id = get_series_id(conn, sid, "Finals")
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
    )

    champ_name = conn.execute(
        "SELECT city || ' ' || mascot AS name FROM teams WHERE id = ?", (champion,)
    ).fetchone()["name"]

    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"  🎉 CHAMPION: {champ_name}")
    lines.append(f"{'='*60}\n")
    output = "\n".join(lines)
    log_print(output, logger)


if __name__ == "__main__":
    main()
