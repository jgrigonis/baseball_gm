# src/db/repositories/all_star_repo.py
#
# All-Star voting (src/league/all_star.py): who's on the ballot, the ballots
# GMs cast, and the players voted in.

from __future__ import annotations

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
    "pitch_games_played",
    "pitch_games_started",
    "pitch_wins",
    "pitch_saves",
    "pitch_outs",
    "pitch_earned_runs",
    "pitch_home_runs",
    "pitch_walks",
    "pitch_hit_batters",
    "pitch_strike_outs",
)


class AllStarRepository:
    def __init__(self, conn):
        self.conn = conn

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
                """INSERT INTO all_stars
                       (season_id, player_id, team_id, slot, points, wildcard)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (
                    season_id,
                    r["player_id"],
                    r["team_id"],
                    r["slot"],
                    r["points"],
                    r["wildcard"],
                ),
            )

    def has_all_stars(self, season_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM all_stars WHERE season_id = %s LIMIT 1", (season_id,)
        ).fetchone()
        return row is not None

    def all_stars(self, season_id: str) -> list[dict]:
        """The season's All-Stars with names and teams, most points first
        within each slot."""
        rows = self.conn.execute(
            """SELECT a.player_id, a.team_id, a.slot, a.points, a.wildcard,
                      p.first_name || ' ' || p.last_name AS name,
                      t.city, t.mascot
               FROM all_stars a
               JOIN players p ON p.id = a.player_id
               JOIN teams t ON t.id = a.team_id
               WHERE a.season_id = %s
               ORDER BY a.wildcard, a.slot, a.points DESC, name""",
            (season_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def ids(self, season_id: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT player_id FROM all_stars WHERE season_id = %s", (season_id,)
        ).fetchall()
        return {r["player_id"] for r in rows}

    def seasons_for(self, player_id: str) -> list[dict]:
        """The seasons a player was an All-Star: year and team, oldest first."""
        rows = self.conn.execute(
            """SELECT s.year, t.city, t.mascot
               FROM all_stars a
               JOIN seasons s ON s.id = a.season_id
               JOIN teams t ON t.id = a.team_id
               WHERE a.player_id = %s
               ORDER BY s.year""",
            (player_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def _group(rows) -> dict[str, dict[str, list]]:
    """Vote rows, in pick order, as {team id: {slot: [player id or None]}}.
    A skipped pick is None."""
    out: dict[str, dict[str, list]] = {}
    for r in rows:
        picks = out.setdefault(r["team_id"], {}).setdefault(r["slot"], [])
        picks.extend([None] * (r["pick"] - 1 - len(picks)))
        picks.append(r["player_id"])
    return out
