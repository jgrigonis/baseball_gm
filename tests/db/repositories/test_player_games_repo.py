# tests/db/repositories/test_player_games_repo.py
import pytest

from src.db.repositories.player_games import PlayerGameRepository
from src.stats.stats import Stats
from src.stats.fielding_stats import FieldingStats


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def player_repo(db_conn):
    return PlayerGameRepository(db_conn)


# Alias used by some tests
@pytest.fixture
def player_games_repo(db_conn):
    return PlayerGameRepository(db_conn)


@pytest.fixture
def ctx(db_conn, factory):
    """
    Unique game, players, and teams per test.
    All IDs are UUIDs so committed rows never collide across runs.
    """
    from types import SimpleNamespace
    import uuid

    season = factory.season()
    home   = factory.team()
    away   = factory.team()
    p1     = factory.player_row()
    p2     = factory.player_row()

    game_id = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)"
        " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (game_id, "2025-04-01", season.id, home.id, away.id),
    )

    return SimpleNamespace(
        conn=db_conn,
        season=season,
        home=home,
        away=away,
        p1=p1,
        p2=p2,
        game_id=game_id,
    )


@pytest.fixture
def sample_stats():
    stats = Stats()
    stats.batting.at_bats    = 4
    stats.batting.hits       = 2
    stats.batting.doubles    = 1
    stats.batting.triples    = 0
    stats.batting.home_runs  = 1
    stats.batting.rbi        = 3
    stats.batting.runs       = 2
    stats.batting.walks      = 1
    stats.batting.strike_outs = 1
    stats.batting.hbp        = 0
    stats.batting.sac_flys   = 0
    stats.batting.sac_bunts  = 0
    stats.batting.gdp        = 0
    stats.batting.gtp        = 0
    stats.batting.sb         = 1
    stats.batting.cs         = 0
    stats.batting.pickoffs   = 0

    stats.pitching.outs         = 27
    stats.pitching.hits         = 5
    stats.pitching.runs         = 2
    stats.pitching.home_runs    = 1
    stats.pitching.walks        = 2
    stats.pitching.strike_outs  = 8
    stats.pitching.hb           = 0
    stats.pitching.pitch_count  = 95
    stats.pitching.doubles      = 1
    stats.pitching.triples      = 0
    stats.pitching.pickoffs     = 0
    stats.pitching.balks        = 0
    stats.pitching.wild_pitches = 1

    stats.fielding.putouts    = 3
    stats.fielding.assists    = 1
    stats.fielding.errors     = 0
    stats.fielding.passed_ball = 0
    return stats


@pytest.fixture
def sample_fielding_positions():
    ss = FieldingStats()
    ss.putouts = 1
    ss.assists = 5
    ss.errors  = 0
    return [("ss", ss)]


@pytest.fixture
def sample_fielding_positions_two_way():
    fb = FieldingStats()
    fb.putouts = 10
    fb.assists = 2
    fb.errors  = 0

    p = FieldingStats()
    p.putouts = 0
    p.assists = 2
    p.errors  = 1
    return [("1b", fb), ("p", p)]


# ---------------------------------------------------------------------------
# TestPlayerGameRepositoryInsert
# ---------------------------------------------------------------------------


