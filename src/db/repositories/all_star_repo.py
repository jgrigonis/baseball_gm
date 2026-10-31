# src/db/repositories/all_star_repo.py
#
# All-Star voting (src/league/all_star.py): who's on the ballot, the ballots
# GMs cast, and the players voted in. The All-Star Game and the Rookie Game
# are run alike, so the game's methods work on either: event="rookie" keeps
# them in the Rookie Game's tables.

from __future__ import annotations

from psycopg.types.json import Jsonb

from src.player.player_evaluator import PlayerEvaluator
from src.player.player_skills import PlayerSkills

_STAT_COLUMNS = (
    "bat_games_played",
    "bat_ab",
    "bat_hits",
    "bat_doubles",
    "bat_triples",
    "bat_home_runs",
    "bat_rbi",
    "bat_walks",
    "bat_hbp",
    "bat_sac_flys",
    "bat_stolen_bases",
    "bat_runs",
    "bat_strike_outs",
    "pitch_games_played",
    "pitch_games_started",
    "pitch_wins",
    "pitch_losses",
    "pitch_hits",
    "pitch_saves",
    "pitch_outs",
    "pitch_earned_runs",
    "pitch_home_runs",
    "pitch_walks",
    "pitch_hit_batters",
    "pitch_strike_outs",
)


# Each event's tables: its players, the game, the draft and the lines.
TABLES = {
    "all_star": (
        "all_stars",
        "all_star_games",
        "all_star_picks",
        "all_star_game_stats",
    ),
    "rookie": (
        "rookie_game_players",
        "rookie_games",
        "rookie_game_picks",
        "rookie_game_stats",
    ),
}


