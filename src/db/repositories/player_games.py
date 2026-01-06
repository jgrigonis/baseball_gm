# src/db/repositories/player_game_stats.py
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
# src/db/repositories/player_games.py

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
        game_id: int,
        player_id: int,
        team_id: int,
        opponent_team_id: int,
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

    def get_for_game(self, game_id: int, player_id: int) -> Stats | None:
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

    def fetch_player_games(self, player_id: int) -> list[Stats]:
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
    # MAPPING TODO fix names
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
        b.sb = row["bat_sac_bunts"]
        b.gdp = row["bat_gdp"]
        b.gtp = row["bat_gtp"]
        b.cs = row["bat_stolen_bases"]
        b.cs = row["bat_caught_stealing"]
        b.cs = row["bat_pickoffs"]

        p.outs = row["pitch_outs"]
        p.hits = row["pitch_hits"]
        p.runs = row["pitch_runs"]
        p.home_runs = row["pitch_home_runs"]
        p.walks = row["pitch_walks"]
        p.strike_outs = row["pitch_strike_outs"]
        p.hb = row["pitch_hit_batters"]
        p.pitch_count = row["pitch_count"]

        f.putouts = row["field_putouts"]
        f.assists = row["field_assists"]
        f.errors = row["field_errors"]
        f.chances = f.putouts + f.assists + f.errors

        return s

    def dump_one(self):
        row = self.conn.execute(
            """
            SELECT *
            FROM player_game_stats
            """
        ).fetchone()
        if row is None:
            return None

        return self._row_to_stats(row)

    def load_season_stats(self, player_id, season):
        rows = self.conn.fetch_player_games(player_id, season)

        stats = Stats()
        for row in rows:
            stats.add(row.to_stats())

        return SeasonStats(stats, games_played=len(rows))


# Season stats:
# season = Stats()
# for game_stats in repo.get_all_for_player(player_id):
#     season.add(game_stats)


# Usage example
# repo = PlayerGameStatsRepository(conn)

# for player in team.players:
#     if player.game_stats.at_bats > 0:
#         repo.insert(
#             game_id=game.id,
#             player_id=player.id,
#             team_id=team.id,
#             stats=player.game_stats
#         )


# Unit test example
# def test_insert_player_game_stats():
#     conn = sqlite3.connect(":memory:")
#     init_db(conn)

#     repo = PlayerGameStatsRepository(conn)
#     fake_stats = FakeStats(
#         hits=2,
#         at_bats=4,
#         home_runs=1,
#         walks=1,
#         strikeouts=0,
#         rbi=3,
#         outs=2,
#     )

#     repo.insert(
#         game_id=1,
#         player_id=10,
#         team_id=3,
#         stats=fake_stats
#     )

#     row = conn.execute(
#         "SELECT hits, at_bats FROM player_game_stats"
#     ).fetchone()

#     assert row == (2, 4)

# You can make repositories stat-type aware:
# BattingStatsRow.from_stats(stats)

# Or add bulk inserts:
# repo.insert_many(game_id, team)

# finish up the code above for this
# CREATE TABLE IF NOT EXISTS player_game_stats (
#     game_id INTEGER NOT NULL,
#     player_id INTEGER NOT NULL,
#     team_id INTEGER NOT NULL,

#     -- batting
#     plate_appearances INTEGER,
#     at_bats INTEGER,
#     hits INTEGER,
#     doubles INTEGER,
#     triples INTEGER,
#     home_runs INTEGER,
#     walks INTEGER,
#     strikeouts INTEGER,
#     hbp INTEGER,
#     sac_flies INTEGER,
#     rbi INTEGER,
#     runs INTEGER,

#     -- baserunning
#     stolen_bases INTEGER,
#     caught_stealing INTEGER,

#     -- fielding
#     putouts INTEGER,
#     assists INTEGER,
#     errors INTEGER,

#     -- pitching (only filled if applicable)
#     batters_faced INTEGER,
#     outs_pitched INTEGER,
#     hits_allowed INTEGER,
#     runs_allowed INTEGER,
#     earned_runs INTEGER,
#     walks_allowed INTEGER,
#     strikeouts_pitched INTEGER,
#     home_runs_allowed INTEGER,

#     PRIMARY KEY (game_id, player_id)
# );