class TestPlayerGameRepositoryInsert:

    def test_insert_basic(self, player_repo, ctx, sample_stats):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)

        row = ctx.conn.execute(
            "SELECT * FROM player_game_stats WHERE game_id = %s AND player_id = %s",
            (ctx.game_id, ctx.p1.id),
        ).fetchone()

        assert row is not None
        assert row["game_id"] == ctx.game_id
        assert row["player_id"] == ctx.p1.id
        assert row["team_id"] == ctx.home.id
        assert row["opponent_team_id"] == ctx.away.id

    def test_insert_batting_stats(self, player_repo, ctx, sample_stats):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)

        row = ctx.conn.execute(
            "SELECT * FROM player_game_stats WHERE game_id = %s AND player_id = %s",
            (ctx.game_id, ctx.p1.id),
        ).fetchone()

        assert row["bat_ab"] == 4
        assert row["bat_hits"] == 2
        assert row["bat_doubles"] == 1
        assert row["bat_home_runs"] == 1
        assert row["bat_rbi"] == 3
        assert row["bat_runs"] == 2
        assert row["bat_walks"] == 1
        assert row["bat_strike_outs"] == 1
        assert row["bat_stolen_bases"] == 1

    def test_insert_pitching_stats(self, player_repo, ctx, sample_stats):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)

        row = ctx.conn.execute(
            "SELECT * FROM player_game_stats WHERE game_id = %s AND player_id = %s",
            (ctx.game_id, ctx.p1.id),
        ).fetchone()

        assert row["pitch_outs"] == 27
        assert row["pitch_hits"] == 5
        assert row["pitch_runs"] == 2
        assert row["pitch_home_runs"] == 1
        assert row["pitch_walks"] == 2
        assert row["pitch_strike_outs"] == 8
        assert row["pitch_count"] == 95

    def test_insert_fielding_stats(self, player_repo, ctx, sample_stats):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)

        row = ctx.conn.execute(
            "SELECT * FROM player_game_stats WHERE game_id = %s AND player_id = %s",
            (ctx.game_id, ctx.p1.id),
        ).fetchone()

        assert row["field_putouts"] == 3
        assert row["field_assists"] == 1
        assert row["field_errors"] == 0

    def test_insert_idempotent(self, player_repo, ctx, sample_stats):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)
        sample_stats.batting.hits = 3
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)

        count = ctx.conn.execute(
            "SELECT COUNT(*) AS n FROM player_game_stats WHERE game_id = %s AND player_id = %s",
            (ctx.game_id, ctx.p1.id),
        ).fetchone()["n"]
        assert count == 1

        row = ctx.conn.execute(
            "SELECT bat_hits FROM player_game_stats WHERE game_id = %s AND player_id = %s",
            (ctx.game_id, ctx.p1.id),
        ).fetchone()
        assert row["bat_hits"] == 3

    def test_insert_zero_stats(self, player_repo, ctx):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, Stats())

        row = ctx.conn.execute(
            "SELECT * FROM player_game_stats WHERE game_id = %s AND player_id = %s",
            (ctx.game_id, ctx.p1.id),
        ).fetchone()
        assert row is not None
        assert row["bat_ab"] == 0
        assert row["pitch_outs"] == 0
        assert row["field_putouts"] == 0

    def test_insert_multiple_players_same_game(self, player_repo, ctx, sample_stats, factory):
        players = [factory.player_row() for _ in range(5)]
        for p in players:
            player_repo.insert(ctx.game_id, p.id, ctx.home.id, ctx.away.id, sample_stats)

        count = ctx.conn.execute(
            "SELECT COUNT(*) AS n FROM player_game_stats WHERE game_id = %s",
            (ctx.game_id,),
        ).fetchone()["n"]
        assert count == 5


# ---------------------------------------------------------------------------
# TestPlayerGameRepositoryFieldingPositions
# ---------------------------------------------------------------------------


