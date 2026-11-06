# src/db/repositories/player_season_stats_repo.py

# A player stays a rookie until he passes either major league limit in the
# seasons before this one.
ROOKIE_MAX_AB = 130
ROOKIE_MAX_OUTS = 150  # 50 innings


class PlayerSeasonStatsRepository:
    def __init__(self, conn):
        self.conn = conn

    def get_max_games_played(self, season_id: str) -> int:
        """Return the max bat_games_played across all players in a season (regular season only)."""
        row = self.conn.execute(
            """SELECT MAX(bat_games_played) as tg FROM player_season_stats
               WHERE season_id = %s AND NOT is_postseason""",
            (season_id,),
        ).fetchone()
        return row["tg"] or 1

    def get_season_totals(self, season_id: str) -> dict:
        """The whole league's regular season totals, the bat_* and pitch_*
        columns advanced.LeagueRates needs, summed into one dict."""
        cols = [
            "bat_ab", "bat_hits", "bat_doubles", "bat_triples", "bat_home_runs",
            "bat_walks", "bat_hbp", "bat_sac_flys", "bat_runs",
            "pitch_outs", "pitch_earned_runs", "pitch_home_runs", "pitch_walks",
            "pitch_hit_batters", "pitch_strike_outs",
        ]  # fmt: skip
        sums = ", ".join(f"COALESCE(SUM({c}), 0) AS {c}" for c in cols)
        row = self.conn.execute(
            f"""SELECT {sums} FROM player_season_stats
                WHERE season_id = %s AND NOT is_postseason""",
            (season_id,),
        ).fetchone()
        return {c: int(row[c]) for c in cols} if row else {}

    def get_batting_for_league(self, league_id: str, season_id: str) -> list[dict]:
        """Return batting stats for all players in a league (regular season, at
        least 1 AB). A player traded during the season gets one row, his
        totals for every team, under the team he's on now."""
        return self._league_totals(
            league_id,
            season_id,
            [
                "bat_ab",
                "bat_hits",
                "bat_doubles",
                "bat_triples",
                "bat_home_runs",
                "bat_rbi",
                "bat_runs",
                "bat_walks",
                "bat_strike_outs",
                "bat_stolen_bases",
                "bat_hbp",
                "bat_sac_flys",
                "bat_games_played",
            ],
            "SUM(bat_ab) >= 1",
        )

    def _league_totals(
        self, league_id: str, season_id: str, columns: list[str], having: str
    ) -> list[dict]:
        """Each player's regular season `columns`, summed across the teams he
        played for in a league season. team_id, city and mascot are his
        current team if he played for it, else the one he played most for."""
        sums = ", ".join(f"SUM({c}) AS {c}" for c in columns)
        rows = self.conn.execute(
            f"""WITH s AS (
                    SELECT pss.* FROM player_season_stats pss
                    JOIN league_season_teams lst
                      ON lst.team_id = pss.team_id AND lst.season_id = pss.season_id
                     AND lst.league_id = %s
                    WHERE pss.season_id = %s AND NOT pss.is_postseason
                ),
                totals AS (
                    SELECT player_id, {sums} FROM s
                    GROUP BY player_id HAVING {having}
                ),
                shown AS (
                    SELECT DISTINCT ON (s.player_id) s.player_id, s.team_id
                    FROM s
                    LEFT JOIN team_players tp
                      ON tp.player_id = s.player_id AND tp.team_id = s.team_id
                    ORDER BY s.player_id, (tp.team_id IS NOT NULL) DESC,
                             s.bat_games_played + s.pitch_games_played DESC
                )
                SELECT totals.*, p.first_name, p.last_name, t.city, t.mascot,
                       shown.team_id
                FROM totals
                JOIN shown ON shown.player_id = totals.player_id
                JOIN players p ON p.id = totals.player_id
                JOIN teams t ON t.id = shown.team_id""",
            (league_id, season_id),
        ).fetchall()
        # SUM comes back as a Decimal
        return [
            {k: int(v) if k in columns and v is not None else v for k, v in r.items()}
            for r in rows
        ]

    def get_rookie_ids(self, league_id: str, season_id: str) -> set[str]:
        """Players who are rookies in this league season: drafted in the league
        (not on the rosters it started with) and, in the regular seasons before
        this one, under the major league limits of ROOKIE_MAX_AB at bats and
        ROOKIE_MAX_OUTS outs pitched (50 innings)."""
        rows = self.conn.execute(
            """WITH cur AS (SELECT year FROM seasons WHERE id = %s),
                drafted AS (
                    SELECT DISTINCT dp.player_id
                    FROM draft_picks dp
                    JOIN drafts d ON d.id = dp.draft_id
                    JOIN seasons ds ON ds.id = d.season_id
                    WHERE d.league_id = %s AND ds.year <= (SELECT year FROM cur)
                ),
                before AS (
                    SELECT pss.player_id, SUM(pss.bat_ab) AS ab,
                           SUM(pss.pitch_outs) AS outs
                    FROM player_season_stats pss
                    JOIN seasons s ON s.id = pss.season_id
                    WHERE NOT pss.is_postseason
                      AND s.year < (SELECT year FROM cur)
                      AND pss.player_id IN (SELECT player_id FROM drafted)
                    GROUP BY pss.player_id
                )
                SELECT drafted.player_id FROM drafted
                LEFT JOIN before ON before.player_id = drafted.player_id
                WHERE COALESCE(before.ab, 0) <= %s
                  AND COALESCE(before.outs, 0) <= %s""",
            (season_id, league_id, ROOKIE_MAX_AB, ROOKIE_MAX_OUTS),
        ).fetchall()
        return {r["player_id"] for r in rows}

    def get_player_season(self, player_id: str, season_id: str) -> dict | None:
        """Return a player's regular season stats as a dict, or None. A player
        traded during the season gets his totals for every team."""
        rows = self.conn.execute(
            """SELECT * FROM player_season_stats
               WHERE player_id = %s AND season_id = %s AND NOT is_postseason""",
            (player_id, season_id),
        ).fetchall()
        if not rows:
            return None
        total = dict(rows[0])
        for row in rows[1:]:
            for k, v in row.items():
                if isinstance(v, int) and not isinstance(v, bool):
                    total[k] = (total[k] or 0) + v
        return total

    def get_player_season_totals(self, season_id: str) -> dict[str, dict]:
        """
        Return {player_id: regular season totals} for a season, summed across
        teams so a traded player's games all count.
        """
        rows = self.conn.execute(
            """SELECT player_id,
                      SUM(bat_games_played) AS bat_games_played,
                      SUM(bat_ab) AS bat_ab, SUM(bat_hits) AS bat_hits,
                      SUM(bat_doubles) AS bat_doubles, SUM(bat_triples) AS bat_triples,
                      SUM(bat_home_runs) AS bat_home_runs, SUM(bat_walks) AS bat_walks,
                      SUM(bat_hbp) AS bat_hbp, SUM(bat_sac_flys) AS bat_sac_flys,
                      SUM(pitch_games_played) AS pitch_games_played,
                      SUM(pitch_games_started) AS pitch_games_started,
                      SUM(pitch_outs) AS pitch_outs,
                      SUM(pitch_earned_runs) AS pitch_earned_runs
               FROM player_season_stats
               WHERE season_id = %s AND NOT is_postseason
               GROUP BY player_id""",
            (season_id,),
        ).fetchall()
        totals = {}
        for row in rows:
            row = dict(row)
            player_id = row.pop("player_id")
            # SUM comes back as a Decimal
            totals[player_id] = {k: int(v or 0) for k, v in row.items()}
        return totals

    def get_form_totals(self, season_id: str, player_ids) -> dict[str, dict]:
        """{player_id: regular season totals} for these players: what
        src/league/performance.py needs to judge how they've played."""
        if not player_ids:
            return {}
        rows = self.conn.execute(
            """SELECT player_id,
                      SUM(bat_ab) AS bat_ab, SUM(bat_hits) AS bat_hits,
                      SUM(bat_doubles) AS bat_doubles, SUM(bat_triples) AS bat_triples,
                      SUM(bat_home_runs) AS bat_home_runs, SUM(bat_walks) AS bat_walks,
                      SUM(bat_hbp) AS bat_hbp, SUM(bat_sac_flys) AS bat_sac_flys,
                      SUM(pitch_games_played) AS pitch_games_played,
                      SUM(pitch_games_started) AS pitch_games_started,
                      SUM(pitch_outs) AS pitch_outs,
                      SUM(pitch_home_runs) AS pitch_home_runs,
                      SUM(pitch_walks) AS pitch_walks,
                      SUM(pitch_hit_batters) AS pitch_hit_batters,
                      SUM(pitch_strike_outs) AS pitch_strike_outs
               FROM player_season_stats
               WHERE season_id = %s AND NOT is_postseason AND player_id = ANY(%s)
               GROUP BY player_id""",
            (season_id, list(player_ids)),
        ).fetchall()
        out = {}
        for row in rows:
            row = dict(row)
            player_id = row.pop("player_id")
            # SUM comes back as a Decimal
            out[player_id] = {k: int(v or 0) for k, v in row.items()}
        return out

    def get_team_stats_map(self, season_id: str, team_id: str) -> dict[str, dict]:
        """Return {player_id: stat_dict} for all players on a team in a season
        (regular season). A player traded during the season gets his totals
        for every team he played for."""
        rows = self.conn.execute(
            """SELECT player_id,
                      SUM(bat_games_played) AS bat_games_played,
                      SUM(bat_hits) AS bat_hits, SUM(bat_ab) AS bat_ab,
                      SUM(bat_home_runs) AS bat_home_runs, SUM(bat_rbi) AS bat_rbi,
                      SUM(pitch_games_played) AS pitch_games_played,
                      SUM(pitch_games_started) AS pitch_games_started,
                      SUM(pitch_outs) AS pitch_outs,
                      SUM(pitch_earned_runs) AS pitch_earned_runs,
                      SUM(pitch_wins) AS pitch_wins, SUM(pitch_losses) AS pitch_losses,
                      SUM(pitch_saves) AS pitch_saves
               FROM player_season_stats
               WHERE season_id = %s AND NOT is_postseason
                 AND player_id IN (
                     SELECT player_id FROM team_players WHERE team_id = %s
                 )
               GROUP BY player_id""",
            (season_id, team_id),
        ).fetchall()
        # SUM comes back as a Decimal
        return {
            r["player_id"]: {
                k: (v if k == "player_id" or v is None else int(v))
                for k, v in r.items()
            }
            for r in rows
        }

    def get_max_games_played_for_team(
        self, season_id: str, team_id: str, is_postseason: bool = False
    ) -> int:
        """Return the max bat_games_played for a specific team in a season."""
        row = self.conn.execute(
            """SELECT MAX(bat_games_played) as tg FROM player_season_stats
               WHERE season_id = %s AND is_postseason = %s AND team_id = %s""",
            (season_id, is_postseason, team_id),
        ).fetchone()
        return row["tg"] or 0

    def get_for_team(
        self, season_id: str, team_id: str, is_postseason: bool = False
    ) -> list[dict]:
        """Return all player stats with first/last name for a team in a season."""
        rows = self.conn.execute(
            """SELECT p.id as player_id, p.first_name, p.last_name, pss.*
               FROM player_season_stats pss
               JOIN players p ON p.id = pss.player_id
               WHERE pss.season_id = %s AND pss.is_postseason = %s
                 AND pss.team_id = %s""",
            (season_id, is_postseason, team_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pitching_for_league(self, league_id: str, season_id: str) -> list[dict]:
        """Return pitching stats for all players in a league (regular season, at
        least 9 outs), a traded pitcher's teams summed into one row."""
        return self._league_totals(
            league_id,
            season_id,
            [
                "pitch_games_played",
                "pitch_games_started",
                "pitch_wins",
                "pitch_losses",
                "pitch_saves",
                "pitch_holds",
                "pitch_outs",
                "pitch_hits",
                "pitch_earned_runs",
                "pitch_walks",
                "pitch_strike_outs",
                "pitch_home_runs",
                "pitch_complete_games",
                "pitch_shutouts",
                "pitch_hit_batters",
            ],
            "SUM(pitch_outs) >= 9",
        )
