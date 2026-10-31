# src/api/services/league_start.py

from __future__ import annotations

import datetime
import random

from src.api.services import lobby_teams, personas
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.pitcher_state import PitcherStateRepository
from src.db.repositories.player_energy import PlayerEnergyRepository
from src.league import divisions
from src.league.backstory.service import create_backstory
from src.league.bootstrap import LeagueBootstrapper
from src.league.league_constants import (
    ALL_STAR_BREAK_AFTER_GAMES,
    ALL_STAR_BREAK_DAYS,
    LEAGUE_START_YEAR,
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
from src.league.offseason.snake_draft import SnakeDraft, write_draft_order
from src.league.schedule import ScheduleGenerator, save_schedule_to_db


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
    manifest_path = lobby_teams.manifest_path()
    if not manifest_path.exists():
        raise ValueError(f"Manifest not found at {manifest_path.resolve()}")
    manifest = load_manifest(manifest_path)
    validate_manifest_structure(manifest)
    validate_manifest_uniqueness(manifest)

    # The manifest is only the team list: every new league starts in
    # LEAGUE_START_YEAR, whatever year the file was written for.
    # The league plays with num_teams of its teams (lobby_teams.team_entries).
    year = LEAGUE_START_YEAR
    manifest = {
        **manifest,
        "season_year": year,
        "teams": lobby_teams.team_entries(league_id, league["num_teams"]),
    }

    # ── 2. Generate fresh CSVs for every team ─────────────────────────────────
    create_team_files(manifest["teams"], year, rng=rng, league_id=league_id)

    # ── 3. Bootstrap teams + season ───────────────────────────────────────────
    start_date_str = manifest.get("season_start_date", f"{year}-04-01")
    start_date = datetime.date.fromisoformat(start_date_str).replace(year=year)

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

    # ── 3b'. Leagues and divisions ──────────────────────────────────────────
    # Their own random stream, like the backstory's.
    divisions.save(
        conn,
        league_id,
        divisions.draw(
            [(t.id, t.city) for t in teams], random.Random(f"{seed}-divisions")
        ),
    )

    # ── 3c. Backstory: past seasons generated from the rosters ────────────────
    # Its own random stream, so the rest of the league comes out the same
    # for a seed whatever the backstory length.
    backstory = create_backstory(
        conn,
        league_id,
        season_id,
        league.get("backstory_years") or 0,
        random.Random(f"{seed}-backstory"),
    )

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
            leagues=divisions.schedule_leagues(conn, league_id),
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

    # Each GM dealt a team in the lobby gets it; anyone without one gets an
    # open team, in the shuffled order.
    lobby_picks = lobby_teams.claims(conn, league_id, team_ids_all)
    picked = set(lobby_picks.values())
    open_teams = [tid for tid in team_ids_all if tid not in picked]

    def team_for(gm_id: str) -> str | None:
        if gm_id in lobby_picks:
            return lobby_picks[gm_id]
        return open_teams.pop(0) if open_teams else None

    # 5a. The people who joined
    for gm in human_gms:
        team_id = team_for(gm["id"])
        if team_id:
            gm_repo.assign_team_to_gm(team_id, gm["id"])

    # 5b. The AI GMs picked in the lobby take the rest, in the order they
    # came in. Leagues whose lobby is short of them (e.g. made before the
    # lobby listed them) get new ones, each a persona from the library with
    # its own random stream, so the rest of the league comes out the same
    # for a seed.
    waiting = personas.lobby_ai_gms(conn, league_id)
    persona_rng = random.Random(f"{seed}-personas")
    for ai_gm in waiting:
        team_id = team_for(ai_gm["id"])
        if team_id:
            gm_repo.assign_team_to_gm(team_id, ai_gm["id"])
        else:
            gm_repo.delete_gm(ai_gm["id"])
    for team_id in open_teams:
        ai_gm_id = gm_repo.create_gm(
            league_id=league_id,
            team_id=team_id,
            display_name=personas.FALLBACK_NAME,
            is_ai=True,
        )
        personas.give_persona(conn, league_id, ai_gm_id, persona_rng)
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

    # The first draft goes worst to best by last season's backstory record,
    # as every later draft does. With no backstory it's a shuffle, separate
    # from the GM assignment's.
    draft_order_ids = team_ids_all[:]
    rng.shuffle(draft_order_ids)
    if backstory.last_season_id:
        order = SnakeDraft(conn, league_id, rng)._build_draft_order(
            backstory.last_season_id
        )
        draft_order_ids = [e["team_id"] for e in order]
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