class TestPlayerGameRepositoryFieldingPositions:

    def test_insert_single_fielding_position(self, player_repo, ctx, sample_stats, sample_fielding_positions):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id,
                           sample_stats, fielding_positions=sample_fielding_positions)

        rows = ctx.conn.execute(
            "SELECT * FROM player_game_fielding WHERE game_id = %s AND player_id = %s",
            (ctx.game_id, ctx.p1.id),
        ).fetchall()

        assert len(rows) == 1
        assert rows[0]["position"] == "ss"
        assert rows[0]["putouts"] == 1
        assert rows[0]["assists"] == 5
        assert rows[0]["errors"] == 0

    def test_insert_two_way_player(self, player_repo, ctx, sample_stats, sample_fielding_positions_two_way):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id,
                           sample_stats, fielding_positions=sample_fielding_positions_two_way)

        rows = ctx.conn.execute(
            """
            SELECT * FROM player_game_fielding
            WHERE game_id = %s AND player_id = %s
            ORDER BY position
            """,
            (ctx.game_id, ctx.p1.id),
        ).fetchall()

        assert len(rows) == 2
        positions = {r["position"]: r for r in rows}
        assert positions["1b"]["putouts"] == 10
        assert positions["p"]["assists"] == 2
        assert positions["p"]["errors"] == 1

    def test_insert_no_fielding_positions(self, player_repo, ctx, sample_stats):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)

        rows = ctx.conn.execute(
            "SELECT * FROM player_game_fielding WHERE game_id = %s AND player_id = %s",
            (ctx.game_id, ctx.p1.id),
        ).fetchall()
        assert len(rows) == 0

    def test_insert_fielding_positions_idempotent(self, player_repo, ctx, sample_stats, sample_fielding_positions):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id,
                           sample_stats, fielding_positions=sample_fielding_positions)

        updated_fs = FieldingStats()
        updated_fs.putouts = 3
        updated_fs.assists = 7
        updated_fs.errors  = 1

        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id,
                           sample_stats, fielding_positions=[("ss", updated_fs)])

        rows = ctx.conn.execute(
            "SELECT * FROM player_game_fielding WHERE game_id = %s AND player_id = %s",
            (ctx.game_id, ctx.p1.id),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["putouts"] == 3
        assert rows[0]["assists"] == 7
        assert rows[0]["errors"] == 1

    def test_fielding_positions_isolated_per_player(self, player_repo, ctx, sample_stats):
        ss_stats = FieldingStats(); ss_stats.putouts = 1; ss_stats.assists = 5
        cf_stats = FieldingStats(); cf_stats.putouts = 3; cf_stats.assists = 0

        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id,
                           sample_stats, fielding_positions=[("ss", ss_stats)])
        player_repo.insert(ctx.game_id, ctx.p2.id, ctx.home.id, ctx.away.id,
                           sample_stats, fielding_positions=[("cf", cf_stats)])

        p1_rows = ctx.conn.execute(
            "SELECT * FROM player_game_fielding WHERE game_id = %s AND player_id = %s",
            (ctx.game_id, ctx.p1.id),
        ).fetchall()
        p2_rows = ctx.conn.execute(
            "SELECT * FROM player_game_fielding WHERE game_id = %s AND player_id = %s",
            (ctx.game_id, ctx.p2.id),
        ).fetchall()

        assert len(p1_rows) == 1 and p1_rows[0]["position"] == "ss"
        assert len(p2_rows) == 1 and p2_rows[0]["position"] == "cf"


# ---------------------------------------------------------------------------
# TestPlayerGameRepositoryDeleteGameStats
# ---------------------------------------------------------------------------


class TestPlayerGameRepositoryDeleteGameStats:

    def test_delete_cleans_player_game_stats(self, player_repo, ctx, sample_stats):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)
        player_repo.delete_game_stats(ctx.game_id)

        count = ctx.conn.execute(
            "SELECT COUNT(*) AS n FROM player_game_stats WHERE game_id = %s",
            (ctx.game_id,),
        ).fetchone()["n"]
        assert count == 0

    def test_delete_cleans_player_game_fielding(self, player_repo, ctx, sample_stats, sample_fielding_positions):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id,
                           sample_stats, fielding_positions=sample_fielding_positions)
        player_repo.delete_game_stats(ctx.game_id)

        count = ctx.conn.execute(
            "SELECT COUNT(*) AS n FROM player_game_fielding WHERE game_id = %s",
            (ctx.game_id,),
        ).fetchone()["n"]
        assert count == 0

    def test_delete_only_affects_specified_game(self, player_repo, ctx, sample_stats,
                                                sample_fielding_positions, factory):
        import uuid
        game2_id = str(uuid.uuid4())
        ctx.conn.execute(
            "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (game2_id, "2025-04-02", ctx.season.id, ctx.home.id, ctx.away.id),
        )

        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id,
                           sample_stats, fielding_positions=sample_fielding_positions)
        player_repo.insert(game2_id, ctx.p1.id, ctx.home.id, ctx.away.id,
                           sample_stats, fielding_positions=sample_fielding_positions)

        player_repo.delete_game_stats(ctx.game_id)

        assert ctx.conn.execute(
            "SELECT COUNT(*) AS n FROM player_game_fielding WHERE game_id = %s",
            (ctx.game_id,),
        ).fetchone()["n"] == 0

        assert ctx.conn.execute(
            "SELECT COUNT(*) AS n FROM player_game_fielding WHERE game_id = %s",
            (game2_id,),
        ).fetchone()["n"] == 1


