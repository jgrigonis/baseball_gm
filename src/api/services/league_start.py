# src/api/services/league_start.py
#
# Orchestrates everything that happens when a commissioner fires
# POST /leagues/{league_id}/start:
#
#   1. Load the fixed manifest
#   2. Generate fresh player CSVs for all teams
#   3. Bootstrap teams + season via LeagueBootstrapper
#   4. Generate the game schedule
#   5. Fill empty slots with AI GMs and assign all GMs to teams
#   6. Create the draft record
#   7. Advance league state → 'draft'

from __future__ import annotations

import datetime
import random
import sqlite3
import uuid
from pathlib import Path

from src.league.bootstrap import LeagueBootstrapper
from src.league.manifest_helper import (
    create_team_files,
    load_manifest,
    validate_manifest_structure,
    validate_manifest_uniqueness,
)
from src.league.offseason.draft_generator import DraftGenerator
from src.league.schedule import ScheduleGenerator, save_schedule_to_db
from src.util.locations import MANIFEST_FILES_DIR

_MANIFEST_FILENAME = "world_league-2025.json"


def start_league(league_id: str, conn: sqlite3.Connection) -> dict:
    """
    Run the full pre-game setup for a league. Idempotent on repeated calls
    only if the league is still in 'lobby' state.

    Returns a summary dict with season_id, team_count, game_count, draft_id.
    """
    league = conn.execute("SELECT * FROM leagues WHERE id = ?", (league_id,)).fetchone()

    if not league:
        raise ValueError(f"League {league_id} not found.")
    if league["state"] != "lobby":
        raise ValueError(
            f"League is already in state '{league['state']}', cannot start."
        )

    seed = random.randint(0, 999_999)
    rng = random.Random(seed)

    # ── 1. Load manifest ──────────────────────────────────────────────────────
    manifest_path = Path(MANIFEST_FILES_DIR) / _MANIFEST_FILENAME
    if not manifest_path.exists():
        raise ValueError(f"Manifest not found at {manifest_path.resolve()}")
    manifest = load_manifest(manifest_path)
    validate_manifest_structure(manifest)
    validate_manifest_uniqueness(manifest)

    # Stamp the league name from the manifest onto the leagues row so it's
    # consistent, but keep whatever name the GM chose if they set one.
    # (No-op if the league already has a real name.)

    # ── 2. Generate fresh CSVs for every team ─────────────────────────────────
    # Always regenerate — each new league gets a fresh random roster.
    year = manifest.get("season_year", 2025)
    create_team_files(manifest["teams"], year, rng=rng)

    # ── 3. Bootstrap teams + season ───────────────────────────────────────────
    start_date_str = manifest.get("season_start_date", f"{year}-04-01")
    start_date = datetime.date.fromisoformat(start_date_str)

    bootstrapper = LeagueBootstrapper(conn, rng=rng)

    # Override the manifest's league_name with the one chosen at league-create
    # time so the season links to the right leagues row.
    patched_manifest = {**manifest, "league_name": league["name"]}

    league_db_id, teams, season_id = bootstrapper.bootstrap_from_manifest(
        patched_manifest, start_date, allow_roster_update=True
    )

    # bootstrap_from_manifest creates its own leagues row via LeagueRepository;
    # we need to make sure it reuses *our* league_id rather than creating a
    # duplicate. See note below — we patch the repo call via the existing
    # league row instead.
    #
    # If LeagueRepository.create_league is idempotent on name (i.e. returns
    # an existing id for a duplicate name), league_db_id may differ from
    # league_id. We reconcile by re-pointing season → our league.
    if league_db_id != league_id:
        # Ensure our league_id owns the season
        existing = conn.execute(
            "SELECT 1 FROM league_seasons WHERE league_id = ? AND season_id = ?",
            (league_id, season_id),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO league_seasons (league_id, season_id) VALUES (?, ?)",
                (league_id, season_id),
            )

    # ── 4. Generate schedule ──────────────────────────────────────────────────
    existing_games = conn.execute(
        "SELECT COUNT(*) FROM games WHERE season_id = ?", (season_id,)
    ).fetchone()[0]

    if existing_games == 0:
        team_ids = [t.id for t in teams]
        scheduler = ScheduleGenerator(rng=rng)
        schedule = scheduler.create_schedule(
            season_id=season_id,
            team_ids=team_ids,
            start_date=start_date,
            games_per_matchup=3,
            home_and_away=True,
        )
        save_schedule_to_db(conn, schedule)
        game_count = len(schedule)
    else:
        game_count = existing_games

    # ── 5. Fill AI GMs + assign all GMs to teams ─────────────────────────────
    human_gms = conn.execute(
        "SELECT * FROM gms WHERE league_id = ? AND is_ai = 0 ORDER BY created_at",
        (league_id,),
    ).fetchall()

    team_ids_all = [t.id for t in teams]
    rng.shuffle(team_ids_all)  # randomise human team assignments

    # Assign human GMs to teams first
    assigned_teams = set()
    for gm, team_id in zip(human_gms, team_ids_all):
        conn.execute("UPDATE gms SET team_id = ? WHERE id = ?", (team_id, gm["id"]))
        assigned_teams.add(team_id)

    # Fill remaining slots with AI GMs
    ai_team_ids = [tid for tid in team_ids_all if tid not in assigned_teams]
    for team_id in ai_team_ids:
        ai_gm_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO gms (id, league_id, team_id, display_name, is_ai)
            VALUES (?, ?, ?, 'AI Manager', 1)
            """,
            (ai_gm_id, league_id, team_id),
        )
        conn.execute("INSERT INTO gm_profiles (gm_id) VALUES (?)", (ai_gm_id,))

    # ── 6. Generate prospect pool ────────────────────────────────────────────

    # Clear any leftover prospects from previous league attempts
    conn.execute("""
        DELETE FROM players WHERE id IN (
            SELECT p.id FROM players p
            JOIN player_status ps ON ps.player_id = p.id
            LEFT JOIN team_players tp ON tp.player_id = p.id
            WHERE ps.status = 'prospect'
            AND tp.player_id IS NULL
        )
        """)
    conn.commit()

    generator = DraftGenerator(conn, rng=rng)
    prospect_count = generator.run(season_id=season_id, year=year)

    # ── 7. Create draft ───────────────────────────────────────────────────────
    draft_id = str(uuid.uuid4())
    draft_format = "preference" if league["mode"] == "blitz" else "interactive"
    conn.execute(
        """
        INSERT INTO drafts (id, league_id, season_id, format, state)
        VALUES (?, ?, ?, ?, 'pending')
        """,
        (draft_id, league_id, season_id, draft_format),
    )

    # ── 8. Advance league state → draft ───────────────────────────────────────
    conn.execute("UPDATE leagues SET state = 'draft' WHERE id = ?", (league_id,))

    conn.commit()

    return {
        "league_id": league_id,
        "season_id": season_id,
        "draft_id": draft_id,
        "team_count": len(teams),
        "game_count": game_count,
        "prospect_count": prospect_count,
        "seed": seed,
    }
