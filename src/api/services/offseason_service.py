# src/api/services/offseason_service.py
"""
Runs the full offseason pipeline for a league, then bootstraps the next season
so the league transitions back to 'draft' state ready for year 2+.

Steps:
  1. OffseasonPipeline.run() — age, retire, generate_draft, AI draft, trim, reset, write_csvs
  2. Load next year's manifest (world_league-{year+1}.json)
  3. LeagueBootstrapper.bootstrap_from_manifest() — creates new season + schedule
  4. Generate new draft record for human GM
  5. Set league state → 'draft'
"""

from __future__ import annotations

import random
import sqlite3
import uuid
from pathlib import Path

from src.league.bootstrap import LeagueBootstrapper
from src.league.manifest_helper import load_manifest, find_missing_team_files, create_team_files
from src.league.offseason.offseason_pipeline import OffseasonPipeline
from src.league.schedule import ScheduleGenerator, save_schedule_to_db
from src.util.locations import MANIFEST_FILES_DIR

_MANIFEST_PREFIX = "world_league"


def _get_season_id(conn, league_id: str) -> str | None:
    row = conn.execute(
        "SELECT season_id FROM league_seasons WHERE league_id = ? ORDER BY rowid DESC LIMIT 1",
        (league_id,),
    ).fetchone()
    return row["season_id"] if row else None


def _get_season_year(conn, season_id: str) -> int:
    row = conn.execute("SELECT year FROM seasons WHERE id = ?", (season_id,)).fetchone()
    return row["year"] if row else 2025


def run_offseason(league_id: str, conn: sqlite3.Connection) -> dict:
    """
    Run the full offseason for a league and return to draft state.
    Idempotent — safe to call multiple times (pipeline skips completed steps).
    """
    league = conn.execute("SELECT * FROM leagues WHERE id = ?", (league_id,)).fetchone()
    if not league:
        raise ValueError(f"League {league_id} not found")
    if league["state"] not in ("offseason",):
        raise ValueError(f"League must be in 'offseason' state, currently '{league['state']}'")

    season_id = _get_season_id(conn, league_id)
    if not season_id:
        raise ValueError("No season found for this league")

    current_year = _get_season_year(conn, season_id)
    next_year = current_year + 1
    league_mode = dict(league).get("mode", "blitz") or "blitz"

    rng = random.Random()

    # ── 1. Run offseason pipeline ─────────────────────────────────────────────
    print(f"Running offseason pipeline for {league_id} (season {season_id})...")
    pipeline = OffseasonPipeline(conn, rng)
    pipeline.run(season_id, league_id=league_id)

    # ── 2. Load next year's manifest ──────────────────────────────────────────
    manifest_path = Path(MANIFEST_FILES_DIR) / f"{_MANIFEST_PREFIX}-{next_year}.json"
    if not manifest_path.exists():
        raise ValueError(f"Next year manifest not found: {manifest_path}")

    manifest = load_manifest(str(manifest_path))

    # ── 3. Generate team CSV files for next year if missing ───────────────────
    missing = find_missing_team_files(manifest, league_id=league_id)
    if missing:
        print(f"  Generating {len(missing)} missing team CSV files for year {next_year}...")
        create_team_files(missing, next_year, rng=rng, league_id=league_id)

    # ── 4. Bootstrap next season ──────────────────────────────────────────────
    import datetime
    start_date_str = manifest.get("season_start_date", f"{next_year}-04-01")
    start_date = datetime.date.fromisoformat(start_date_str)

    bootstrapper = LeagueBootstrapper(conn, rng=rng)
    _, teams, new_season_id = bootstrapper.bootstrap_from_manifest(
        manifest,
        start_date,
        allow_roster_update=True,   # import aged player skills
        league_id=league_id,
        force_new_teams=False,      # reuse existing team records
    )

    # ── 5. Generate schedule ──────────────────────────────────────────────────
    existing_games = conn.execute(
        "SELECT COUNT(*) FROM games WHERE season_id = ?", (new_season_id,)
    ).fetchone()[0]

    if existing_games == 0:
        scheduler = ScheduleGenerator(rng=rng)
        schedule = scheduler.create_schedule(
            season_id=new_season_id,
            team_ids=[t.id for t in teams],
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

    # ── 6. Re-assign human GMs to their same teams in new season ─────────────
    # GMs keep their team_id — teams persist across seasons, nothing to change

    # ── 7. Create draft record ────────────────────────────────────────────────
    existing_draft = conn.execute(
        "SELECT id FROM drafts WHERE league_id = ? AND season_id = ?",
        (league_id, new_season_id),
    ).fetchone()

    if not existing_draft:
        draft_id = str(uuid.uuid4())
        draft_format = "preference" if league_mode == "blitz" else "interactive"
        conn.execute(
            "INSERT INTO drafts (id, league_id, season_id, format, state) VALUES (?, ?, ?, ?, 'pending')",
            (draft_id, league_id, new_season_id, draft_format),
        )
    else:
        draft_id = existing_draft["id"]

    # ── 8. Transition league state → draft ────────────────────────────────────
    conn.execute("UPDATE leagues SET state = 'draft' WHERE id = ?", (league_id,))
    conn.commit()

    print(f"  Offseason complete. League {league_id} → state=draft, season {new_season_id}")

    return {
        "prev_season_id":  season_id,
        "new_season_id":   new_season_id,
        "new_year":        next_year,
        "draft_id":        draft_id,
        "game_count":      game_count,
        "team_count":      len(teams),
    }