# ---------------------------------------------------------------------------
# TestPlayerGameRepositoryGetForGame
# ---------------------------------------------------------------------------


class TestPlayerGameRepositoryGetForGame:

    def test_get_for_game_existing(self, player_repo, ctx, sample_stats):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)
        retrieved = player_repo.get_for_game(ctx.game_id, ctx.p1.id)
        assert retrieved is not None
        assert isinstance(retrieved, Stats)

    def test_get_for_game_batting_stats(self, player_repo, ctx, sample_stats):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)
        retrieved = player_repo.get_for_game(ctx.game_id, ctx.p1.id)
        assert retrieved.batting.at_bats == 4
        assert retrieved.batting.hits == 2
        assert retrieved.batting.doubles == 1
        assert retrieved.batting.home_runs == 1
        assert retrieved.batting.rbi == 3
        assert retrieved.batting.runs == 2

    def test_get_for_game_pitching_stats(self, player_repo, ctx, sample_stats):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)
        retrieved = player_repo.get_for_game(ctx.game_id, ctx.p1.id)
        assert retrieved.pitching.outs == 27
        assert retrieved.pitching.hits == 5
        assert retrieved.pitching.runs == 2
        assert retrieved.pitching.strike_outs == 8
        assert retrieved.pitching.pitch_count == 95

    def test_get_for_game_fielding_stats(self, player_repo, ctx, sample_stats):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)
        retrieved = player_repo.get_for_game(ctx.game_id, ctx.p1.id)
        assert retrieved.fielding.putouts == 3
        assert retrieved.fielding.assists == 1
        assert retrieved.fielding.errors == 0
        assert retrieved.fielding.chances == 4

    def test_get_for_game_nonexistent(self, player_repo):
        assert player_repo.get_for_game("nonexistent-game", "nonexistent-player") is None

    def test_get_for_game_wrong_player(self, player_repo, ctx, sample_stats):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)
        assert player_repo.get_for_game(ctx.game_id, ctx.p2.id) is None

    def test_get_for_game_wrong_game(self, player_repo, ctx, sample_stats):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)
        assert player_repo.get_for_game("wrong-game-id", ctx.p1.id) is None


# ---------------------------------------------------------------------------
# TestPlayerGameRepositoryFetchPlayerGames
# ---------------------------------------------------------------------------


