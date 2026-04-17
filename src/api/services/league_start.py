# src/api/services/league_start.py

from __future__ import annotations

import datetime
import random
import uuid
from pathlib import Path

from src.db.repositories.league_repo import LeagueRepository
from src.league.bootstrap import LeagueBootstrapper
from src.league.manifest_helper import (
    create_team_files,
    load_manifest,
    validate_manifest_structure,
    validate_manifest_uniqueness,
)
from src.league.offseason.draft_generator import DraftGenerator
from src.league.offseason.snake_draft import write_draft_order
from src.league.schedule import ScheduleGenerator, save_schedule_to_db
from src.util.locations import MANIFEST_FILES_DIR

_MANIFEST_FILENAME = "world_league-2025.json"


def start_league(
    league_id: str,
    conn,
    bootstrapper=None,
    draft_gen=None,
    scheduler=None,
) -> dict:
    lr = LeagueRepository(conn)
    league = lr.get_by_id(league_id)

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

    year = manifest.get("season_year", 2025)

    # ── 2. Generate fresh CSVs for every team ─────────────────────────────────
    create_team_files(manifest["teams"], year, rng=rng, league_id=league_id)

    # ── 3. Bootstrap teams + season ───────────────────────────────────────────
    start_date_str = manifest.get("season_start_date", f"{year}-04-01")
    start_date = datetime.date.fromisoformat(start_date_str)

    bootstrapper = bootstrapper or LeagueBootstrapper(conn, rng=rng)

    _, teams, season_id = bootstrapper.bootstrap_from_manifest(
        manifest,
        start_date,
        allow_roster_update=True,
        league_id=league_id,
        force_new_teams=True,
    )

    # ── 3b. Clear stale injury/energy state for this league ─────────────────
    # Player IDs are deterministic (CSV hashes) and reused across leagues.
    # Delete only rows scoped to THIS league_id so other leagues are unaffected.
    conn.execute(
        "DELETE FROM player_injuries WHERE league_id = %s",
        (league_id,),
    )
    conn.execute(
        "DELETE FROM player_energy WHERE league_id = %s",
        (league_id,),
    )
    conn.execute(
        "DELETE FROM pitcher_state WHERE league_id = %s",
        (league_id,),
    )
    # conn.commit()

    # ── 4. Generate schedule ──────────────────────────────────────────────────
    existing_games = conn.execute(
        "SELECT COUNT(*) as count FROM games WHERE season_id = %s", (season_id,)
    ).fetchone()["count"]

    if existing_games == 0:
        scheduler = scheduler or ScheduleGenerator(rng=rng)
        schedule = scheduler.create_schedule(
            season_id=season_id,
            team_ids=[t.id for t in teams],
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
        "SELECT id FROM gms WHERE league_id = %s AND NOT is_ai ORDER BY created_at",
        (league_id,),
    ).fetchall()

    team_ids_all = [t.id for t in teams]
    rng.shuffle(team_ids_all)

    # 5a. Prepare Batch Update for Human GMs
    human_updates = []
    assigned_teams = set()

    for gm, team_id in zip(human_gms, team_ids_all):
        human_updates.append((team_id, gm["id"]))
        # conn.execute("UPDATE gms SET team_id = %s WHERE id = %s", (team_id, gm["id"]))
        assigned_teams.add(team_id)

    if human_updates:
        conn.cursor().executemany(
            "UPDATE gms SET team_id = %s WHERE id = %s", human_updates
        )

    # 5b. Prepare Batch Insert for AI GMs
    ai_inserts = []
    profile_inserts = []

    remaining_teams = [tid for tid in team_ids_all if tid not in assigned_teams]

    for team_id in remaining_teams:
        ai_gm_id = str(uuid.uuid4())
        ai_inserts.append((ai_gm_id, league_id, team_id))
        profile_inserts.append((ai_gm_id,))

    if ai_inserts:
        cur = conn.cursor()
        # Insert the AI GMs
        cur.executemany(
            "INSERT INTO gms (id, league_id, team_id, display_name, is_ai) VALUES (%s, %s, %s, 'AI Manager', TRUE)",
            ai_inserts,
        )
        # Insert the matching Profiles
        cur.executemany("INSERT INTO gm_profiles (gm_id) VALUES (%s)", profile_inserts)

    # 5c. Get the human gm team
    human_gm_team = conn.execute(
        """
        SELECT t.city, t.mascot FROM gms g
        JOIN teams t ON t.id = g.team_id
        WHERE g.league_id = %s AND NOT g.is_ai
        LIMIT 1
        """,
        (league_id,),
    ).fetchone()

    # ── 6. Generate prospect pool ─────────────────────────────────────────────
    # Only delete prospects that belong to THIS league — don't touch other leagues.
    conn.execute(
        """
        DELETE FROM players WHERE id IN (
            SELECT p.id FROM players p
            JOIN player_status ps ON ps.player_id = p.id
            LEFT JOIN team_players tp ON tp.player_id = p.id
            WHERE ps.status = 'prospect'
              AND tp.player_id IS NULL
              AND p.league_id = %s
        )
    """,
        (league_id,),
    )
    # conn.commit()

    prospect_count = draft_gen or DraftGenerator(conn, rng=rng).run(
        season_id=season_id, year=year, league_id=league_id
    )

    # ── 7. Create draft ───────────────────────────────────────────────────────
    draft_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO drafts (id, league_id, season_id, format, state) VALUES (%s, %s, %s, %s, 'pending')",
        (
            draft_id,
            league_id,
            season_id,
            "preference" if league["mode"] == "blitz" else "interactive",
        ),
    )

    # Write draft order using a separate shuffle from GM assignment
    draft_order_ids = team_ids_all[:]
    rng.shuffle(draft_order_ids)
    write_draft_order(conn, draft_id, league_id, year, draft_order_ids)

    # ── 8. Advance league state → draft ──────────────────────────────────────
    conn.execute("UPDATE leagues SET state = 'draft' WHERE id = %s", (league_id,))
    # conn.commit()

    return {
        "league_id": league_id,
        "season_id": season_id,
        "draft_id": draft_id,
        "team_count": len(teams),
        "game_count": game_count,
        "prospect_count": prospect_count,
        "seed": seed,
        "your_team": (
            f"{human_gm_team['city']} {human_gm_team['mascot']}"
            if human_gm_team
            else None
        ),
    }
