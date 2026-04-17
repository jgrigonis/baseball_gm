# src/league/play_season.py
"""
Play games in a season.
"""

import argparse
from datetime import datetime
import logging
import random
import traceback

from src.db.connection import get_connection
from src.db.repositories.bullpen_roles_repo import BullpenRepository
from src.db.repositories.game_lineup_repo import LineupRepository
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.lineup_preference_repo import LineupPreferenceRepository
from src.db.repositories.pitcher_state import PitcherStateRepository, MIN_ENERGY_STARTER
from src.db.repositories.player_energy import PlayerEnergyRepository
from src.db.repositories.player_games import PlayerGameRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.game.game import Game
from src.game.game_event_logger import GameEventLogger
from src.league.statistics.print_standings import print_standings
from src.team.team_in_game import TeamInGame
from src.util.logger import setup_logger


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season-id", "-i", required=True, help="Season ID to play")
    parser.add_argument(
        "--seed", "-s", type=int, help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--force", "-f", action="store_true", help="Replay completed games"
    )
    parser.add_argument("--limit", "-l", type=int, help="Limit number of games to play")
    parser.add_argument(
        "--resume", "-r", action="store_true", help="Resume from last completed game"
    )
    parser.add_argument(
        "--logs", action="store_true", help="Keep logfiles for each game"
    )
    return parser.parse_args()


def clear_game_data(conn, game_id: str):
    conn.execute("DELETE FROM player_game_stats WHERE game_id = %s", (game_id,))
    conn.execute("DELETE FROM team_game_stats WHERE game_id = %s", (game_id,))
    conn.execute("DELETE FROM player_game_fielding WHERE game_id = %s", (game_id,))
    conn.execute("DELETE FROM game_lineup_slots WHERE game_id = %s", (game_id,))
    conn.execute(
        "UPDATE games SET home_score=NULL,away_score=NULL,winner_id=NULL,innings_played=NULL,completed=0 WHERE id=%s",
        (game_id,),
    )
    conn.commit()


def save_player_stats(conn, game_id, home_team, away_team):
    conn.execute("DELETE FROM player_game_stats WHERE game_id = %s", (game_id,))
    conn.execute("DELETE FROM player_game_fielding WHERE game_id = %s", (game_id,))
    conn.commit()
    player_game_repo = PlayerGameRepository(conn)
    for team, opp in [(home_team, away_team), (away_team, home_team)]:
        for player in team.players:
            if (
                player.game_stats.batting.plate_appearances > 0
                or player.game_stats.pitching.pitch_count > 0
                or player.game_stats.fielding.chances > 0
            ):
                fielding_positions = list(player.fielding_by_position.items())
                for position, _ in fielding_positions:
                    if position is None:
                        raise ValueError(
                            f"Cannot insert fielding stats for {player.id}: position is None"
                        )
                player_game_repo.insert_player_game(
                    game_id=game_id,
                    player_id=player.id,
                    team_id=team.record.id,
                    opponent_team_id=opp.record.id,
                    stats=player.game_stats,
                    fielding_positions=fielding_positions,
                )
    conn.commit()


def load_energy(conn, game_repo, game_id, home_team, away_team, league_id=""):
    pitcher_repo = PitcherStateRepository(conn, league_id=league_id)
    game_record = game_repo.get(game_id)
    game_date = datetime.fromisoformat(game_record["game_date"]).date()
    for player in home_team.players + away_team.players:
        state = pitcher_repo.get_with_recovery(
            player_id=player.id,
            game_date=game_date,
            recovery_skill=player.skills["recovery"],
        )
        if player.pitcher_fatigue:
            player.pitcher_fatigue.set_energy(state.current_energy, state.max_energy)
    return game_date


def save_energy(conn, game_date, home_team, away_team, league_id=""):
    pitcher_repo = PitcherStateRepository(conn, league_id=league_id)
    for player in home_team.players + away_team.players:
        if player.game_stats.pitching.pitch_count > 0:
            player.pitcher_fatigue.degrade_cap(player.game_stats.pitching.pitch_count)
            pitcher_repo.update_after_game(
                player_id=player.id,
                final_energy=player.pitcher_fatigue.energy,
                max_energy=player.pitcher_fatigue.max_energy,
                pitch_count=player.game_stats.pitching.pitch_count,
                game_date=game_date,
            )


def save_position_energy(conn, player_energy_states, league_id):
    repo = PlayerEnergyRepository(conn, league_id)
    for state in player_energy_states.values():
        if state.season_games_played > 0 or state.last_game_date is not None:
            repo.save_player_energy(state)


