# src/db/repositories/player_games.py
"""
Repository for player game statistics.

Handles:
- Inserting player stats for individual games
- Retrieving player stats for a specific game
- Fetching all games for a player
- Aggregating stats by season

Uses tables:
- player_game_stats
- games
"""

from src.stats.stats import Stats, SeasonStats
from src.stats.batting_stats import BattingStats
from src.stats.pitching_stats import PitchingStats
from src.stats.fielding_stats import FieldingStats


class PlayerGameRepository:
    """Repository for managing player game statistics."""

    def __init__(self, conn):
        self.conn = conn

    # ------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------

    def insert_player_game(
        self,
        game_id: str,
        player_id: str,
        team_id: str,
        opponent_team_id: str,
        stats: Stats,
        fielding_positions: list[tuple[str, FieldingStats]] | None = None,
    ) -> None:
        """
        Persist a player's stats for a single game.
        Idempotent - calling multiple times with same game_id/player_id updates the record.

        Args:
            game_id: Game ID
            player_id: Player ID
            team_id: Player's team ID
            opponent_team_id: Opponent team ID
            stats: Stats object containing batting, pitching, and fielding stats
        """

        b = stats.batting
        p = stats.pitching
        f = stats.fielding
        self.conn.execute(
            """
            INSERT INTO player_game_stats (
                game_id, player_id, team_id, opponent_team_id,

                bat_game_played, bat_game_started,
                bat_ab, bat_hits, bat_doubles, bat_triples,
                bat_home_runs, bat_rbi, bat_runs,
                bat_walks, bat_strike_outs, bat_strike_outs_looking, bat_hbp, bat_sac_flys,
                bat_sac_bunts, bat_gdp, bat_gtp, bat_stolen_bases, bat_caught_stealing,

                pitch_game_played, pitch_game_started,
                pitch_complete_game, pitch_shutout, pitch_no_hitter, pitch_win, pitch_loss, pitch_save, pitch_hold,
                pitch_outs, pitch_hits, pitch_runs, pitch_earned_runs,
                pitch_home_runs, pitch_walks, pitch_strike_outs, pitch_strike_outs_looking,
                pitch_hit_batters, pitch_doubles, pitch_triples, pitch_pickoffs, 
                pitch_balks, pitch_wild_pitches, pitch_count,

                field_putouts, field_assists, field_errors, passed_balls, 
                catcher_interferences, catcher_cs, catcher_sb,
                field_double_plays, field_triple_plays
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (game_id, player_id) DO UPDATE SET
                team_id = EXCLUDED.team_id, opponent_team_id = EXCLUDED.opponent_team_id,
                bat_game_played = EXCLUDED.bat_game_played, bat_game_started = EXCLUDED.bat_game_started,
                bat_ab = EXCLUDED.bat_ab, bat_hits = EXCLUDED.bat_hits,
                bat_doubles = EXCLUDED.bat_doubles, bat_triples = EXCLUDED.bat_triples,
                bat_home_runs = EXCLUDED.bat_home_runs, bat_rbi = EXCLUDED.bat_rbi,
                bat_runs = EXCLUDED.bat_runs, bat_walks = EXCLUDED.bat_walks,
                bat_strike_outs = EXCLUDED.bat_strike_outs,
                bat_strike_outs_looking = EXCLUDED.bat_strike_outs_looking, bat_hbp = EXCLUDED.bat_hbp,
                bat_sac_flys = EXCLUDED.bat_sac_flys, bat_sac_bunts = EXCLUDED.bat_sac_bunts,
                bat_gdp = EXCLUDED.bat_gdp, bat_gtp = EXCLUDED.bat_gtp,
                bat_stolen_bases = EXCLUDED.bat_stolen_bases, bat_caught_stealing = EXCLUDED.bat_caught_stealing,
                pitch_game_played = EXCLUDED.pitch_game_played, pitch_game_started = EXCLUDED.pitch_game_started,
                pitch_complete_game = EXCLUDED.pitch_complete_game, pitch_shutout = EXCLUDED.pitch_shutout,
                pitch_no_hitter = EXCLUDED.pitch_no_hitter,
                pitch_win = EXCLUDED.pitch_win, pitch_loss = EXCLUDED.pitch_loss,
                pitch_save = EXCLUDED.pitch_save, pitch_hold = EXCLUDED.pitch_hold,
                pitch_outs = EXCLUDED.pitch_outs, pitch_hits = EXCLUDED.pitch_hits,
                pitch_runs = EXCLUDED.pitch_runs, pitch_earned_runs = EXCLUDED.pitch_earned_runs,
                pitch_home_runs = EXCLUDED.pitch_home_runs, pitch_walks = EXCLUDED.pitch_walks,
                pitch_strike_outs = EXCLUDED.pitch_strike_outs,
                pitch_strike_outs_looking = EXCLUDED.pitch_strike_outs_looking,
                pitch_hit_batters = EXCLUDED.pitch_hit_batters,
                pitch_doubles = EXCLUDED.pitch_doubles, pitch_triples = EXCLUDED.pitch_triples,
                pitch_pickoffs = EXCLUDED.pitch_pickoffs, pitch_balks = EXCLUDED.pitch_balks,
                pitch_wild_pitches = EXCLUDED.pitch_wild_pitches, pitch_count = EXCLUDED.pitch_count,
                field_putouts = EXCLUDED.field_putouts, field_assists = EXCLUDED.field_assists,
                field_errors = EXCLUDED.field_errors, passed_balls = EXCLUDED.passed_balls,
                catcher_interferences = EXCLUDED.catcher_interferences,
                catcher_cs = EXCLUDED.catcher_cs, catcher_sb = EXCLUDED.catcher_sb,
                field_double_plays = EXCLUDED.field_double_plays,
                field_triple_plays = EXCLUDED.field_triple_plays
            """,
            (
                game_id,
                player_id,
                team_id,
                opponent_team_id,
                b.game_played,
                b.game_started,
                b.at_bats,
                b.hits,
                b.doubles,
                b.triples,
                b.home_runs,
                b.rbi,
                b.runs,
                b.walks,
                b.strike_outs,
                b.strike_outs_looking,
                b.hbp,
                b.sac_flys,
                b.sac_bunts,
                b.gdp,
                b.gtp,
                b.sb,
                b.cs,
                p.game_played,
                p.game_started,
                p.complete_game,
                p.shut_out,
                p.no_hitter,
                p.win,
                p.loss,
                p.save,
                p.hold,
                p.outs,
                p.hits,
                p.runs,
                p.earned_runs,
                p.home_runs,
                p.walks,
                p.strike_outs,
                p.strike_outs_looking,
                p.hb,
                p.doubles,
                p.triples,
                p.pickoffs,
                p.balks,
                p.wild_pitches,
                p.pitch_count,
                f.putouts,
                f.assists,
                f.errors,
                f.passed_balls,
                f.catcher_interferences,
                f.catcher_cs,
                f.catcher_sb,
                f.double_plays,
                f.triple_plays,
            ),
        )

        # Insert per-position fielding stats
        if fielding_positions:
            for position, fs in fielding_positions:
                self.conn.execute(
                    """
                    INSERT INTO player_game_fielding (
                        game_id, player_id, position,
                        putouts, assists, errors, passed_balls,
                        catcher_interferences, catcher_cs, catcher_sb,
                        double_plays, triple_plays
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (game_id, player_id, position) DO UPDATE SET
                        putouts = EXCLUDED.putouts, assists = EXCLUDED.assists,
                        errors = EXCLUDED.errors, passed_balls = EXCLUDED.passed_balls,
                        catcher_interferences = EXCLUDED.catcher_interferences,
                        catcher_cs = EXCLUDED.catcher_cs, catcher_sb = EXCLUDED.catcher_sb,
                        double_plays = EXCLUDED.double_plays,
                        triple_plays = EXCLUDED.triple_plays
                    """,
                    (
                        game_id,
                        player_id,
                        position,
                        fs.putouts,
                        fs.assists,
                        fs.errors,
                        fs.passed_balls,
                        fs.catcher_interferences,
                        fs.catcher_cs,
                        fs.catcher_sb,
                        fs.double_plays,
                        fs.triple_plays,
                    ),
                )

        # self.conn.commit()

    # Only called by tests
    def delete_game_stats(self, game_id: str) -> None:
        """
        Delete all player stats for a game (for replaying games).
        Delete the fielding stats as well.

        Args:
            game_id: Game ID
        """
        self.conn.execute(
            "DELETE FROM player_game_stats WHERE game_id = %s", (game_id,)
        )
        self.conn.execute(
            "DELETE FROM player_game_fielding WHERE game_id = %s", (game_id,)
        )
        # self.conn.commit()

    # ------------------------------------------------------------
    # READ
    # ------------------------------------------------------------

    def get_for_game(self, game_id: str, player_id: str) -> Stats | None:
        """
        Fetch a player's stats for a single game.

        Args:
            game_id: Game ID
            player_id: Player ID

        Returns:
            Stats object if found, None otherwise
        """
        row = self.conn.execute(
            """
            SELECT *
            FROM player_game_stats
            WHERE game_id = %s AND player_id = %s
            """,
            (game_id, player_id),
        ).fetchone()

        if row is None:
            return None

        return self._row_to_stats(row)

    def fetch_player_games(self, player_id: str) -> list[Stats]:
        """
        Fetch all game stats for a player across their career.

        Args:
            player_id: Player ID

        Returns:
            List of Stats objects, one per game, ordered by game_id
        """
        rows = self.conn.execute(
            """
            SELECT *
            FROM player_game_stats
            WHERE player_id = %s
            ORDER BY game_id
            """,
            (player_id,),
        ).fetchall()

        return [self._row_to_stats(r) for r in rows]

    def load_season_stats(self, player_id: str, season_id: str) -> SeasonStats:
        """
        Load aggregated stats for a player in a specific season.

        Args:
            player_id: Player ID
            season_id: Season ID

        Returns:
            SeasonStats with aggregated stats and games played count
        """
        rows = self.conn.execute(
            """
            SELECT pgs.*
            FROM player_game_stats pgs
            JOIN games g ON pgs.game_id = g.id
            WHERE pgs.player_id = %s AND g.season_id = %s AND g.series_id IS NULL
            ORDER BY g.game_date
            """,
            (player_id, season_id),
        ).fetchall()

        # Aggregate stats across all games
        aggregated = Stats()
        for row in rows:
            game_stats = self._row_to_stats(row)
            aggregated.add(game_stats)

        return SeasonStats(aggregated, games_played=len(rows))

    def get_players_in_game(self, game_id: str) -> list[str]:
        """
        Get all player IDs who participated in a game.

        Args:
            game_id: Game ID

        Returns:
            List of player IDs
        """
        rows = self.conn.execute(
            """
            SELECT DISTINCT player_id FROM player_game_stats
            WHERE game_id = %s
            ORDER BY player_id
            """,
            (game_id,),
        ).fetchall()

        return [row["player_id"] for row in rows]

    # ------------------------------------------------------------
    # MAPPING
    # ------------------------------------------------------------

    def _row_to_stats(self, row) -> Stats:
        s = Stats()

        b: BattingStats = s.batting
        p: PitchingStats = s.pitching
        f: FieldingStats = s.fielding

        b.at_bats = row["bat_ab"]
        b.hits = row["bat_hits"]
        b.doubles = row["bat_doubles"]
        b.triples = row["bat_triples"]
        b.home_runs = row["bat_home_runs"]
        b.rbi = row["bat_rbi"]
        b.runs = row["bat_runs"]
        b.walks = row["bat_walks"]
        b.strike_outs = row["bat_strike_outs"]
        b.strike_outs_looking = row["bat_strike_outs_looking"]
        b.hbp = row["bat_hbp"]
        b.sac_flys = row["bat_sac_flys"]
        b.sac_bunts = row["bat_sac_bunts"]
        b.gdp = row["bat_gdp"]
        b.gtp = row["bat_gtp"]
        b.sb = row["bat_stolen_bases"]
        b.cs = row["bat_caught_stealing"]

        p.win = row["pitch_win"]
        p.loss = row["pitch_loss"]
        p.save = row["pitch_save"]
        p.hold = row["pitch_hold"]
        p.outs = row["pitch_outs"]
        p.hits = row["pitch_hits"]
        p.runs = row["pitch_runs"]
        p.earned_runs = row["pitch_earned_runs"]
        p.home_runs = row["pitch_home_runs"]
        p.walks = row["pitch_walks"]
        p.strike_outs = row["pitch_strike_outs"]
        p.strike_outs_looking = row["pitch_strike_outs_looking"]
        p.hb = row["pitch_hit_batters"]
        p.pitch_count = row["pitch_count"]
        p.doubles = row["pitch_doubles"]
        p.triples = row["pitch_triples"]
        p.pickoffs = row["pitch_pickoffs"]
        p.balks = row["pitch_balks"]
        p.wild_pitches = row["pitch_wild_pitches"]

        f.putouts = row["field_putouts"]
        f.assists = row["field_assists"]
        f.errors = row["field_errors"]
        f.double_plays = row["field_double_plays"]
        f.triple_plays = row["field_triple_plays"]
        f.chances = f.putouts + f.assists + f.errors

        return s

    def get_player_stats_totals(
        self, player_id: str, season_id: str | None = None
    ) -> dict | None:
        """Return aggregated batting+pitching totals for a player.

        If season_id is given, scopes to that season; otherwise returns career totals.
        Returns None if the player has no games matching the filter.
        """
        season_filter = "AND g.season_id = %s" if season_id else ""
        params = [player_id, season_id] if season_id else [player_id]
        row = self.conn.execute(
            f"""
            SELECT
                COUNT(DISTINCT pgs.game_id) AS games_played,
                SUM(pgs.bat_ab) AS bat_ab,
                SUM(pgs.bat_hits) AS bat_hits,
                SUM(pgs.bat_doubles) AS bat_doubles,
                SUM(pgs.bat_triples) AS bat_triples,
                SUM(pgs.bat_home_runs) AS bat_home_runs,
                SUM(pgs.bat_rbi) AS bat_rbi,
                SUM(pgs.bat_runs) AS bat_runs,
                SUM(pgs.bat_walks) AS bat_walks,
                SUM(pgs.bat_strike_outs) AS bat_strike_outs,
                SUM(pgs.bat_strike_outs_looking) AS bat_strike_outs_looking,
                SUM(pgs.bat_stolen_bases) AS bat_stolen_bases,
                SUM(pgs.bat_hbp) AS bat_hbp,
                SUM(pgs.bat_sac_flys) AS bat_sac_flys,
                SUM(pgs.pitch_game_played) AS pitch_game_played,
                SUM(pgs.pitch_game_started) AS pitch_game_started,
                SUM(pgs.pitch_win) AS pitch_win,
                SUM(pgs.pitch_loss) AS pitch_loss,
                SUM(pgs.pitch_save) AS pitch_save,
                SUM(pgs.pitch_hold) AS pitch_hold,
                SUM(pgs.pitch_complete_game) AS pitch_complete_game,
                SUM(pgs.pitch_shutout) AS pitch_shutout,
                SUM(pgs.pitch_no_hitter) AS pitch_no_hitter,
                SUM(pgs.pitch_outs) AS pitch_outs,
                SUM(pgs.pitch_hits) AS pitch_hits,
                SUM(pgs.pitch_runs) AS pitch_runs,
                SUM(pgs.pitch_earned_runs) AS pitch_earned_runs,
                SUM(pgs.pitch_walks) AS pitch_walks,
                SUM(pgs.pitch_strike_outs) AS pitch_strike_outs,
                SUM(pgs.pitch_strike_outs_looking) AS pitch_strike_outs_looking,
                SUM(pgs.pitch_home_runs) AS pitch_home_runs,
                SUM(pgs.pitch_count) AS pitch_count
            FROM player_game_stats pgs
            JOIN games g ON g.id = pgs.game_id
            WHERE pgs.player_id = %s {season_filter}
            """,
            params,
        ).fetchone()
        if not row or (row["games_played"] or 0) == 0:
            return None
        return dict(row)

    def get_batting_box_score(self, game_id: str) -> list[dict]:
        """Return batting lines for a game box score: the starting lineup in
        batting order with each starter's position (game_lineup_slots), then
        anyone else who batted. A starter shows even without an at-bat."""
        rows = self.conn.execute(
            """SELECT p.first_name, p.last_name, p.id as player_id, pgs.team_id,
                      pgs.bat_ab as "AB", pgs.bat_runs as "R", pgs.bat_hits as "H",
                      pgs.bat_doubles as doubles, pgs.bat_triples as triples,
                      pgs.bat_home_runs as "HR", pgs.bat_rbi as "RBI",
                      pgs.bat_walks as "BB", pgs.bat_strike_outs as "K",
                      pgs.bat_stolen_bases as "SB", pgs.bat_hbp as "HBP",
                      pgs.bat_sac_flys as "SF",
                      pgs.bat_game_started as started,
                      ls.batting_order, ls.position
               FROM player_game_stats pgs
               JOIN players p ON p.id = pgs.player_id
               LEFT JOIN game_lineup_slots ls
                 ON ls.game_id = pgs.game_id AND ls.team_id = pgs.team_id
                AND ls.player_id = pgs.player_id AND ls.is_pitcher = 0
               WHERE pgs.game_id = %s
                 AND (pgs.bat_ab > 0 OR ls.batting_order IS NOT NULL)
               ORDER BY pgs.team_id, ls.batting_order NULLS LAST,
                        pgs.bat_game_started DESC, p.last_name""",
            (game_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_team_errors(self, game_id: str) -> dict[str, int]:
        """Return {team_id: errors} for a game, from its fielding lines."""
        rows = self.conn.execute(
            """SELECT pgs.team_id, SUM(pgf.errors) AS e
               FROM player_game_fielding pgf
               JOIN player_game_stats pgs
                 ON pgs.game_id = pgf.game_id AND pgs.player_id = pgf.player_id
               WHERE pgf.game_id = %s
               GROUP BY pgs.team_id""",
            (game_id,),
        ).fetchall()
        return {r["team_id"]: int(r["e"] or 0) for r in rows}

    def get_no_hitters(self, season_id: str) -> list[dict]:
        """Return the season's no-hitters, regular season and playoffs, in date order."""
        rows = self.conn.execute(
            """SELECT p.id as player_id, p.first_name, p.last_name, g.id as game_id,
                      g.game_date, g.series_id IS NOT NULL AS postseason,
                      pgs.team_id, t.city, t.mascot, o.city as opp_city, o.mascot as opp_mascot,
                      pgs.pitch_strike_outs as "K", pgs.pitch_walks as "BB"
               FROM player_game_stats pgs
               JOIN games g ON g.id = pgs.game_id
               JOIN players p ON p.id = pgs.player_id
               JOIN teams t ON t.id = pgs.team_id
               JOIN teams o ON o.id = pgs.opponent_team_id
               WHERE g.season_id = %s AND pgs.pitch_no_hitter = 1
               ORDER BY g.game_date, g.id""",
            (season_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pitching_box_score(self, game_id: str) -> list[dict]:
        """Return pitching lines for all pitchers who appeared in a game, ordered for display."""
        rows = self.conn.execute(
            """SELECT p.first_name, p.last_name, p.id as player_id, pgs.team_id,
                      pgs.pitch_outs as outs, pgs.pitch_hits as "H",
                      pgs.pitch_runs as "R", pgs.pitch_earned_runs as "ER",
                      pgs.pitch_walks as "BB", pgs.pitch_strike_outs as "K",
                      pgs.pitch_home_runs as "HR", pgs.pitch_win as "W",
                      pgs.pitch_loss as "L", pgs.pitch_save as "SV",
                      pgs.pitch_complete_game as "CG", pgs.pitch_shutout as "SHO",
                      pgs.pitch_no_hitter as "NH",
                      pgs.pitch_game_started as started
               FROM player_game_stats pgs
               JOIN players p ON p.id = pgs.player_id
               WHERE pgs.game_id = %s AND pgs.pitch_game_played = 1
               ORDER BY pgs.team_id, pgs.pitch_game_started DESC, pgs.pitch_outs DESC""",
            (game_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------
    # FIELDING AGGREGATES
    # ------------------------------------------------------------

    def get_league_fielding_by_position(self, season_id: str) -> list[dict]:
        """Season fielding totals per player and position across the league
        (pitchers and DH excluded), for the defensive leaderboards."""
        return self.conn.execute(
            """SELECT p.first_name || ' ' || p.last_name AS name,
                      pgf.player_id, pgf.position,
                      t.city, t.mascot, pgs.team_id,
                      COUNT(DISTINCT pgf.game_id)        AS g,
                      SUM(pgf.putouts)                   AS po,
                      SUM(pgf.assists)                   AS a,
                      SUM(pgf.errors)                    AS e,
                      SUM(COALESCE(pgf.passed_balls, 0)) AS pb,
                      SUM(COALESCE(pgf.double_plays, 0)) AS dp,
                      SUM(COALESCE(pgf.triple_plays, 0)) AS tp
               FROM player_game_fielding pgf
               JOIN games gm  ON gm.id  = pgf.game_id
               JOIN players p ON p.id   = pgf.player_id
               JOIN player_game_stats pgs
                    ON pgs.game_id = pgf.game_id AND pgs.player_id = pgf.player_id
               JOIN teams t   ON t.id   = pgs.team_id
               WHERE gm.season_id = %s AND pgf.position NOT IN ('p', 'dh')
               GROUP BY pgf.player_id, pgf.position, pgs.team_id,
                        p.first_name, p.last_name, t.city, t.mascot""",
            (season_id,),
        ).fetchall()

    def get_team_fielding_by_position(self, season_id: str, team_id: str) -> list[dict]:
        """Season fielding totals per player and position for one team
        (pitchers and DH excluded), for the lineup page."""
        return self.conn.execute(
            """SELECT pgf.player_id, pgf.position,
                      COUNT(DISTINCT pgf.game_id) AS g,
                      SUM(pgf.putouts)  AS po,
                      SUM(pgf.assists)  AS a,
                      SUM(pgf.errors)   AS e,
                      SUM(COALESCE(pgf.passed_balls, 0)) AS pb,
                      SUM(COALESCE(pgf.double_plays, 0)) AS dp,
                      SUM(COALESCE(pgf.triple_plays, 0)) AS tp
               FROM player_game_fielding pgf
               JOIN games gm ON gm.id = pgf.game_id
               JOIN player_game_stats pgs
                 ON pgs.game_id = pgf.game_id AND pgs.player_id = pgf.player_id
               WHERE gm.season_id = %s AND pgs.team_id = %s
                 AND pgf.position NOT IN ('p', 'dh')
               GROUP BY pgf.player_id, pgf.position""",
            (season_id, team_id),
        ).fetchall()

    def get_team_fielding_lines(self, season_id: str, team_id: str) -> list[dict]:
        """Season fielding totals per player and position for one team, with
        names, ordered for the team stats table (only DH excluded)."""
        return self.conn.execute(
            """SELECT p.first_name || ' ' || p.last_name AS name,
                      pgf.player_id, pgf.position,
                      COUNT(DISTINCT pgf.game_id)   AS g,
                      SUM(pgf.putouts)              AS po,
                      SUM(pgf.assists)              AS a,
                      SUM(pgf.errors)               AS e,
                      SUM(pgf.passed_balls)         AS pb,
                      SUM(COALESCE(pgf.double_plays, 0)) AS dp,
                      SUM(COALESCE(pgf.triple_plays, 0)) AS tp
               FROM player_game_fielding pgf
               JOIN games g    ON g.id = pgf.game_id
               JOIN players p  ON p.id = pgf.player_id
               JOIN player_game_stats pgs
                    ON pgs.game_id = pgf.game_id AND pgs.player_id = pgf.player_id
               WHERE g.season_id = %s AND pgs.team_id = %s AND pgf.position != 'dh'
               GROUP BY pgf.player_id, pgf.position, p.first_name, p.last_name
               ORDER BY name, pgf.position""",
            (season_id, team_id),
        ).fetchall()