class TestPlayerGameRepositoryFetchPlayerGames:

    def test_fetch_player_games_single(self, player_repo, ctx, sample_stats):
        player_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)
        games = player_repo.fetch_player_games(ctx.p1.id)
        assert len(games) == 1
        assert isinstance(games[0], Stats)
        assert games[0].batting.hits == 2

    def test_fetch_player_games_multiple(self, player_repo, ctx, sample_stats, factory):
        import uuid
        for i in range(5):
            gid = str(uuid.uuid4())
            ctx.conn.execute(
                "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)"
                " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (gid, f"2025-04-{i+1:02d}", ctx.season.id, ctx.home.id, ctx.away.id),
            )
            player_repo.insert(gid, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)

        games = player_repo.fetch_player_games(ctx.p1.id)
        assert len(games) == 5
        assert all(isinstance(g, Stats) for g in games)

    def test_fetch_player_games_empty(self, player_repo):
        assert player_repo.fetch_player_games("nonexistent-player") == []

    def test_fetch_player_games_ordered(self, player_games_repo, ctx, sample_stats, factory):
        import uuid
        for i in reversed(range(5)):
            gid = str(uuid.uuid4())
            ctx.conn.execute(
                "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)"
                " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (gid, f"2025-04-{i+1:02d}", ctx.season.id, ctx.home.id, ctx.away.id),
            )
            player_games_repo.insert(gid, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)

        games = player_games_repo.fetch_player_games(ctx.p1.id)
        assert len(games) == 5

    def test_fetch_player_games_different_stats(self, player_games_repo, ctx):
        import uuid
        for i in range(3):
            gid = str(uuid.uuid4())
            ctx.conn.execute(
                "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)"
                " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (gid, f"2025-04-{i+1:02d}", ctx.season.id, ctx.home.id, ctx.away.id),
            )
            s = Stats(); s.batting.hits = i; s.batting.at_bats = 4
            player_games_repo.insert(gid, ctx.p1.id, ctx.home.id, ctx.away.id, s)

        games = player_games_repo.fetch_player_games(ctx.p1.id)
        assert len(games) == 3
        assert set(g.batting.hits for g in games) == {0, 1, 2}

    def test_fetch_player_games_only_for_specific_player(self, player_games_repo, ctx, sample_stats):
        import uuid
        game2_id = str(uuid.uuid4())
        ctx.conn.execute(
            "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (game2_id, "2025-04-02", ctx.season.id, ctx.home.id, ctx.away.id),
        )
        player_games_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)
        player_games_repo.insert(ctx.game_id, ctx.p2.id, ctx.home.id, ctx.away.id, sample_stats)
        player_games_repo.insert(game2_id,    ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)

        games = player_games_repo.fetch_player_games(ctx.p1.id)
        assert len(games) == 2


# ---------------------------------------------------------------------------
# TestPlayerGameRepositoryLoadSeasonStats
# ---------------------------------------------------------------------------