def _load_eligible_ids(conn, team_id: str, league_id: str, blitz: bool) -> set[str]:
    """Return player IDs eligible to play based on league mode.
    Blitz: 26man + 40man. Long form: 26man only.
    """
    statuses = "'26man','40man'" if blitz else "'26man'"
    rows = conn.execute(
        f"""SELECT ps.player_id FROM player_status ps
            JOIN team_players tp ON tp.player_id = ps.player_id
            WHERE tp.team_id = %s AND ps.status IN ({statuses})""",
        (team_id,),
    ).fetchall()
    return {r["player_id"] for r in rows}


def _pick_starter(
    rotations_repo: TeamRotationsRepository,
    pitcher_repo: PitcherStateRepository,
    team_id: str,
    season_id: str,
    game_date,
    series_id: str = "",
    injured_ids: set | None = None,
    team_players: list | None = None,
    eligible_ids: set | None = None,
) -> tuple[str | None, bool]:
    """
    Returns (starter_id, should_advance_pointer).

    Normal start (rotation pitcher healthy + rested):
        (pitcher_id, True)  — advance pointer after game

    Spot start (scheduled pitcher is injured):
        (bullpen_pid, False) — use non-rotation pitcher, keep pointer on injured slot
                               so the injured pitcher resumes their spot when healthy

    No rotation or all pitchers unavailable:
        (None, False) — caller falls back to stamina-based selection
    """
    injured_ids = injured_ids or set()
    team_players = team_players or []

    def _eligible(pid: str) -> bool:
        return eligible_ids is None or pid in eligible_ids

    scheduled = rotations_repo.get_scheduled_starter(team_id, season_id, series_id)
    if not scheduled:
        return None, False

    rotation = rotations_repo.get_current_rotation(team_id, season_id, game_date)
    if not rotation:
        return None, False

    rotation_ids = {r["player_id"] for r in rotation}

    # ── Scheduled pitcher is injured → spot start from bullpen ────────────────
    if scheduled in injured_ids:
        # Find bullpen candidates: pitchers not in rotation and not injured
        bullpen = [
            p
            for p in team_players
            if p.pitcher_fatigue
            and p.id not in rotation_ids
            and p.id not in injured_ids
            and _eligible(p.id)
        ]
        if bullpen:
            # Filter to pitchers with enough energy to start, excluding closers
            ready = [
                p
                for p in bullpen
                if pitcher_repo.get_with_recovery(
                    p.id, game_date, p.skills.get("recovery", 50)
                ).current_energy
                >= MIN_ENERGY_STARTER
                and getattr(p, "bullpen_role", None) != "Closer"
            ]
            pool = (
                ready if ready else bullpen
            )  # fall back to full bullpen if none ready
            # Pick highest effective stamina (stamina adjusted by fatigue) among eligible pitchers
            best = max(
                pool, key=lambda p: p.get_effective_stat(p.skills.get("stamina", 0))
            )
            return (
                best.id,
                False,
            )  # do NOT advance pointer — injured pitcher reclaims slot when healthy

        # No bullpen available — walk healthy rotation pitchers as last resort
        # (still don't advance so the injured slot isn't lost)
        healthy_rotation = sorted(
            [r for r in rotation if r["player_id"] not in injured_ids],
            key=lambda r: r["rotation_order"],
        )
        if not healthy_rotation:
            return None, False
        best_r = max(
            healthy_rotation,
            key=lambda r: pitcher_repo.get_with_recovery(
                r["player_id"], game_date, 50
            ).current_energy,
        )
        return best_r["player_id"], True

    # ── Scheduled pitcher is healthy — check energy ───────────────────────────
    rotation_sorted = sorted(rotation, key=lambda r: r["rotation_order"])
    orders = [r["rotation_order"] for r in rotation_sorted]
    scheduled_entry = next(
        (r for r in rotation_sorted if r["player_id"] == scheduled), None
    )
    start_idx = (
        orders.index(scheduled_entry["rotation_order"]) if scheduled_entry else 0
    )

    # Walk forward through healthy rotation pitchers looking for rested one
    for i in range(len(rotation_sorted)):
        idx = (start_idx + i) % len(rotation_sorted)
        candidate = rotation_sorted[idx]
        if candidate["player_id"] in injured_ids:
            continue
        state = pitcher_repo.get_with_recovery(
            player_id=candidate["player_id"],
            game_date=game_date,
            recovery_skill=50,
        )
        if state.current_energy >= MIN_ENERGY_STARTER:
            return candidate["player_id"], True

    # All healthy rotation pitchers tired — most rested healthy one
    healthy = [r for r in rotation_sorted if r["player_id"] not in injured_ids]
    if not healthy:
        return None, False
    best = max(
        healthy,
        key=lambda r: pitcher_repo.get_with_recovery(
            r["player_id"], game_date, 50
        ).current_energy,
    )
    return best["player_id"], True


