# tests/db/repositories/test_player_repo.py
import pytest
import uuid
from datetime import datetime

from src.db.repositories.player_repo import PlayerRepository
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills


@pytest.fixture
def player_repo(db_conn):
    return PlayerRepository(db_conn)


@pytest.fixture
def sample_skills():
    return PlayerSkills(
        clutch=75,
        speed=80,
        power=70,
        eye=65,
        contact=85,
        base_running=78,
        bunting=50,
        catching=60,
        infield=75,
        outfield=80,
        arm=70,
        accuracy=75,
        stamina=80,
        recovery=70,
        ground_balls=65,
        strikes=75,
    )


@pytest.fixture
def ctx(db_conn, factory):
    """Unique player IDs + season per test — no cross-run collisions."""
    from types import SimpleNamespace

    league = factory.league()
    season = factory.season()
    # Generate IDs only — don't pre-insert players, so each test controls insertion
    p1 = SimpleNamespace(id=str(uuid.uuid4()))
    p2 = SimpleNamespace(id=str(uuid.uuid4()))
    return SimpleNamespace(
        conn=db_conn, season=season, p1=p1, p2=p2, league_id=league.id
    )


# ---------------------------------------------------------------------------
# TestPlayerRepositoryInsert
# ---------------------------------------------------------------------------


class TestPlayerRepositoryInsert:

    def test_insert_new_player(self, player_repo, ctx, sample_skills):
        player_repo.insert(
            ctx.p1.id, "Mike", "Trout", "R", "R", "of", sample_skills, ctx.league_id
        )

        row = ctx.conn.execute(
            "SELECT * FROM players WHERE id = %s", (ctx.p1.id,)
        ).fetchone()
        assert row is not None
        assert row["first_name"] == "Mike"
        assert row["last_name"] == "Trout"
        assert row["bats"] == "R"
        assert row["throws"] == "R"
        assert row["position"] == "of"

        skills_row = ctx.conn.execute(
            "SELECT * FROM player_skills WHERE player_id = %s", (ctx.p1.id,)
        ).fetchone()
        assert skills_row is not None
        assert skills_row["clutch"] == 75
        assert skills_row["speed"] == 80
        assert skills_row["power"] == 70

    def test_insert_idempotent(self, player_repo, ctx, db_conn, sample_skills):
        player_repo.insert(
            ctx.p1.id, "Mike", "Trout", "r", "r", "rf", sample_skills, ctx.league_id
        )
        player_repo.insert(
            ctx.p1.id, "Michael", "Trout", "r", "r", "rf", sample_skills, ctx.league_id
        )

        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM players WHERE id = %s", (ctx.p1.id,)
        ).fetchone()["n"]
        assert count == 1

        row = db_conn.execute(
            "SELECT first_name FROM players WHERE id = %s", (ctx.p1.id,)
        ).fetchone()
        assert row["first_name"] == "Mike"

    def test_insert_multiple_players(
        self, player_repo, ctx, db_conn, sample_skills, factory
    ):
        ids = [ctx.p1.id, ctx.p2.id, factory.player_row().id]
        for pid in ids:
            player_repo.insert(
                pid, "First", "Last", "R", "R", "rf", sample_skills, ctx.league_id
            )

        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM players WHERE id = ANY(%s)", (ids,)
        ).fetchone()["n"]
        assert count == 3

    def test_insert_different_handedness(
        self, player_repo, ctx, db_conn, sample_skills
    ):
        import uuid

        p3_id = str(uuid.uuid4())
        player_repo.insert(
            ctx.p1.id, "A", "B", "r", "r", "1b", sample_skills, ctx.league_id
        )
        player_repo.insert(
            ctx.p2.id, "C", "D", "L", "L", "of", sample_skills, ctx.league_id
        )
        player_repo.insert(p3_id, "E", "F", "S", "R", "c", sample_skills, ctx.league_id)

        rows = db_conn.execute(
            "SELECT id, bats FROM players WHERE id = ANY(%s) ORDER BY bats",
            ([ctx.p1.id, ctx.p2.id, p3_id],),
        ).fetchall()
        bats = {r["bats"] for r in rows}
        assert bats == {"R", "L", "S"}

    def test_insert_creates_timestamp(self, player_repo, ctx, db_conn, sample_skills):
        before = datetime.now()
        player_repo.insert(
            ctx.p1.id, "First", "Player", "r", "r", "1b", sample_skills, ctx.league_id
        )
        after = datetime.now()

        row = db_conn.execute(
            "SELECT updated_at FROM player_skills WHERE player_id = %s", (ctx.p1.id,)
        ).fetchone()
        assert row["updated_at"] is not None
        ts = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
        assert ts.replace(tzinfo=None) >= before.replace(microsecond=0) or ts.replace(
            tzinfo=None
        ) <= after.replace(microsecond=0)


