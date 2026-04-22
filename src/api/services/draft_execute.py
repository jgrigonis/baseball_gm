# src/api/services/draft_execute.py
#
# Blitz preference-list draft. Subclasses SnakeDraft and overrides
# _run_snake so that human GMs pick from their submitted preference
# list first, falling back to best prospect rating when the list is
# exhausted or missing (same as AI GMs).

from __future__ import annotations

import random
from datetime import datetime, UTC

from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.offseason_repo import OffseasonRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.league.offseason.offseason_pipeline import OffseasonPipeline
from src.league.offseason.snake_draft import SnakeDraft, DraftPick, ROUNDS
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_record import PlayerRecord
from src.team.roster_assigner import RosterAssigner


class BlitzDraft(SnakeDraft):
    """
    Snake draft variant for blitz leagues.

    Human GMs pick their highest available preference-list player.
    AI GMs (and human GMs with exhausted/missing lists) fall back to
    best prospect rating — identical to the base SnakeDraft behaviour.
    """

    def __init__(
        self, conn, league_id: str, gm_preferences: dict[str, list[str]], rng=None
    ):
        """
        Args:
            conn: DB connection
            league_id: League to scope the draft pool to
            gm_preferences: { team_id: [player_id, ...] } in rank order.
                            Only human GMs will have entries; AI GMs won't.
        """
        super().__init__(conn, league_id, rng)
        self._prefs: dict[str, list[str]] = {
            tid: list(pids) for tid, pids in gm_preferences.items()
        }

    def _run_snake(
        self,
        draft_order: list[dict],
        rated: list[tuple[PlayerRecord, int]],
    ) -> list[DraftPick]:
        """Override: respect preference lists for human GMs."""
        picks = []
        overall_pick = 1
        available: set[str] = {p.id for p, _ in rated}
        fallback: list[tuple[PlayerRecord, int]] = list(rated)

        for round_num in range(1, ROUNDS + 1):
            order = draft_order if round_num % 2 == 1 else list(reversed(draft_order))

            for team_entry in order:
                if not available:
                    print(f"  Draft pool exhausted at pick {overall_pick}")
                    return picks

                team_id = team_entry["team_id"]

                chosen: PlayerRecord | None = None
                # is_auto = True

                pref_list = self._prefs.get(team_id, [])
                for pid in pref_list:
                    if pid in available:
                        record = next((p for p, _ in fallback if p.id == pid), None)
                        if record:
                            chosen = record
                            pref_list.remove(pid)
                            # is_auto = False
                            break

                if chosen is None:
                    for player, _ in fallback:
                        if player.id in available:
                            chosen = player
                            break

                if chosen is None:
                    break

                available.discard(chosen.id)
                rating = PlayerEvaluator.prospect_rating(chosen.skills)
                tr = TeamRepository(self.conn)
                tr.add_player(team_id, chosen.id)
                self.status_repo.set_status(chosen.id, "minors")

                picks.append(
                    DraftPick(
                        round=round_num,
                        pick=overall_pick,
                        team_id=team_id,
                        team_name=team_entry["team_name"],
                        player_id=chosen.id,
                        player_name=chosen.name,
                        age=chosen.age,
                        position=chosen.position,
                        prospect_rating=rating,
                    )
                )

                overall_pick += 1

        self.conn.commit()
        return picks

    def _reassign_rosters(self, draft_order: list[dict]) -> None:
        """Only reassign AI-managed teams — human GMs set their own roster."""
        assigner = RosterAssigner()
        ai_teams = [t for t in draft_order if t["team_id"] not in self._prefs]

        for team_entry in ai_teams:
            team_id = team_entry["team_id"]
            player_ids = self.player_repo.get_player_ids_from_team_players(team_id)
            players = []
            for pid in player_ids:
                p = self.player_repo.look_up(pid)
                if p:
                    players.append(p)
            if not players:
                continue
            assignments = assigner.assign(players)
            self.status_repo.bulk_set(assignments)

        print(f"  Reassigned rosters for {len(ai_teams)} AI teams")


def execute_blitz_draft(draft_id: str, conn) -> dict:
    """
    Run the full blitz preference-list draft end-to-end.
    Assumes DraftGenerator has already been run (prospect pool exists).
    """
    dr = DraftRepository(conn)
    draft = dr.get_draft(draft_id)

    if not draft:
        raise ValueError(f"Draft {draft_id} not found.")
    if draft["state"] != "pending":
        raise ValueError(f"Draft is already in state '{draft['state']}'.")
    if draft["format"] != "preference":
        raise ValueError("execute_blitz_draft only handles preference-format drafts.")

    league_id = draft["league_id"]
    season_id = draft["season_id"]

    dr.set_draft_state(draft_id, "open")

    # Load all human GM team IDs first
    gm_repo = GMRepository(conn)
    human_team_ids = gm_repo.get_human_team_ids(league_id)

    # Load preference lists keyed by team_id (human GMs only)
    pref_rows = dr.get_ids_and_rank_from_preferences(draft_id, league_id)

    gm_preferences: dict[str, list[str]] = {tid: [] for tid in human_team_ids}
    for row in pref_rows:
        gm_preferences.setdefault(row["team_id"], []).append(row["player_id"])

    sr = SeasonRepository(conn)
    row = sr.get_year(season_id)
    year = row["year"] if row else 2025

    # Read the pre-stored draft order from draft_order table (written by
    # league_start or offseason_pipeline — never recompute from standings here)
    stored_order = dr.get_team_id_draft_order(draft_id)

    blitz = BlitzDraft(conn, league_id=league_id, gm_preferences=gm_preferences)

    if stored_order:
        draft_order = [{"team_id": r["team_id"], "team_name": ""} for r in stored_order]
        picks = blitz.run_snake_draft_with_order(draft_order, year, league_id)
    else:
        raise RuntimeError(f"No stored order found")

    # Record into draft_picks table
    now = datetime.now(UTC).isoformat()
    for pick in picks:
        gm_id = gm_repo.get_gm_id_from_team_id(league_id, pick.team_id)
        # gm_id = _gm_for_team(conn, league_id, pick.team_id)
        auto = pick.team_id not in gm_preferences
        dr.insert_draft_picks(
            draft_id,
            pick.pick,
            pick.round,
            gm_id,
            pick.team_id,
            pick.player_id,
            auto,
            now,
        )

    dr.set_complete_current_pick(draft_id, len(picks) + 1)
    lr = LeagueRepository(conn)
    lr.set_state(league_id, "preseason")

    # Run post-draft pipeline steps (trim rosters, rotations, energy, stats, csvs).
    # These were deferred so they run against the final rosters including draft picks.
    osr = OffseasonRepository(conn)
    prev_season_id = osr.find_season_with_offseason_steps(league_id, season_id)
    # prev_season_id = _prev_season_id(conn, league_id, season_id)
    if prev_season_id:
        print(f"Running post-draft pipeline steps for season {prev_season_id}...")
        pipeline = OffseasonPipeline(conn, random.Random())
        pipeline.run(prev_season_id, league_id=league_id, skip_auto_draft=True)

    return {
        "draft_id": draft_id,
        "season_id": season_id,
        "picks_made": len(picks),
        "auto_picks": sum(1 for p in picks if p.team_id not in gm_preferences),
        "rounds": ROUNDS,
        "league_state": "preseason",
    }