def play_game(
    conn,
    args,
    team_repo: TeamRepository,
    game_repo: GameRepository,
    team_game_repo: TeamGameRepository,
    rotations_repo: TeamRotationsRepository,
    season_id: str,
    game_info: dict,
    rng: random.Random,
    league_id: str = "",
    league_mode: str = "blitz",
):
    """Play a single game and save results."""
    blitz = league_mode == "blitz"

    home_record = team_repo.get(game_info["home_team_id"])
    away_record = team_repo.get(game_info["away_team_id"])
    home_team = TeamInGame(home_record)
    away_team = TeamInGame(away_record)

    game_date = load_energy(
        conn, game_repo, game_info["game_id"], home_team, away_team, league_id=league_id
    )

    # Pitching rotations
    home_rotation = rotations_repo.get_current_rotation(
        home_team.record.id, season_id, game_date
    )
    away_rotation = rotations_repo.get_current_rotation(
        away_team.record.id, season_id, game_date
    )

    home_rotation_ids = {r["player_id"] for r in home_rotation}
    away_rotation_ids = {r["player_id"] for r in away_rotation}
    for player in home_team.players:
        if player.record.id in home_rotation_ids:
            player.is_starter = True
    for player in away_team.players:
        if player.record.id in away_rotation_ids:
            player.is_starter = True

    # Roster eligibility: blitz=40man, long form=26man (handled inside _load_eligible_ids)
    home_eligible = _load_eligible_ids(conn, home_team.record.id, league_id, blitz)
    away_eligible = _load_eligible_ids(conn, away_team.record.id, league_id, blitz)

    # Build injured_ids BEFORE ticking so players finishing their last game of injury
    # are still excluded from today's game (they return for the next game).
    all_player_ids = [p.id for p in home_team.players + away_team.players]
    injury_repo = InjuryRepository(conn, league_id=league_id)
    injured_ids = {pid for pid in all_player_ids if injury_repo.is_injured(pid)}
    injury_repo.tick_all(all_player_ids)

    pitcher_repo = PitcherStateRepository(conn, league_id=league_id)
    series_id = game_info.get("series_id") or ""
    home_starter_id, home_advance = _pick_starter(
        rotations_repo,
        pitcher_repo,
        home_team.record.id,
        season_id,
        game_date,
        series_id,
        injured_ids=injured_ids,
        team_players=list(home_team.players),
        eligible_ids=home_eligible,
    )
    away_starter_id, away_advance = _pick_starter(
        rotations_repo,
        pitcher_repo,
        away_team.record.id,
        season_id,
        game_date,
        series_id,
        injured_ids=injured_ids,
        team_players=list(away_team.players),
        eligible_ids=away_eligible,
    )

    # Fallback: if no rotation set, pick the best healthy pitcher by stamina
    def _best_pitcher_id(team: TeamInGame) -> str | None:
        pitchers = [
            p for p in team.players if p.pitcher_fatigue and p.id not in injured_ids
        ]
        if not pitchers:
            return None
        return max(pitchers, key=lambda p: p.skills.get("stamina", 0)).id

    if not home_starter_id:
        home_starter_id = _best_pitcher_id(home_team)
        if home_starter_id:
            print(f"  ⚠ No rotation for {home_team.record.mascot} — using best pitcher")
    if not away_starter_id:
        away_starter_id = _best_pitcher_id(away_team)
        if away_starter_id:
            print(f"  ⚠ No rotation for {away_team.record.mascot} — using best pitcher")

    # Bullpen roles
    bpr = BullpenRepository(conn)
    home_bullpen = bpr.get_current_roles(home_record.id, season_id)
    away_bullpen = bpr.get_current_roles(away_record.id, season_id)
    home_role_map = {e["player_id"]: e["role"] for e in home_bullpen}
    away_role_map = {e["player_id"]: e["role"] for e in away_bullpen}
    for player in home_team.players:
        if player.id in home_role_map:
            player.bullpen_role = home_role_map[player.id]
    for player in away_team.players:
        if player.id in away_role_map:
            player.bullpen_role = away_role_map[player.id]

    log_level = logging.INFO if args.logs else logging.WARNING
    log_id = game_info["game_id"] if args.logs else None
    logger = setup_logger(
        name="game",
        level=log_level,
        console_level=logging.WARNING,
        log_id=log_id,
        log_to_file=bool(args.logs),
    )

    _ps_repo = PitcherStateRepository(conn)
    pitcher_states = {pid: _ps_repo.get(pid) for pid in all_player_ids}

    energy_repo = PlayerEnergyRepository(conn)
    player_energy_states = {
        p.id: energy_repo.get_with_recovery(
            p.id, game_date, durability=p.skills.get("durability", 50)
        )
        for p in home_team.position_players + away_team.position_players
    }
    for player in home_team.position_players + away_team.position_players:
        state = player_energy_states.get(player.id)
        if state and player.player_energy:
            player.player_energy.set_position_energy(
                state.current_energy, state.max_energy
            )

    lpr = LineupPreferenceRepository(conn)
    home_saved = lpr.get_preferences(home_team.record.id, league_id)
    away_saved = lpr.get_preferences(away_team.record.id, league_id)
    # home_saved = _load_saved_lineup(conn, home_team.record.id, league_id)
    # away_saved = _load_saved_lineup(conn, away_team.record.id, league_id)

    event_logger = GameEventLogger(conn, game_id=game_info["game_id"])
    game = Game(
        home_team=home_team,
        away_team=away_team,
        rng=rng,
        logger=logger,
        pitcher_states=pitcher_states,
        game_date=game_date,
        player_energy_states=player_energy_states,
        injured_ids=injured_ids,
        event_logger=event_logger,
        home_eligible=home_eligible,
        away_eligible=away_eligible,
    )

    home_team.set_lineup(
        starting_pitcher_id=home_starter_id,
        dh=True,
        injured_ids=injured_ids,
        restrict_to_ids=home_eligible or None,
        saved_lineup=home_saved,
    )
    away_team.set_lineup(
        starting_pitcher_id=away_starter_id,
        dh=True,
        injured_ids=injured_ids,
        restrict_to_ids=away_eligible or None,
        saved_lineup=away_saved,
    )

    lineup_repo = LineupRepository(conn)
    lineup_repo.save_lineup(
        game_info["game_id"], home_record.id, home_team.lineup, home_team.pitcher
    )
    lineup_repo.save_lineup(
        game_info["game_id"], away_record.id, away_team.lineup, away_team.pitcher
    )

    home_starter = next(
        (p for p in home_team.players if p.record.id == home_starter_id), None
    )
    away_starter = next(
        (p for p in away_team.players if p.record.id == away_starter_id), None
    )
    home_energy = (
        f"{home_starter.pitcher_fatigue.energy:.1f}"
        if home_starter and home_starter.pitcher_fatigue
        else "N/A"
    )
    away_energy = (
        f"{away_starter.pitcher_fatigue.energy:.1f}"
        if away_starter and away_starter.pitcher_fatigue
        else "N/A"
    )
    print(
        f"  ⚾ {away_team.record.mascot}"
        f" ({away_starter.record.last_name if away_starter else '?'}, energy={away_energy})"
        f" @ {home_team.record.mascot}"
        f" ({home_starter.record.last_name if home_starter else '?'}, energy={home_energy})"
    )

    logger.info(home_team.output_lineup_ratings())
    logger.info(home_team.output_pitcher_ratings())
    logger.info(away_team.output_lineup_ratings())
    logger.info(away_team.output_pitcher_ratings())
    logger.info(home_team.output_lineup_skills())
    logger.info(home_team.output_pitcher_skills())
    logger.info(away_team.output_lineup_skills())
    logger.info(away_team.output_pitcher_skills())
    logger.info(home_team.output_lineup_card())
    logger.info(away_team.output_lineup_card())
    logger.info(home_team.output_rotation_card())
    logger.info(away_team.output_rotation_card())
    logger.info(home_team.output_bullpen_card())
    logger.info(away_team.output_bullpen_card())

    result = game.play()

    winner_id = (
        game_info["home_team_id"]
        if result.home_score > result.away_score
        else game_info["away_team_id"]
    )
    game_repo.save_game_result(game_info["game_id"], result, winner_id)
    if home_advance:
        rotations_repo.advance_rotation_pointer(
            home_team.record.id, season_id, series_id
        )
    if away_advance:
        rotations_repo.advance_rotation_pointer(
            away_team.record.id, season_id, series_id
        )
    team_game_repo.save_game_stats(
        game_info["game_id"],
        game_info["home_team_id"],
        game_info["away_team_id"],
        home_team,
        away_team,
        result.home_score,
        result.away_score,
    )
    save_player_stats(conn, game_info["game_id"], home_team, away_team)

    for player_id in game.batters_this_game:
        state = player_energy_states.get(player_id)
        if state:
            state.consecutive_days += 1
            state.season_games_played += 1
            state.last_game_date = game_date

    save_energy(conn, game_date, home_team, away_team, league_id=league_id)
    save_position_energy(conn, player_energy_states, league_id)

    for player_id, severity, activity in game.new_injuries:
        injury_repo.injure(
            player_id,
            season_id,
            game_date,
            severity=severity,
            activity=activity,
            rng=rng,
        )

    logger.info(home_team.output_defensive_stats())
    logger.info(away_team.output_defensive_stats())
    logger.info(home_team.output_batting_stats())
    logger.info(away_team.output_batting_stats())
    logger.info(home_team.output_pitching_stats())
    logger.info(away_team.output_pitching_stats())

    # moving from game_lineup_repo
    conn.commit()

    return result


