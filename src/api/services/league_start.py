# src/api/services/league_start.py

from __future__ import annotations

import datetime
import random
from pathlib import Path

from src.api.services import personas
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.pitcher_state import PitcherStateRepository
from src.db.repositories.player_energy import PlayerEnergyRepository
from src.league.bootstrap import LeagueBootstrapper
from src.league.league_constants import (
    ALL_STAR_BREAK_AFTER_GAMES,
    ALL_STAR_BREAK_DAYS,
    SEASON_LENGTH,
)
from src.league.league_modes import is_blitz_style
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
    ir = InjuryRepository(conn, league_id)
    ir.clear_all_injuries()
    per = PlayerEnergyRepository(conn, league_id)
    per.clear_season()
    ps = PitcherStateRepository(conn, league_id)
    ps.clear_all_pitcher_state()

    # ── 4. Generate schedule ──────────────────────────────────────────────────
    gr = GameRepository(conn)
    existing_games = gr.games_remaining(season_id)

    if existing_games == 0:
        scheduler = scheduler or ScheduleGenerator(rng=rng)
        schedule = scheduler.create_schedule(
            season_id=season_id,
            team_ids=[t.id for t in teams],
            start_date=start_date,
            target_games=SEASON_LENGTH,
            all_star_break_after=ALL_STAR_BREAK_AFTER_GAMES,
            all_star_break_days=ALL_STAR_BREAK_DAYS,
        )
        save_schedule_to_db(conn, schedule)
        game_count = len(schedule)
    else:
        game_count = existing_games

    # ── 5. Fill AI GMs + assign all GMs to teams ─────────────────────────────
    gm_repo = GMRepository(conn)
    human_gms = gm_repo.get_human_gm_ids(league_id)

    team_ids_all = [t.id for t in teams]
    rng.shuffle(team_ids_all)

    # 5a. Prepare Batch Update for Human GMs
    assigned_teams = set()

    for gm, team_id in zip(human_gms, team_ids_all):
        gm_repo.assign_team_to_gm(team_id, gm["id"])
        assigned_teams.add(team_id)

    # 5b. The AI GMs picked in the lobby take the rest, in the order they
    # came in. Leagues whose lobby is short of them (e.g. made before the
    # lobby listed them) get new ones, each a persona from the library with
    # its own random stream, so the rest of the league comes out the same
    # for a seed.
    remaining_teams = [tid for tid in team_ids_all if tid not in assigned_teams]
    waiting = personas.lobby_ai_gms(conn, league_id)
    persona_rng = random.Random(f"{seed}-personas")
    for team_id, ai_gm in zip(remaining_teams, waiting):
        gm_repo.assign_team_to_gm(team_id, ai_gm["id"])
    for team_id in remaining_teams[len(waiting) :]:
        ai_gm_id = gm_repo.create_gm(
            league_id=league_id,
            team_id=team_id,
            display_name=personas.FALLBACK_NAME,
            is_ai=True,
        )
        personas.give_persona(conn, league_id, ai_gm_id, persona_rng)
    for ai_gm in waiting[len(remaining_teams) :]:
        gm_repo.delete_gm(ai_gm["id"])
    human_gm_team = gm_repo.get_human_gm_city_mascot(league_id)

    # ── 6. Generate prospect pool ─────────────────────────────────────────────
    # Only delete prospects that belong to THIS league — don't touch other leagues.
    dr = DraftRepository(conn)
    prospect_count = draft_gen or DraftGenerator(conn, rng=rng).run(
        year=year, league_id=league_id
    )

    # ── 7. Create draft ───────────────────────────────────────────────────────
    if is_blitz_style(league["mode"]):
        draft_format = "preference"
    else:
        draft_format = "interactive"
    draft_id = dr.create_draft(league_id, season_id, draft_format)

    # Write draft order using a separate shuffle from GM assignment
    draft_order_ids = team_ids_all[:]
    rng.shuffle(draft_order_ids)
    write_draft_order(conn, draft_id, league_id, year, draft_order_ids)

    # ── 8. Advance league state → draft ──────────────────────────────────────
    lr.set_state(league_id, "draft")

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