class TestPlayerGameRepositoryLoadSeasonStats:

    @pytest.fixture
    def season_setup(self, db_conn, factory):
        """Four games across two seasons."""
        from types import SimpleNamespace
        import uuid

        season1 = factory.season(year=3300)
        season2 = factory.season(year=3301)
        home    = factory.team()
        away    = factory.team()
        player  = factory.player_row()

        games_s1 = []
        for i in range(3):
            gid = str(uuid.uuid4())
            db_conn.execute(
                "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)"
                " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (gid, f"2025-04-{i+1:02d}", season1.id, home.id, away.id),
            )
            games_s1.append(gid)

        game_s2 = str(uuid.uuid4())
        db_conn.execute(
            "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (game_s2, "2025-04-04", season2.id, home.id, away.id),
        )

        return SimpleNamespace(
            conn=db_conn, season1=season1, season2=season2,
            home=home, away=away, player=player,
            games_s1=games_s1, game_s2=game_s2,
        )

    def test_load_season_stats_basic(self, player_repo, season_setup):
        ss = season_setup
        for gid in ss.games_s1:
            s = Stats(); s.batting.hits = 2; s.batting.at_bats = 4
            player_repo.insert(gid, ss.player.id, ss.home.id, ss.away.id, s)

        result = player_repo.load_season_stats(ss.player.id, ss.season1.id)
        assert result.games_played == 3
        assert result.stats.batting.hits == 6
        assert result.stats.batting.at_bats == 12

    def test_load_season_stats_aggregation(self, player_repo, season_setup):
        ss = season_setup
        stats_data = [(2, 1, 4), (3, 0, 5), (1, 1, 3)]
        for gid, (hits, hrs, ab) in zip(ss.games_s1, stats_data):
            s = Stats()
            s.batting.hits = hits; s.batting.home_runs = hrs; s.batting.at_bats = ab
            player_repo.insert(gid, ss.player.id, ss.home.id, ss.away.id, s)

        result = player_repo.load_season_stats(ss.player.id, ss.season1.id)
        assert result.games_played == 3
        assert result.stats.batting.hits == 6
        assert result.stats.batting.home_runs == 2
        assert result.stats.batting.at_bats == 12

    def test_load_season_stats_different_season(self, player_repo, season_setup):
        ss = season_setup
        s1 = Stats(); s1.batting.hits = 2
        player_repo.insert(ss.games_s1[0], ss.player.id, ss.home.id, ss.away.id, s1)

        s2 = Stats(); s2.batting.hits = 3
        player_repo.insert(ss.game_s2, ss.player.id, ss.home.id, ss.away.id, s2)

        r1 = player_repo.load_season_stats(ss.player.id, ss.season1.id)
        assert r1.games_played == 1 and r1.stats.batting.hits == 2

        r2 = player_repo.load_season_stats(ss.player.id, ss.season2.id)
        assert r2.games_played == 1 and r2.stats.batting.hits == 3

    def test_load_season_stats_no_games(self, player_repo, season_setup):
        ss = season_setup
        result = player_repo.load_season_stats(ss.player.id, ss.season1.id)
        assert result.games_played == 0
        assert result.stats.batting.hits == 0

    def test_load_season_stats_pitching_aggregation(self, player_repo, season_setup):
        ss = season_setup
        for gid in ss.games_s1:
            s = Stats(); s.pitching.outs = 9; s.pitching.strike_outs = 5; s.pitching.walks = 2
            player_repo.insert(gid, ss.player.id, ss.home.id, ss.away.id, s)

        result = player_repo.load_season_stats(ss.player.id, ss.season1.id)
        assert result.stats.pitching.outs == 27
        assert result.stats.pitching.strike_outs == 15
        assert result.stats.pitching.walks == 6

    def test_load_season_stats_fielding_aggregation(self, player_repo, season_setup):
        ss = season_setup
        for gid in ss.games_s1:
            s = Stats(); s.fielding.putouts = 3; s.fielding.assists = 2; s.fielding.errors = 1
            player_repo.insert(gid, ss.player.id, ss.home.id, ss.away.id, s)

        result = player_repo.load_season_stats(ss.player.id, ss.season1.id)
        assert result.stats.fielding.putouts == 9
        assert result.stats.fielding.assists == 6
        assert result.stats.fielding.errors == 3


# ---------------------------------------------------------------------------
# TestPlayerGameRepositoryRowToStats
# ---------------------------------------------------------------------------


class TestPlayerGameRepositoryRowToStats:

    def test_row_to_stats_round_trip(self, player_games_repo, ctx, sample_stats):
        player_games_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, sample_stats)
        retrieved = player_games_repo.get_for_game(ctx.game_id, ctx.p1.id)

        assert retrieved.batting.at_bats    == sample_stats.batting.at_bats
        assert retrieved.batting.hits       == sample_stats.batting.hits
        assert retrieved.batting.doubles    == sample_stats.batting.doubles
        assert retrieved.batting.home_runs  == sample_stats.batting.home_runs
        assert retrieved.batting.rbi        == sample_stats.batting.rbi
        assert retrieved.pitching.outs      == sample_stats.pitching.outs
        assert retrieved.pitching.hits      == sample_stats.pitching.hits
        assert retrieved.pitching.strike_outs == sample_stats.pitching.strike_outs
        assert retrieved.pitching.pitch_count == sample_stats.pitching.pitch_count
        assert retrieved.fielding.putouts   == sample_stats.fielding.putouts
        assert retrieved.fielding.assists   == sample_stats.fielding.assists
        assert retrieved.fielding.errors    == sample_stats.fielding.errors

    def test_row_to_stats_calculates_chances(self, player_games_repo, ctx):
        s = Stats(); s.fielding.putouts = 5; s.fielding.assists = 3; s.fielding.errors = 2
        player_games_repo.insert(ctx.game_id, ctx.p1.id, ctx.home.id, ctx.away.id, s)

        retrieved = player_games_repo.get_for_game(ctx.game_id, ctx.p1.id)
        assert retrieved.fielding.chances == 10