def main():
    args = get_args()
    start_time = datetime.now()
    conn = get_connection()

    season_logger = setup_logger(
        name="season",
        level=logging.INFO,
        console_level=logging.WARNING,
        log_id="season",
        log_to_file=True,
    )

    league_row = conn.execute(
        "SELECT league_id FROM league_seasons WHERE season_id = %s LIMIT 1",
        (args.season_id,),
    ).fetchone()
    league_id = league_row["league_id"] if league_row else ""

    league_mode = "blitz"
    if league_id:
        lr = conn.execute(
            "SELECT mode FROM leagues WHERE id = %s", (league_id,)
        ).fetchone()
        if lr:
            league_mode = lr["mode"] or "blitz"

    game_repo = GameRepository(conn)
    team_repo = TeamRepository(conn)
    team_game_repo = TeamGameRepository(conn)
    rotations_repo = TeamRotationsRepository(conn)

    games = game_repo.get_season_games(
        season_id=args.season_id, incomplete_only=args.resume, regular_season_only=True
    )
    if not games:
        print(f"❌ No games found for season {args.season_id}")
        if args.resume:
            print("   All games already completed! Use --force to replay.")
        return

    total_games = len(games)
    if args.limit:
        games = games[: args.limit]

    print(f"🏟️  Playing {len(games)} games for season {args.season_id}")
    if args.resume:
        print(f"   (Resuming - {total_games - len(games)} already completed)")

    seed = args.seed if args.seed is not None else random.randint(0, 999999)
    season_logger.info(f"🎲 Seed: {seed}")
    season_logger.info(f"season id: {args.season_id}")
    rng = random.Random(seed)

    completed = 0
    for i, game_info in enumerate(games, 1):
        if game_info["completed"] and not args.force:
            print(f"[{i}/{len(games)}] Skipping completed game {game_info['game_id']}")
            continue
        if game_info["completed"] and args.force:
            clear_game_data(conn, game_info["game_id"])

        try:
            result = play_game(
                conn,
                args,
                team_repo,
                game_repo,
                team_game_repo,
                rotations_repo,
                args.season_id,
                game_info,
                rng,
                league_id=league_id,
                league_mode=league_mode,
            )
            completed += 1
            if completed % 10 == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = (len(games) - completed) / rate if rate > 0 else 0
                msg = (
                    f"[{i}/{len(games)}] ✅ {completed} games completed"
                    f" ({rate:.1f} games/sec, ~{remaining:.0f}s remaining)"
                )
                print(msg)
                if args.logs:
                    season_logger.info(msg)
            else:
                print(f"[{i}/{len(games)}] ✅ {result}")
                if args.logs:
                    season_logger.info(f"[{i}/{len(games)}] ✅ {result}")
        except Exception as e:
            print(
                f"[{i}/{len(games)}] ❌ Error playing game {game_info['game_id']}: {e}"
            )
            print(traceback.format_exc())
            continue

    elapsed = (datetime.now() - start_time).total_seconds()
    msg_complete = (
        f"✅ Season complete! Games played: {completed},"
        f" Time: {elapsed:.1f}s ({completed/elapsed:.2f} games/sec)"
    )
    print("\n" + msg_complete)
    season_logger.info(msg_complete)
    print_standings(args.season_id, season_logger)


if __name__ == "__main__":
    main()
