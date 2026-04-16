# src/api/services/offseason_service.py
"""
Runs the full offseason pipeline for a league, then creates the next season
directly in the DB so the league transitions back to 'draft' state.

We deliberately bypass LeagueBootstrapper for year 2+ because:
  - Player skills are already updated in the DB by the pipeline's _age step
  - The bootstrapper's get_or_create_league may create a second league record
  - We need year 2's season to be in the SAME league, with the SAME teams

Steps:
  1. OffseasonPipeline.run() — archive, age, retire, generate_draft, trim, reset, write_csvs
     (run_draft pre-marked done; human draft handles all 30 teams)
  2. Create next season record directly in DB under the same league_id
  3. Copy league_season_teams from year 1
  4. Generate schedule
  5. Create draft record
  6. Set league state → 'draft'
"""

from __future__ import annotations

import datetime
import random
import uuid

from src.league.offseason.offseason_pipeline import OffseasonPipeline
from src.league.offseason.snake_draft import write_draft_order
from src.league.offseason.snake_draft import SnakeDraft
from src.league.schedule import ScheduleGenerator, save_schedule_to_db

def _get_season_id(conn, league_id: str) -> str | None:
    row = conn.execute(
        "SELECT season_id FROM league_seasons ls JOIN seasons s ON s.id = ls.season_id WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1",
        (league_id,),
    ).fetchone()
    return row["season_id"] if row else None


def _get_season(conn, season_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM seasons WHERE id = %s", (season_id,)).fetchone()
    return dict(row) if row else None


def _create_next_season(
    conn, league_id: str, current_season_id: str, next_year: int
) -> tuple[str, list[str]]:
    """
    Create the year N+1 season, link it to the existing league, copy teams.
    Returns (new_season_id, [team_ids]).
    """
    current = _get_season(conn, current_season_id)
    current_name = current["name"] if current else f"Season {next_year - 1}"

    # Increment season number in name: "Season 1" → "Season 2"
    parts = current_name.rsplit(" ", 1)
    try:
        new_name = f"{parts[0]} {int(parts[1]) + 1}"
    except (IndexError, ValueError):
        new_name = f"Season {next_year}"

    new_season_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO seasons (id, year, name) VALUES (%s, %s, %s)",
        (new_season_id, next_year, new_name),
    )
    conn.execute(
        "INSERT INTO league_seasons (league_id, season_id) VALUES (%s, %s)",
        (league_id, new_season_id),
    )

    # Copy teams from current season
    team_rows = conn.execute(
        "SELECT team_id FROM league_season_teams WHERE league_id = %s AND season_id = %s",
        (league_id, current_season_id),
    ).fetchall()
    team_ids = [r["team_id"] for r in team_rows]
    for tid in team_ids:
        conn.execute(
            "INSERT INTO league_season_teams (league_id, season_id, team_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (league_id, new_season_id, tid),
        )

    # Bootstrap rotations and bullpen roles for the new season
    from src.league.bootstrap import LeagueBootstrapper
    from src.db.repositories.team_repo import TeamRepository as _TeamRepo

    _rng = random.Random()
    _boot = LeagueBootstrapper(conn, rng=_rng)
    _team_repo = _TeamRepo(conn)
    _teams = [_team_repo.get(tid) for tid in team_ids]
    _teams = [t for t in _teams if t]
    _start = datetime.date(next_year, 4, 1)
    _boot._bootstrap_rotations(_teams, new_season_id, _start)

    conn.commit()
    return new_season_id, team_ids


def run_offseason(league_id: str, conn) -> dict:
    """
    Run the full offseason for a league and return to draft state.
    Idempotent — pipeline skips completed steps; season creation is guarded.
    """
    league = conn.execute(
        "SELECT * FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if not league:
        raise ValueError(f"League {league_id} not found")
    if league["state"] not in ("offseason",):
        raise ValueError(
            f"League must be in 'offseason' state, currently '{league['state']}'"
        )

    season_id = _get_season_id(conn, league_id)
    if not season_id:
        raise ValueError("No season found for this league")

    current_year = _get_season(conn, season_id)["year"]
    next_year = current_year + 1
    league_mode = dict(league).get("mode", "blitz") or "blitz"
    rng = random.Random()

    # ── 1. Run offseason pipeline ─────────────────────────────────────────────
    # Pre-mark run_draft done so the pipeline skips it. The human-facing
    # execute_blitz_draft handles all 30 teams and keeps the prospect pool intact.
    print(f"Running offseason pipeline for {league_id} (season {season_id})...")
    pipeline = OffseasonPipeline(conn, rng)
    pipeline._mark_done(season_id, "run_draft")
    pipeline.run(season_id, league_id=league_id)

    # ── 2. Create next season directly in DB ──────────────────────────────────
    existing_next = conn.execute(
        """SELECT ls.season_id FROM league_seasons ls
           JOIN seasons s ON s.id = ls.season_id
           WHERE ls.league_id = %s AND s.year = %s""",
        (league_id, next_year),
    ).fetchone()

    if existing_next:
        new_season_id = existing_next["season_id"]
        team_ids = [
            r["team_id"]
            for r in conn.execute(
                "SELECT team_id FROM league_season_teams WHERE league_id = %s AND season_id = %s",
                (league_id, new_season_id),
            ).fetchall()
        ]
        print(f"  Season {next_year} already exists: {new_season_id}")
    else:
        new_season_id, team_ids = _create_next_season(
            conn, league_id, season_id, next_year
        )
        print(f"  Created season {next_year}: {new_season_id} ({len(team_ids)} teams)")

    # ── 3. Generate schedule ──────────────────────────────────────────────────
    existing_games = conn.execute(
        "SELECT COUNT(*) FROM games WHERE season_id = %s", (new_season_id,)
    ).fetchone()["count"]

    if existing_games == 0:
        start_date = datetime.date(next_year, 4, 1)
        scheduler = ScheduleGenerator(rng=rng)
        schedule = scheduler.create_schedule(
            season_id=new_season_id,
            team_ids=team_ids,
            start_date=start_date,
            games_per_matchup=3,
            home_and_away=True,
        )
        save_schedule_to_db(conn, schedule)
        game_count = len(schedule)
        print(f"  Schedule generated: {game_count} games")
    else:
        game_count = existing_games
        print(f"  Schedule already exists: {game_count} games")

    # ── 4. Create draft record ────────────────────────────────────────────────
    existing_draft = conn.execute(
        "SELECT id FROM drafts WHERE league_id = %s AND season_id = %s",
        (league_id, new_season_id),
    ).fetchone()

    if not existing_draft:
        draft_id = str(uuid.uuid4())
        draft_format = "preference" if league_mode == "blitz" else "interactive"
        conn.execute(
            "INSERT INTO drafts (id, league_id, season_id, format, state) VALUES (%s, %s, %s, %s, 'pending')",
            (draft_id, league_id, new_season_id, draft_format),
        )
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
        draft_id = existing_draft["id"]

    # ── 5. Transition league state → draft ────────────────────────────────────
    conn.execute("UPDATE leagues SET state = 'draft' WHERE id = %s", (league_id,))
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