# ---------------------------------------------------------------------------
# TestPlayerRepositoryUpdateSkills
# ---------------------------------------------------------------------------


class TestPlayerRepositoryUpdateSkills:

    def test_update_skills(self, player_repo, ctx, db_conn, sample_skills):
        player_repo.insert(
            ctx.p1.id, "First", "Player", "r", "r", "1b", sample_skills, ctx.league_id
        )

        new_skills = PlayerSkills(
            clutch=80,
            speed=85,
            power=75,
            eye=70,
            contact=90,
            base_running=83,
            bunting=55,
            catching=65,
            infield=80,
            outfield=85,
            arm=75,
            accuracy=80,
            stamina=85,
            recovery=75,
            ground_balls=70,
            strikes=80,
        )
        player_repo.update_skills(ctx.p1.id, new_skills)

        row = db_conn.execute(
            "SELECT * FROM player_skills WHERE player_id = %s", (ctx.p1.id,)
        ).fetchone()
        assert row["clutch"] == 80
        assert row["speed"] == 85
        assert row["power"] == 75
        assert row["contact"] == 90

    def test_update_skills_creates_new_timestamp(
        self, player_repo, ctx, db_conn, sample_skills
    ):
        player_repo.insert(
            ctx.p1.id, "First", "Player", "r", "r", "1b", sample_skills, ctx.league_id
        )

        original_ts = db_conn.execute(
            "SELECT updated_at FROM player_skills WHERE player_id = %s", (ctx.p1.id,)
        ).fetchone()["updated_at"]

        import time

        time.sleep(0.01)

        new_skills = PlayerSkills({**sample_skills.as_dict(), "speed": 85})
        player_repo.update_skills(ctx.p1.id, new_skills)

        new_ts = db_conn.execute(
            "SELECT updated_at FROM player_skills WHERE player_id = %s", (ctx.p1.id,)
        ).fetchone()["updated_at"]
        assert new_ts != original_ts

    def test_update_skills_idempotent(self, player_repo, ctx, db_conn, sample_skills):
        player_repo.insert(
            ctx.p1.id, "First", "Player", "r", "r", "1b", sample_skills, ctx.league_id
        )

        for i in range(5):
            new_skills = PlayerSkills({**sample_skills.as_dict(), "speed": 85 + i})
            player_repo.update_skills(ctx.p1.id, new_skills)

        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM player_skills WHERE player_id = %s", (ctx.p1.id,)
        ).fetchone()["n"]
        assert count == 1


# ---------------------------------------------------------------------------
# TestPlayerRepositorySnapshotSkills
# ---------------------------------------------------------------------------


class TestPlayerRepositorySnapshotSkills:

    def test_snapshot_skills(self, player_repo, ctx, db_conn, sample_skills):
        player_repo.insert(
            ctx.p1.id, "First", "Player", "r", "r", "1b", sample_skills, ctx.league_id
        )
        player_repo.snapshot_skills(ctx.p1.id, ctx.season.id)

        row = db_conn.execute(
            "SELECT * FROM player_skills_history WHERE player_id = %s AND season_id = %s",
            (ctx.p1.id, ctx.season.id),
        ).fetchone()
        assert row is not None
        assert row["clutch"] == 75
        assert row["speed"] == 80
        assert row["power"] == 70

    def test_snapshot_skills_multiple_seasons(
        self, player_repo, ctx, db_conn, sample_skills, factory
    ):
        player_repo.insert(
            ctx.p1.id, "First", "Player", "r", "r", "1b", sample_skills, ctx.league_id
        )

        seasons = [factory.season(year=3400 + i) for i in range(3)]
        for i, s in enumerate(seasons):
            updated = PlayerSkills({**sample_skills.as_dict(), "speed": 80 + i})
            player_repo.update_skills(ctx.p1.id, updated)
            player_repo.snapshot_skills(ctx.p1.id, s.id)

        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM player_skills_history WHERE player_id = %s",
            (ctx.p1.id,),
        ).fetchone()["n"]
        assert count == 3

    def test_snapshot_skills_idempotent(self, player_repo, ctx, db_conn, sample_skills):
        player_repo.insert(
            ctx.p1.id, "First", "Player", "R", "R", "1b", sample_skills, ctx.league_id
        )
        player_repo.snapshot_skills(ctx.p1.id, ctx.season.id)

        new_skills = PlayerSkills({**sample_skills.as_dict(), "speed": 85})
        player_repo.update_skills(ctx.p1.id, new_skills)
        player_repo.snapshot_skills(ctx.p1.id, ctx.season.id)

        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM player_skills_history WHERE player_id = %s AND season_id = %s",
            (ctx.p1.id, ctx.season.id),
        ).fetchone()["n"]
        assert count == 1

        row = db_conn.execute(
            "SELECT speed FROM player_skills_history WHERE player_id = %s AND season_id = %s",
            (ctx.p1.id, ctx.season.id),
        ).fetchone()
        assert row["speed"] == 85

    def test_snapshot_skills_creates_timestamp(
        self, player_repo, ctx, db_conn, sample_skills
    ):
        player_repo.insert(
            ctx.p1.id, "First", "Player", "r", "r", "1b", sample_skills, ctx.league_id
        )
        player_repo.snapshot_skills(ctx.p1.id, ctx.season.id)

        row = db_conn.execute(
            "SELECT recorded_at FROM player_skills_history WHERE player_id = %s AND season_id = %s",
            (ctx.p1.id, ctx.season.id),
        ).fetchone()
        assert row["recorded_at"] is not None


