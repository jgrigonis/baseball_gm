# src/api/services/draft_execute.py
#
# Blitz preference-list draft. Subclasses SnakeDraft and overrides
# _run_snake so that human GMs pick from their submitted preference
# list first, falling back to best prospect rating when the list is
# exhausted or missing (same as AI GMs).

from __future__ import annotations

import sqlite3
from datetime import datetime, UTC

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

    def __init__(self, conn, gm_preferences: dict[str, list[str]], **kwargs):
        """
        Args:
            conn: DB connection
            gm_preferences: { team_id: [player_id, ...] } in rank order.
                            Only human GMs will have entries; AI GMs won't.
        """
        super().__init__(conn, **kwargs)
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

                self.conn.execute(
                    "INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)",
                    (team_id, chosen.id),
                )
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
            player_ids = self.conn.execute(
                "SELECT player_id FROM team_players WHERE team_id = ?",
                (team_id,),
            ).fetchall()
            players = []
            for row in player_ids:
                p = self.player_repo.look_up(row["player_id"])
                if p:
                    players.append(p)
            if not players:
                continue
            assignments = assigner.assign(players)
            self.status_repo.bulk_set(assignments)

        print(f"  Reassigned rosters for {len(ai_teams)} AI teams")


def execute_blitz_draft(draft_id: str, conn: sqlite3.Connection) -> dict:
    """
    Run the full blitz preference-list draft end-to-end.
    Assumes DraftGenerator has already been run (prospect pool exists).
    """
    draft = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()

    if not draft:
        raise ValueError(f"Draft {draft_id} not found.")
    if draft["state"] != "pending":
        raise ValueError(f"Draft is already in state '{draft['state']}'.")
    if draft["format"] != "preference":
        raise ValueError("execute_blitz_draft only handles preference-format drafts.")

    league_id = draft["league_id"]
    season_id = draft["season_id"]

    conn.execute("UPDATE drafts SET state = 'open' WHERE id = ?", (draft_id,))
    conn.commit()

    # Load all human GM team IDs first
    human_team_ids = {
        row["team_id"]
        for row in conn.execute(
            "SELECT team_id FROM gms WHERE league_id = ? AND is_ai = 0 AND team_id IS NOT NULL",
            (league_id,),
        ).fetchall()
    }
    # Load preference lists keyed by team_id (human GMs only)
    pref_rows = conn.execute(
        """
        SELECT g.team_id, dp.player_id, dp.rank
        FROM draft_preferences dp
        JOIN gms g ON g.id = dp.gm_id
        WHERE dp.draft_id = ?
          AND g.league_id = ?
          AND g.is_ai = 0
          AND g.team_id IS NOT NULL
        ORDER BY g.team_id, dp.rank
        """,
        (draft_id, league_id),
    ).fetchall()

    gm_preferences: dict[str, list[str]] = {tid: [] for tid in human_team_ids}
    for row in pref_rows:
        gm_preferences.setdefault(row["team_id"], []).append(row["player_id"])

    year = _season_year(conn, season_id)

    # _build_draft_order needs the PREVIOUS completed season for standings.
    # The draft's season_id is the new (empty) season — find the last one with games.
    prior_season_row = conn.execute(
        """SELECT s.id FROM seasons s
           JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = ?
             AND EXISTS (
               SELECT 1 FROM games g
               WHERE g.season_id = s.id AND g.completed = 1
             )
           ORDER BY s.year DESC LIMIT 1""",
        (league_id,),
    ).fetchone()
    standings_season_id = prior_season_row["id"] if prior_season_row else season_id
    if standings_season_id == season_id:
        print("  WARNING: no prior completed season found for draft ordering — order will be arbitrary")

    blitz = BlitzDraft(conn, gm_preferences=gm_preferences)
    picks = blitz.run_snake_draft(season_id=standings_season_id, year=year, league_id=league_id)

    # Record into draft_picks table
    now = datetime.now(UTC).isoformat()
    for pick in picks:
        gm_id = _gm_for_team(conn, league_id, pick.team_id)
        auto = 1 if pick.team_id not in gm_preferences else 0
        conn.execute(
            """
            INSERT OR IGNORE INTO draft_picks
                (draft_id, pick_number, round, gm_id, team_id, player_id, auto_picked, picked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft_id,
                pick.pick,
                pick.round,
                gm_id,
                pick.team_id,
                pick.player_id,
                auto,
                now,
            ),
        )

    conn.execute(
        "UPDATE drafts SET state = 'complete', current_pick = ? WHERE id = ?",
        (len(picks) + 1, draft_id),
    )
    conn.execute("UPDATE leagues SET state = 'preseason' WHERE id = ?", (league_id,))
    conn.commit()

    return {
        "draft_id": draft_id,
        "season_id": season_id,
        "picks_made": len(picks),
        "auto_picks": sum(1 for p in picks if p.team_id not in gm_preferences),
        "rounds": ROUNDS,
        "league_state": "preseason",
    }


def _season_year(conn: sqlite3.Connection, season_id: str) -> int:
    row = conn.execute("SELECT year FROM seasons WHERE id = ?", (season_id,)).fetchone()
    return row["year"] if row else 2025


def _gm_for_team(conn: sqlite3.Connection, league_id: str, team_id: str) -> str | None:
    row = conn.execute(
        "SELECT id FROM gms WHERE league_id = ? AND team_id = ?",
        (league_id, team_id),
    ).fetchone()
    return row["id"] if row else None
