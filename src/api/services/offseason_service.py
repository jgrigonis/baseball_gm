# src/api/services/offseason_service.py
"""
Runs the full offseason pipeline for a league, then creates the next season
directly in the DB so the league transitions back to 'draft' state.

We deliberately bypass LeagueBootstrapper for year 2+ because:
  - Player skills are already updated in the DB by the pipeline's _age step
  - The bootstrapper's get_or_create_league may create a second league record
  - We need year 2's season to be in the SAME league, with the SAME teams

Steps:
  1. OffseasonPipeline.run() — archive, age, retire, generate_draft (stops here)
  2. Create next season record directly in DB under the same league_id
  3. Copy league_season_teams from year 1
  4. Generate schedule
  5. Create draft record
  6. Set league state → 'draft'
  Post-draft (after UI draft): trim, rotations, energy, stats, csvs (via execute_blitz_draft)
"""

from __future__ import annotations

import datetime
import random


from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.gm_repo import GMRepository
from src.league.offseason.offseason_pipeline import OffseasonPipeline
from src.league.rotation_seeder import seed_ai_rotations
from src.league.offseason.snake_draft import write_draft_order
from src.league.offseason.snake_draft import SnakeDraft
from src.league.schedule import ScheduleGenerator, save_schedule_to_db


def _create_next_season(
    conn, league_id: str, current_season_id: str, next_year: int
) -> tuple[str, list[str]]:
    """
    Create the year N+1 season, link it to the existing league, copy teams.
    Returns (new_season_id, [team_ids]).
    """
    sr = SeasonRepository(conn)
    lr = LeagueRepository(conn)
    current = sr.get_season(current_season_id)
    current_name = current["name"] if current else f"Season {next_year - 1}"

    # Increment season number in name: "Season 1" → "Season 2"
    parts = current_name.rsplit(" ", 1)
    try:
        new_name = f"{parts[0]} {int(parts[1]) + 1}"
    except (IndexError, ValueError):
        new_name = f"Season {next_year}"

    new_season_id = sr.create_season(next_year, new_name)
    lr.assign_season_to_league(league_id, new_season_id)

    # Copy teams from current season
    team_ids = lr.get_league_teams(league_id, current_season_id)
    for tid in team_ids:
        lr.assign_team_to_league(league_id, new_season_id, tid)

    # Seed rotations for AI teams only — humans set their own post-draft
    human_team_ids = GMRepository(conn).get_human_team_ids(league_id)
    ai_team_ids = set(team_ids) - human_team_ids
    seed_ai_rotations(
        conn,
        new_season_id,
        ai_team_ids,
        statuses=["26man"],
        effective_date=f"{next_year}-04-01",
        league_id=league_id,
    )

    conn.commit()
    return new_season_id, team_ids


def run_offseason(league_id: str, conn) -> dict:
    """
    Run the full offseason for a league and return to draft state.
    Idempotent — pipeline skips completed steps; season creation is guarded.
    """
    lr = LeagueRepository(conn)
    sr = SeasonRepository(conn)
    league = lr.get_by_id(league_id)
    if not league:
        raise ValueError(f"League {league_id} not found")
    if league["state"] not in ("offseason",):
        raise ValueError(
            f"League must be in 'offseason' state, currently '{league['state']}'"
        )

    season_id = sr.get_current_id_for_league(league_id)
    if not season_id:
        raise ValueError("No season found for this league")

    season = sr.get_season(season_id)
    current_year = season["year"]
    next_year = current_year + 1
    league_mode = dict(league).get("mode", "blitz") or "blitz"
    rng = random.Random()

    # ── 1. Run offseason pipeline ─────────────────────────────────────────────
    # Stop after draft generation — trim/rotations run after the UI draft completes.
    print(f"Running offseason pipeline for {league_id} (season {season_id})...")
    pipeline = OffseasonPipeline(conn, rng)
    pipeline.run(season_id, league_id=league_id, stop_after_draft_gen=True)

    # ── 2. Create next season directly in DB ──────────────────────────────────
    existing_next = sr.get_by_league_and_year(league_id, next_year)

    if existing_next:
        new_season_id = existing_next["season_id"]
        team_ids = lr.get_league_teams(league_id, new_season_id)
        print(f"  Season {next_year} already exists: {new_season_id}")
    else:
        new_season_id, team_ids = _create_next_season(
            conn, league_id, season_id, next_year
        )
        print(f"  Created season {next_year}: {new_season_id} ({len(team_ids)} teams)")

    # ── 3. Generate schedule ──────────────────────────────────────────────────
    gr = GameRepository(conn)
    existing_games = gr.games_remaining(new_season_id)

    if existing_games == 0:
        start_date = datetime.date(next_year, 4, 1)
        scheduler = ScheduleGenerator(rng=rng)
        schedule = scheduler.create_schedule(
            season_id=new_season_id,
            team_ids=team_ids,
            start_date=start_date,
            games_per_series=3,
            home_and_away=True,
        )
        save_schedule_to_db(conn, schedule)
        game_count = len(schedule)
        print(f"  Schedule generated: {game_count} games")
    else:
        game_count = existing_games
        print(f"  Schedule already exists: {game_count} games")

    # ── 4. Create draft record ────────────────────────────────────────────────
    dr = DraftRepository(conn)
    existing_draft_id = dr.get_draft_id(league_id, new_season_id)

    if not existing_draft_id:

        draft_format = "preference" if league_mode == "blitz" else "interactive"
        draft_id = dr.create_draft(league_id, new_season_id, draft_format)
        conn.commit()

        # Write draft order — standings-based for season 2+, randomized for first season
        snake = SnakeDraft(conn, league_id, rng)
        draft_order = snake._build_draft_order(
            season_id
        )  # season_id = completed season
        ordered_ids = [e["team_id"] for e in draft_order]
        write_draft_order(conn, draft_id, league_id, next_year, ordered_ids)
        print(f"  Draft order stored: {len(ordered_ids)} teams")
    else:
        draft_id = existing_draft_id

    # ── 5. Transition league state → draft ────────────────────────────────────
    lr.set_state(league_id, "draft")
    conn.commit()

    print(f"  Offseason complete → state=draft, season {new_season_id}")

    return {
        "prev_season_id": season_id,
        "new_season_id": new_season_id,
        "new_year": next_year,
        "draft_id": draft_id,
        "game_count": game_count,
        "team_count": len(team_ids),
    }