# ---------------------------------------------------------------------------
# TestPlayerRepositoryLookUp
# ---------------------------------------------------------------------------


class TestPlayerRepositoryLookUp:

    def test_look_up_existing_player(self, player_repo, ctx, sample_skills):
        player_repo.insert(
            ctx.p1.id, "Mike", "Trout", "r", "r", "rf", sample_skills, ctx.league_id
        )
        record = player_repo.look_up(ctx.p1.id)

        assert record is not None
        assert isinstance(record, PlayerRecord)
        assert record.id == ctx.p1.id
        assert record.first_name == "Mike"
        assert record.last_name == "Trout"
        assert record.bats == "R"
        assert record.throws == "R"
        assert record.position == "rf"

    def test_look_up_skills(self, player_repo, ctx, sample_skills):
        player_repo.insert(
            ctx.p1.id, "Mike", "Trout", "R", "R", "rf", sample_skills, ctx.league_id
        )
        record = player_repo.look_up(ctx.p1.id)

        assert isinstance(record.skills, PlayerSkills)
        assert record.skills["clutch"] == 75
        assert record.skills["speed"] == 80
        assert record.skills["power"] == 70
        assert record.skills["contact"] == 85

    def test_look_up_nonexistent_player(self, player_repo):
        assert player_repo.look_up("nonexistent") is None

    def test_look_up_player_without_skills(self, player_repo, ctx, db_conn):
        db_conn.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws, position)"
            " VALUES (%s, 'Mike', 'Trout', 'R', 'R', 'of')",
            (ctx.p1.id,),
        )
        with pytest.raises(ValueError, match="has no skills record"):
            player_repo.look_up(ctx.p1.id)

    def test_look_up_returns_current_skills(self, player_repo, ctx, sample_skills):
        player_repo.insert(
            ctx.p1.id, "Mike", "Trout", "r", "r", "rf", sample_skills, ctx.league_id
        )
        new_skills = PlayerSkills({**sample_skills.as_dict(), "speed": 85})
        player_repo.update_skills(ctx.p1.id, new_skills)

        record = player_repo.look_up(ctx.p1.id)
        assert record.skills["speed"] == 85


# ---------------------------------------------------------------------------
# TestPlayerRepositoryGetSkillHistory
# ---------------------------------------------------------------------------


