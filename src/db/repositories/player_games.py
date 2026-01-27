# src/db/repositories/player_games.py
"""
Insert per-game stats

Fetch all games for a player

Aggregate by season

Hydrate Stats

Uses these tables:
player_game_stats
games
teams
"""
from src.stats.stats import Stats
from src.stats.stats import SeasonStats
from src.stats.batting_stats import BattingStats
from src.stats.pitching_stats import PitchingStats
from src.stats.fielding_stats import FieldingStats


class PlayerGameRepository:
    def __init__(self, conn):
        self.conn = conn

    # ------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------

    def insert(
        self,
        game_id: str,
        player_id: str,
        team_id: str,
        opponent_team_id: str,
        stats: Stats,
    ):
        """
        Persist a player's stats for a single game.
        Idempotent per (game_id, player_id).
        """

        b = stats.batting
        p = stats.pitching
        f = stats.fielding
        self.conn.execute(
            """
            INSERT OR REPLACE INTO player_game_stats (
                game_id, player_id, team_id, opponent_team_id,

                bat_ab, bat_hits, bat_doubles, bat_triples,
                bat_home_runs, bat_rbi, bat_runs,
                bat_walks, bat_strike_outs, bat_hbp, bat_sac_flys,
                bat_sac_bunts, bat_gdp, bat_gtp, bat_stolen_bases, bat_caught_stealing, bat_pickoffs,

                pitch_outs, pitch_hits, pitch_runs,
                pitch_home_runs, pitch_walks, pitch_strike_outs,
                pitch_hit_batters, pitch_doubles, pitch_triples, pitch_pickoffs, 
                pitch_balks, pitch_wild_pitches, pitch_count,

                field_putouts, field_assists, field_errors
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                game_id,
                player_id,
                team_id,
                opponent_team_id,
                b.at_bats,
                b.hits,
                b.doubles,
                b.triples,
                b.home_runs,
                b.rbi,
                b.runs,
                b.walks,
                b.strike_outs,
                b.hbp,
                b.sac_flys,
                b.sac_bunts,
                b.gdp,
                b.gtp,
                b.sb,
                b.cs,
                b.pickoffs,
                p.outs,
                p.hits,
                p.runs,
                p.home_runs,
                p.walks,
                p.strike_outs,
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
            ),
        )

        self.conn.commit()

    def get_for_game(self, game_id: str, player_id: str) -> Stats | None:
        """
        READ side (hydration)
        Fetch a player’s stats for a single game
        """
        row = self.conn.execute(
            """
            SELECT *
            FROM player_game_stats
            WHERE game_id = ? AND player_id = ?
            """,
            (game_id, player_id),
        ).fetchone()

        if row is None:
            return None

        return self._row_to_stats(row)

    def fetch_player_games(self, player_id: str) -> list[Stats]:
        """
        Fetch all games for a player (career / season aggregation)
        """
        rows = self.conn.execute(
            """
            SELECT *
            FROM player_game_stats
            WHERE player_id = ?
            ORDER BY game_id
            """,
            (player_id,),
        ).fetchall()

        return [self._row_to_stats(r) for r in rows]

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
        b.hbp = row["bat_hbp"]
        b.sac_flys = row["bat_sac_flys"]
        b.sac_bunts = row["bat_sac_bunts"]
        b.gdp = row["bat_gdp"]
        b.gtp = row["bat_gtp"]
        b.sb = row["bat_stolen_bases"]
        b.cs = row["bat_caught_stealing"]
        b.pickoffs = row["bat_pickoffs"]

        p.outs = row["pitch_outs"]
        p.hits = row["pitch_hits"]
        p.runs = row["pitch_runs"]
        p.home_runs = row["pitch_home_runs"]
        p.walks = row["pitch_walks"]
        p.strike_outs = row["pitch_strike_outs"]
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
        f.chances = f.putouts + f.assists + f.errors

        return s

    # def dump_one(self) -> Stats | None:
    #     """
    #     Just a testing function, not used
    #     """
    #     row = self.conn.execute(
    #         """
    #         SELECT *
    #         FROM player_game_stats
    #         """
    #     ).fetchone()
    #     if row is None:
    #         return None

    #     return self._row_to_stats(row)

    def load_season_stats(self, player_id: str, season_id: str) -> SeasonStats:
        """
        Load a season worth of stats
        """
        rows = self.conn.execute(
            """
            SELECT pgs.*
            FROM player_game_stats pgs
            JOIN games g ON pgs.game_id = g.id
            WHERE pgs.player_id = ? AND g.season_id = ?
            ORDER BY g.date
            """,
            (player_id, season_id),
        ).fetchall()

        stats = Stats()
        for row in rows:
            game_stats = self._row_to_stats(row)
            stats.add(game_stats)  # Assuming Stats has an add method

        return SeasonStats(stats, games_played=len(rows))