class AllStarRepository:
    def __init__(self, conn, event: str = "all_star"):
        self.conn = conn
        self.players, self.games, self.picks, self.stats = TABLES[event]

    def game_dates(self, season_id: str) -> list[str]:
        """Every regular season game date in a season."""
        rows = self.conn.execute(
            """SELECT DISTINCT game_date FROM games
               WHERE season_id = %s AND series_id IS NULL""",
            (season_id,),
        ).fetchall()
        return [r["game_date"] for r in rows]

    def candidates(self, league_id: str, season_id: str) -> list[dict]:
        """Everyone on a team in the league who has played this regular
        season, with his totals, the team he's on, the position he has
        started at most (lineup slots, not counting pitchers) and how many
        starts that is. The caller decides who has played enough."""
        sums = ", ".join(f"SUM(pss.{c}) AS {c}" for c in _STAT_COLUMNS)
        rows = self.conn.execute(
            f"""WITH cur AS (
                    SELECT tp.player_id, tp.team_id FROM team_players tp
                    JOIN league_season_teams lst
                      ON lst.team_id = tp.team_id
                     AND lst.league_id = %s AND lst.season_id = %s
                ),
                tot AS (
                    SELECT pss.player_id, {sums}
                    FROM player_season_stats pss
                    JOIN cur ON cur.player_id = pss.player_id
                    WHERE pss.season_id = %s AND NOT pss.is_postseason
                    GROUP BY pss.player_id
                ),
                starts AS (
                    SELECT DISTINCT ON (gls.player_id)
                           gls.player_id, gls.position, COUNT(*) AS n
                    FROM game_lineup_slots gls
                    JOIN games g ON g.id = gls.game_id
                    JOIN cur ON cur.player_id = gls.player_id
                    WHERE g.season_id = %s AND g.series_id IS NULL
                      AND gls.batting_order IS NOT NULL
                    GROUP BY gls.player_id, gls.position
                    ORDER BY gls.player_id, COUNT(*) DESC, gls.position
                ),
                all_starts AS (
                    SELECT gls.player_id, COUNT(*) AS n
                    FROM game_lineup_slots gls
                    JOIN games g ON g.id = gls.game_id
                    JOIN cur ON cur.player_id = gls.player_id
                    WHERE g.season_id = %s AND g.series_id IS NULL
                      AND gls.batting_order IS NOT NULL
                    GROUP BY gls.player_id
                )
                SELECT tot.*, cur.team_id, t.city, t.mascot,
                       p.first_name, p.last_name, p.throws,
                       starts.position AS start_position,
                       COALESCE(all_starts.n, 0) AS starts,
                       ps.*
                FROM tot
                JOIN cur ON cur.player_id = tot.player_id
                JOIN teams t ON t.id = cur.team_id
                JOIN players p ON p.id = tot.player_id
                JOIN player_skills ps ON ps.player_id = tot.player_id
                LEFT JOIN starts ON starts.player_id = tot.player_id
                LEFT JOIN all_starts ON all_starts.player_id = tot.player_id""",
            (league_id, season_id, season_id, season_id, season_id),
        ).fetchall()
        out = []
        for r in rows:
            r = dict(r)
            skills = PlayerSkills.from_db_row(r)
            ratings = PlayerEvaluator.rate_player(skills, r["throws"] or "R")
            c = {k: int(r[k] or 0) for k in _STAT_COLUMNS}
            c.update(
                player_id=r["player_id"],
                name=f"{r['first_name']} {r['last_name']}",
                team_id=r["team_id"],
                city=r["city"],
                mascot=r["mascot"],
                age=r["age"],
                speed=skills["speed"],
                power=skills["power"],
                contact=skills["contact"],
                start_position=r["start_position"],
                starts=int(r["starts"]),
                offense=ratings["overall_offense"],
                talent=max(ratings["sp"], ratings["rp"]),
                ratings=ratings,
            )
            out.append(c)
        return out

    # ── Ballots ──────────────────────────────────────────────────────────

    def save_ballot(self, season_id: str, team_id: str, ballot: dict) -> None:
        """Replace a team's ballot ({slot: [player id or None, ...]})."""
        self.conn.execute(
            "DELETE FROM all_star_votes WHERE season_id = %s AND team_id = %s",
            (season_id, team_id),
        )
        for slot, picks in ballot.items():
            for pick, player_id in enumerate(picks, 1):
                if player_id:
                    self.conn.execute(
                        """INSERT INTO all_star_votes
                               (season_id, team_id, slot, pick, player_id)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (season_id, team_id, slot, pick, player_id),
                    )

    def ballots(self, season_id: str) -> dict[str, dict[str, list]]:
        """Every ballot cast this season, {team id: {slot: [player id or
        None, ...]}} with picks in order."""
        rows = self.conn.execute(
            """SELECT team_id, slot, pick, player_id FROM all_star_votes
               WHERE season_id = %s ORDER BY team_id, slot, pick""",
            (season_id,),
        ).fetchall()
        return _group(rows)

    def ballot(self, season_id: str, team_id: str) -> dict[str, list] | None:
        """One team's ballot, or None if it hasn't voted."""
        rows = self.conn.execute(
            """SELECT team_id, slot, pick, player_id FROM all_star_votes
               WHERE season_id = %s AND team_id = %s ORDER BY slot, pick""",
            (season_id, team_id),
        ).fetchall()
        return _group(rows).get(team_id)

    def voted_count(self, season_id: str) -> int:
        row = self.conn.execute(
            """SELECT COUNT(DISTINCT team_id) AS n FROM all_star_votes
               WHERE season_id = %s""",
            (season_id,),
        ).fetchone()
        return row["n"]

    # ── All-Stars ────────────────────────────────────────────────────────

    def save_all_stars(self, season_id: str, rows: list[dict]) -> None:
        for r in rows:
            self.conn.execute(
                f"""INSERT INTO {self.players}
                       (season_id, player_id, team_id, slot, points, wildcard,
                        score, replaces)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (
                    season_id,
                    r["player_id"],
                    r["team_id"],
                    r["slot"],
                    r["points"],
                    r["wildcard"],
                    r.get("score", 0),
                    r.get("replaces"),
                ),
            )

    def has_all_stars(self, season_id: str) -> bool:
        row = self.conn.execute(
            f"SELECT 1 FROM {self.players} WHERE season_id = %s LIMIT 1", (season_id,)
        ).fetchone()
        return row is not None

    def all_stars(self, season_id: str) -> list[dict]:
        """The season's All-Stars with names and teams, most points first
        within each slot, and the side (1 or 2) and pick that took each one
        in the captains' draft (None until then)."""
        rows = self.conn.execute(
            f"""SELECT a.player_id, a.team_id, a.slot, a.points, a.wildcard,
                      a.score, a.replaces, p.first_name || ' ' || p.last_name AS name,
                      t.city, t.mascot, k.side, k.pick
               FROM {self.players} a
               JOIN players p ON p.id = a.player_id
               JOIN teams t ON t.id = a.team_id
               LEFT JOIN {self.picks} k
                 ON k.season_id = a.season_id AND k.player_id = a.player_id
               WHERE a.season_id = %s
               ORDER BY a.wildcard, a.slot, a.points DESC, a.score DESC, name""",
            (season_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def remove_all_star(self, season_id: str, player_id: str) -> None:
        self.conn.execute(
            f"DELETE FROM {self.players} WHERE season_id = %s AND player_id = %s",
            (season_id, player_id),
        )

    # ── The game ─────────────────────────────────────────────────────────

    def create_game(
        self, season_id: str, captain1: str, captain2: str, game_date: str, tied: list
    ) -> None:
        self.conn.execute(
            f"""INSERT INTO {self.games}
                   (season_id, captain1_team_id, captain2_team_id, game_date,
                    state, tied_ids)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING""",
            (
                season_id,
                captain1,
                captain2,
                game_date,
                "tie" if tied else "draft",
                tied,
            ),
        )

    def game(self, season_id: str | None) -> dict | None:
        """The season's All-Star Game, with its captains' team names."""
        if not season_id:
            return None
        row = self.conn.execute(
            f"""SELECT g.*, t1.city AS city1, t1.mascot AS mascot1,
                      t2.city AS city2, t2.mascot AS mascot2
               FROM {self.games} g
               JOIN teams t1 ON t1.id = g.captain1_team_id
               JOIN teams t2 ON t2.id = g.captain2_team_id
               WHERE g.season_id = %s""",
            (season_id,),
        ).fetchone()
        return dict(row) if row else None

    def set_state(self, season_id: str, state: str) -> None:
        self.conn.execute(
            f"UPDATE {self.games} SET state = %s WHERE season_id = %s",
            (state, season_id),
        )

    def set_auto(self, season_id: str, side: int) -> None:
        """The scouts make this side's picks from now on."""
        col = "auto1" if side == 1 else "auto2"
        self.conn.execute(
            f"UPDATE {self.games} SET {col} = TRUE WHERE season_id = %s",
            (season_id,),
        )

    def add_pick(self, season_id: str, player_id: str, side: int, pick: int) -> None:
        self.conn.execute(
            f"""INSERT INTO {self.picks} (season_id, player_id, side, pick)
               VALUES (%s, %s, %s, %s)""",
            (season_id, player_id, side, pick),
        )

    def save_result(
        self,
        season_id: str,
        score1: int,
        score2: int,
        innings: int,
        line_score: dict,
        mvp_player_id: str | None,
    ) -> None:
        self.conn.execute(
            f"""UPDATE {self.games}
               SET state = 'played', score1 = %s, score2 = %s, innings = %s,
                   line_score = %s, mvp_player_id = %s
               WHERE season_id = %s""",
            (score1, score2, innings, Jsonb(line_score), mvp_player_id, season_id),
        )

    def save_lines(self, season_id: str, lines: list[dict]) -> None:
        for line in lines:
            cols = ["season_id", *line]
            self.conn.execute(
                f"""INSERT INTO {self.stats} ({", ".join(cols)})
                    VALUES ({", ".join(["%s"] * len(cols))})""",
                (season_id, *line.values()),
            )

    def lines(self, season_id: str) -> list[dict]:
        """Every player's line in the season's All-Star Game, with names."""
        rows = self.conn.execute(
            f"""SELECT s.*, p.first_name || ' ' || p.last_name AS name
               FROM {self.stats} s
               JOIN players p ON p.id = s.player_id
               WHERE s.season_id = %s
               ORDER BY s.side, s.batting_order NULLS LAST, s.pitch_order""",
            (season_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def career_lines(self, player_id: str) -> list[dict]:
        """A player's All-Star Game lines, by year, oldest first: his side's
        captain's city, the score from his side and whether he was MVP."""
        rows = self.conn.execute(
            f"""SELECT s.*, y.year, g.mvp_player_id = s.player_id AS mvp,
                      t.city AS captain_city,
                      CASE WHEN s.side = 1 THEN g.score1 ELSE g.score2 END AS runs,
                      CASE WHEN s.side = 1 THEN g.score2 ELSE g.score1 END
                          AS runs_against
               FROM {self.stats} s
               JOIN seasons y ON y.id = s.season_id
               JOIN {self.games} g ON g.season_id = s.season_id
               JOIN teams t ON t.id = CASE WHEN s.side = 1
                   THEN g.captain1_team_id ELSE g.captain2_team_id END
               WHERE s.player_id = %s
               ORDER BY y.year""",
            (player_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def ids(self, season_id: str) -> set[str]:
        rows = self.conn.execute(
            f"SELECT player_id FROM {self.players} WHERE season_id = %s", (season_id,)
        ).fetchall()
        return {r["player_id"] for r in rows}

    def seasons_for(self, player_id: str) -> list[dict]:
        """The seasons a player was an All-Star: year and team, oldest first."""
        rows = self.conn.execute(
            f"""SELECT s.year, t.city, t.mascot
               FROM {self.players} a
               JOIN seasons s ON s.id = a.season_id
               JOIN teams t ON t.id = a.team_id
               WHERE a.player_id = %s
               ORDER BY s.year""",
            (player_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def years_by_player(self, player_ids: list[str]) -> dict[str, list[int]]:
        """The years each of these players was an All-Star, oldest first.
        Players never voted in are left out."""
        if not player_ids:
            return {}
        rows = self.conn.execute(
            f"""SELECT a.player_id, s.year
               FROM {self.players} a
               JOIN seasons s ON s.id = a.season_id
               WHERE a.player_id = ANY(%s)
               ORDER BY s.year""",
            (list(player_ids),),
        ).fetchall()
        out: dict[str, list[int]] = {}
        for r in rows:
            out.setdefault(r["player_id"], []).append(r["year"])
        return out


def _group(rows) -> dict[str, dict[str, list]]:
    """Vote rows, in pick order, as {team id: {slot: [player id or None]}}.
    A skipped pick is None."""
    out: dict[str, dict[str, list]] = {}
    for r in rows:
        picks = out.setdefault(r["team_id"], {}).setdefault(r["slot"], [])
        picks.extend([None] * (r["pick"] - 1 - len(picks)))
        picks.append(r["player_id"])
    return out