class TestPlayerRepositoryGetSkillHistory:

    def test_get_skill_history_empty(self, player_repo, ctx, sample_skills):
        player_repo.insert(
            ctx.p1.id, "Mike", "Trout", "r", "r", "rf", sample_skills, ctx.league_id
        )
        assert player_repo.get_skill_history(ctx.p1.id) == []

    def test_get_skill_history_single_season(self, player_repo, ctx, sample_skills):
        player_repo.insert(
            ctx.p1.id, "Mike", "Trout", "r", "r", "rf", sample_skills, ctx.league_id
        )
        player_repo.snapshot_skills(ctx.p1.id, ctx.season.id)

        history = player_repo.get_skill_history(ctx.p1.id)
        assert len(history) == 1
        assert history[0]["season_id"] == ctx.season.id
        assert history[0]["clutch"] == 75
        assert history[0]["speed"] == 80

    def test_get_skill_history_multiple_seasons(
        self, player_repo, ctx, sample_skills, factory
    ):
        player_repo.insert(
            ctx.p1.id, "Mike", "Trout", "r", "r", "rf", sample_skills, ctx.league_id
        )

        seasons = [factory.season(year=3500 + i) for i in range(3)]
        for i, s in enumerate(seasons):
            updated = PlayerSkills({**sample_skills.as_dict(), "speed": 80 + i})
            player_repo.update_skills(ctx.p1.id, updated)
            player_repo.snapshot_skills(ctx.p1.id, s.id)

        history = player_repo.get_skill_history(ctx.p1.id)
        assert len(history) == 3

    def test_get_skill_history_ordered(self, player_repo, ctx, sample_skills, factory):
        player_repo.insert(
            ctx.p1.id, "Mike", "Trout", "r", "r", "rf", sample_skills, ctx.league_id
        )

        seasons = [factory.season(year=3600 + i) for i in [2, 0, 1]]
        for s in seasons:
            player_repo.snapshot_skills(ctx.p1.id, s.id)

        history = player_repo.get_skill_history(ctx.p1.id)
        season_ids = [h["season_id"] for h in history]
        assert season_ids == sorted(season_ids)

    def test_get_skill_history_shows_progression(
        self, player_repo, ctx, sample_skills, factory
    ):
        player_repo.insert(
            ctx.p1.id, "Mike", "Trout", "R", "R", "of", sample_skills, ctx.league_id
        )

        seasons = [factory.season(year=3700 + i) for i in range(3)]
        expected_speeds = {}
        for i, s in enumerate(seasons):
            speed = 75 + i * 5
            new_skills = PlayerSkills({**sample_skills.as_dict(), "speed": speed})
            player_repo.update_skills(ctx.p1.id, new_skills)
            player_repo.snapshot_skills(ctx.p1.id, s.id)
            expected_speeds[s.id] = speed

        history = player_repo.get_skill_history(ctx.p1.id)
        assert len(history) == 3
        actual_speeds = {h["season_id"]: h["speed"] for h in history}
        assert actual_speeds == expected_speeds


# ---------------------------------------------------------------------------
# TestPlayerRepositoryExists
# ---------------------------------------------------------------------------


class TestPlayerRepositoryExists:

    def test_exists_true(self, player_repo, ctx, sample_skills):
        player_repo.insert(
            ctx.p1.id, "Mike", "Trout", "r", "r", "of", sample_skills, ctx.league_id
        )
        assert player_repo.exists(ctx.p1.id) is True

    def test_exists_false(self, player_repo):
        assert player_repo.exists("nonexistent") is False

    def test_exists_multiple_players(self, player_repo, ctx, sample_skills):
        player_repo.insert(
            ctx.p1.id, "Player", "One", "r", "r", "1b", sample_skills, ctx.league_id
        )
        player_repo.insert(
            ctx.p2.id, "Player", "Two", "L", "L", "rf", sample_skills, ctx.league_id
        )

        assert player_repo.exists(ctx.p1.id) is True
        assert player_repo.exists(ctx.p2.id) is True
        assert player_repo.exists("truly-nonexistent") is False


# ---------------------------------------------------------------------------
# TestPlayerRepositoryGetAllPlayers
# ---------------------------------------------------------------------------


class TestPlayerRepositoryGetAllPlayers:

    def test_get_all_players_single(self, player_repo, ctx, sample_skills):
        player_repo.insert(
            ctx.p1.id, "Mike", "Trout", "r", "r", "rf", sample_skills, ctx.league_id
        )

        players = player_repo.get_all_players()
        ids = {p.id for p in players}
        assert ctx.p1.id in ids

    def test_get_all_players_multiple(self, player_repo, ctx, sample_skills):
        p3_id = str(uuid.uuid4())
        for pid in [ctx.p1.id, ctx.p2.id, p3_id]:
            player_repo.insert(
                pid, "First", "Last", "R", "R", "rf", sample_skills, ctx.league_id
            )

        players = player_repo.get_all_players()
        ids = {p.id for p in players}
        assert {ctx.p1.id, ctx.p2.id, p3_id}.issubset(ids)
        assert all(isinstance(p, PlayerRecord) for p in players)

    def test_get_all_players_includes_skills(self, player_repo, ctx, sample_skills):
        player_repo.insert(
            ctx.p1.id, "Mike", "Trout", "R", "R", "rf", sample_skills, ctx.league_id
        )

        players = player_repo.get_all_players()
        p = next(p for p in players if p.id == ctx.p1.id)
        assert p.skills is not None
        assert isinstance(p.skills, PlayerSkills)
        assert p.skills["speed"] == 80


# ---------------------------------------------------------------------------
# TestPlayerRepositoryIntegration
# ---------------------------------------------------------------------------


class TestPlayerRepositoryIntegration:

    def test_full_player_lifecycle(self, player_repo, ctx, sample_skills, factory):
        player_repo.insert(
            ctx.p1.id, "Mike", "Trout", "R", "R", "rf", sample_skills, ctx.league_id
        )

        record = player_repo.look_up(ctx.p1.id)
        assert record.skills["speed"] == 80

        s1 = factory.season(year=3800)
        new_skills = PlayerSkills({**sample_skills.as_dict(), "speed": 78})
        player_repo.update_skills(ctx.p1.id, new_skills)
        player_repo.snapshot_skills(ctx.p1.id, s1.id)

        history = player_repo.get_skill_history(ctx.p1.id)
        assert len(history) == 1 and history[0]["speed"] == 78

        s2 = factory.season(year=3801)
        new_skills2 = PlayerSkills({**sample_skills.as_dict(), "speed": 76})
        player_repo.update_skills(ctx.p1.id, new_skills2)
        player_repo.snapshot_skills(ctx.p1.id, s2.id)

        history = player_repo.get_skill_history(ctx.p1.id)
        assert len(history) == 2
        speeds = {h["season_id"]: h["speed"] for h in history}
        assert speeds[s1.id] == 78
        assert speeds[s2.id] == 76

    def test_roster_management(self, player_repo, sample_skills, factory):
        league_id = factory.league().id
        players = [factory.player_row() for _ in range(25)]
        for i, p in enumerate(players):
            player_repo.insert(
                p.id,
                f"First{i}",
                f"Last{i}",
                "R" if i % 2 == 0 else "L",
                "R",
                "cf",
                sample_skills,
                league_id=league_id,
            )

        all_players = player_repo.get_all_players()
        ids = {p.id for p in all_players}
        inserted_ids = {p.id for p in players}
        assert inserted_ids.issubset(ids)
        assert all(p.skills is not None for p in all_players if p.id in inserted_ids)


# ---------------------------------------------------------------------------
# TestRetiredPlayersCareerStats
# ---------------------------------------------------------------------------


class TestRetiredPlayersCareerStats:

    def _season_stats(self, conn, player_id, season_id, team_id, **stats):
        cols = ["player_id", "season_id", "team_id", *stats]
        conn.execute(
            f"INSERT INTO player_season_stats ({', '.join(cols)})"
            f" VALUES ({', '.join(['%s'] * len(cols))})",
            (player_id, season_id, team_id, *stats.values()),
        )

    def test_returns_career_totals_not_final_season(self, player_repo, factory, db_conn):
        league = factory.league()
        team = factory.team()
        s1, s2 = factory.season(2025), factory.season(2026)
        player = factory.prospect(league.id)

        self._season_stats(
            db_conn, player.id, s1.id, team.id,
            bat_games_played=100, bat_ab=400, bat_hits=120, bat_home_runs=20,
        )
        self._season_stats(
            db_conn, player.id, s2.id, team.id,
            bat_games_played=50, bat_ab=200, bat_hits=50, bat_home_runs=5,
        )
        # Postseason stats should not be counted
        db_conn.execute(
            "INSERT INTO player_season_stats"
            " (player_id, season_id, team_id, is_postseason, bat_ab, bat_hits)"
            " VALUES (%s, %s, %s, TRUE, 30, 10)",
            (player.id, s2.id, team.id),
        )
        db_conn.execute(
            "INSERT INTO player_retirements (player_id, league_id, season_id, former_team_id)"
            " VALUES (%s, %s, %s, %s)",
            (player.id, league.id, s2.id, team.id),
        )

        rows = player_repo.get_retired_players_career_stats(team.id, league.id, s2.id)

        assert len(rows) == 1
        row = rows[0]
        assert row["seasons_played"] == 2
        assert row["bat_games_played"] == 150
        assert row["bat_ab"] == 600
        assert row["bat_hits"] == 170
        assert row["bat_home_runs"] == 25
        assert row["is_mine"] is True

    def test_player_with_no_stats_still_listed(self, player_repo, factory, db_conn):
        league = factory.league()
        season = factory.season()
        player = factory.prospect(league.id)
        db_conn.execute(
            "INSERT INTO player_retirements (player_id, league_id, season_id)"
            " VALUES (%s, %s, %s)",
            (player.id, league.id, season.id),
        )

        rows = player_repo.get_retired_players_career_stats(None, league.id, season.id)

        assert len(rows) == 1
        assert rows[0]["bat_ab"] is None
        assert rows[0]["seasons_played"] is None
