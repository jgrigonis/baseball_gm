# tests/db/test_team_rotations_repo.py
"""Unit tests for TeamRotationsRepository."""

import pytest

from src.db.repositories.team_rotations_repo import TeamRotationsRepository


@pytest.fixture
def rot(db_conn, factory):
    """
    Seed season, team, and 7 players via the factory.
    Returns a namespace with stable references tests can use.
    """
    from types import SimpleNamespace

    season = factory.season(year=2024)
    team = factory.team(city="Boston", mascot="Red Sox")

    players = []
    for i in range(1, 8):
        pid = f"{team.id[:8]}-p{i:03d}"
        db_conn.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws, position)"
            " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (pid, f"First{i}", f"Last{i}", "R", "R", "sp"),
        )
        db_conn.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)"
            " ON CONFLICT DO NOTHING",
            (team.id, pid),
        )
        players.append(pid)

    return SimpleNamespace(
        season_id=season.id,
        team_id=team.id,
        players=players,  # [p1..p7] — players[0] == "tst-rot-p001", etc.
        p=players,  # shorthand: rot.p[0] .. rot.p[6]
    )


@pytest.fixture
def repo(db_conn):
    return TeamRotationsRepository(db_conn, league_id="test")


class TestSetRotation:
    def test_set_rotation_success(self, repo, db_conn, rot):
        rotation_ids = rot.p[:5]
        repo.set_rotation(rot.team_id, rot.season_id, rotation_ids, "2024-04-01")

        cursor = db_conn.execute(
            """SELECT player_id, rotation_order FROM team_rotations
               WHERE team_id = %s AND season_id = %s
               ORDER BY rotation_order""",
            (rot.team_id, rot.season_id),
        )
        rows = cursor.fetchall()

        assert len(rows) == 5
        assert (rows[0]["player_id"], rows[0]["rotation_order"]) == (rot.p[0], 1)
        assert (rows[1]["player_id"], rows[1]["rotation_order"]) == (rot.p[1], 2)
        assert (rows[4]["player_id"], rows[4]["rotation_order"]) == (rot.p[4], 5)


class TestGetCurrentRotation:
    def test_get_current_rotation_success(self, repo, rot):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        rotation = repo.get_current_rotation(rot.team_id, rot.season_id, "2024-04-15")

        assert len(rotation) == 5
        assert rotation[0]["player_id"] == rot.p[0]
        assert rotation[0]["rotation_order"] == 1
        assert rotation[4]["player_id"] == rot.p[4]
        assert rotation[4]["rotation_order"] == 5

    def test_get_current_rotation_empty(self, repo, rot):
        rotation = repo.get_current_rotation(rot.team_id, rot.season_id, "2024-04-01")
        assert rotation == []

    def test_get_current_rotation_respects_effective_date(self, repo, rot):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        rotation = repo.get_current_rotation(rot.team_id, rot.season_id, "2024-03-15")
        assert rotation == []

        rotation = repo.get_current_rotation(rot.team_id, rot.season_id, "2024-04-15")
        assert len(rotation) == 5

    def test_get_current_rotation_respects_end_date(self, repo, db_conn, rot):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        db_conn.execute(
            """UPDATE team_rotations SET end_date = %s
               WHERE player_id = %s AND team_id = %s AND season_id = %s""",
            ("2024-05-01", rot.p[2], rot.team_id, rot.season_id),
        )

        rotation = repo.get_current_rotation(rot.team_id, rot.season_id, "2024-04-15")
        assert len(rotation) == 5

        rotation = repo.get_current_rotation(rot.team_id, rot.season_id, "2024-05-15")
        assert len(rotation) == 4
        assert rot.p[2] not in [p["player_id"] for p in rotation]


class TestGetNextStarter:
    def test_get_next_starter_no_previous_games(self, repo, rot):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")
        assert (
            repo.get_next_starter(rot.team_id, rot.season_id, "2024-04-15") == rot.p[0]
        )

    def test_get_next_starter_with_previous_game(self, repo, db_conn, rot, factory):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        opp = factory.team(city="New York", mascot="Yankees")
        game_id = "tst-rot-g1"
        db_conn.execute(
            "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (game_id, "2024-04-02", rot.season_id, rot.team_id, opp.id),
        )
        db_conn.execute(
            """INSERT INTO player_game_stats
               (game_id, player_id, team_id, opponent_team_id, pitch_game_started)
               VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (game_id, rot.p[0], rot.team_id, opp.id, 1),
        )

        assert (
            repo.get_next_starter(rot.team_id, rot.season_id, "2024-04-03") == rot.p[1]
        )

    def test_get_next_starter_wraps_around(self, repo, db_conn, rot, factory):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        opp = factory.team(city="Chicago", mascot="Cubs")
        game_id = "tst-rot-g2"
        db_conn.execute(
            "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (game_id, "2024-04-02", rot.season_id, rot.team_id, opp.id),
        )
        db_conn.execute(
            """INSERT INTO player_game_stats
               (game_id, player_id, team_id, opponent_team_id, pitch_game_started)
               VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (game_id, rot.p[4], rot.team_id, opp.id, 1),
        )

        assert (
            repo.get_next_starter(rot.team_id, rot.season_id, "2024-04-03") == rot.p[0]
        )

    def test_get_next_starter_no_rotation(self, repo, rot):
        assert repo.get_next_starter(rot.team_id, rot.season_id, "2024-04-01") is None


class TestUpdateRotation:
    def test_update_rotation_success(self, repo, db_conn, rot):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        repo.update_rotation(rot.team_id, rot.season_id, rot.p[2], 1, "2024-05-01")

        cursor = db_conn.execute(
            """SELECT end_date FROM team_rotations
               WHERE player_id = %s AND rotation_order = %s AND effective_date = %s""",
            (rot.p[2], 3, "2024-04-01"),
        )
        row = cursor.fetchone()
        assert row["end_date"] == "2024-05-01"

        cursor = db_conn.execute(
            """SELECT rotation_order, end_date FROM team_rotations
               WHERE player_id = %s AND effective_date = %s""",
            (rot.p[2], "2024-05-01"),
        )
        row = cursor.fetchone()
        assert row["rotation_order"] == 1
        assert row["end_date"] is None

    def test_update_rotation_same_order_no_change(self, repo, db_conn, rot):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        repo.update_rotation(rot.team_id, rot.season_id, rot.p[2], 3, "2024-05-01")

        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM team_rotations WHERE player_id = %s", (rot.p[2],)
        ).fetchone()["n"]
        assert count == 1


class TestRemoveFromRotation:
    def test_remove_from_rotation_success(self, repo, db_conn, rot):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        repo.remove_from_rotation(rot.team_id, rot.season_id, rot.p[2], "2024-05-01")

        row = db_conn.execute(
            """SELECT end_date FROM team_rotations
               WHERE player_id = %s AND team_id = %s AND season_id = %s""",
            (rot.p[2], rot.team_id, rot.season_id),
        ).fetchone()
        assert row["end_date"] == "2024-05-01"

        rotation = repo.get_current_rotation(rot.team_id, rot.season_id, "2024-05-15")
        assert rot.p[2] not in [p["player_id"] for p in rotation]

    def test_remove_from_rotation_not_in_rotation(self, repo, rot):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        with pytest.raises(ValueError, match="not in active rotation"):
            repo.remove_from_rotation(
                rot.team_id, rot.season_id, rot.p[5], "2024-05-01"
            )


class TestAddToRotation:
    def test_add_to_rotation_success(self, repo, rot):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        repo.add_to_rotation(rot.team_id, rot.season_id, rot.p[5], 6, "2024-05-01")

        rotation = repo.get_current_rotation(rot.team_id, rot.season_id, "2024-05-15")
        assert len(rotation) == 6
        assert rotation[5]["player_id"] == rot.p[5]
        assert rotation[5]["rotation_order"] == 6

    def test_add_to_rotation_shifts_existing(self, repo, rot):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        repo.add_to_rotation(rot.team_id, rot.season_id, rot.p[5], 3, "2024-05-01")

        rotation = repo.get_current_rotation(rot.team_id, rot.season_id, "2024-05-15")
        assert len(rotation) == 6

        by_player = {p["player_id"]: p["rotation_order"] for p in rotation}
        assert by_player[rot.p[5]] == 3
        assert by_player[rot.p[2]] == 4
        assert by_player[rot.p[3]] == 5
        assert by_player[rot.p[4]] == 6

    def test_add_to_rotation_already_in_rotation(self, repo, rot):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        with pytest.raises(ValueError, match="already in active rotation"):
            repo.add_to_rotation(rot.team_id, rot.season_id, rot.p[2], 6, "2024-05-01")


class TestSwapRotationSpots:
    def test_swap_rotation_spots_success(self, repo, rot):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        repo.swap_rotation_spots(
            rot.team_id, rot.season_id, rot.p[0], rot.p[4], "2024-05-01"
        )

        rotation = repo.get_current_rotation(rot.team_id, rot.season_id, "2024-05-15")
        by_player = {p["player_id"]: p["rotation_order"] for p in rotation}
        assert by_player[rot.p[0]] == 5
        assert by_player[rot.p[4]] == 1

    def test_swap_rotation_spots_player1_not_in_rotation(self, repo, rot):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        with pytest.raises(ValueError, match="not in active rotation"):
            repo.swap_rotation_spots(
                rot.team_id, rot.season_id, rot.p[5], rot.p[0], "2024-05-01"
            )

    def test_swap_rotation_spots_player2_not_in_rotation(self, repo, rot):
        repo.set_rotation(rot.team_id, rot.season_id, rot.p[:5], "2024-04-01")

        with pytest.raises(ValueError, match="not in active rotation"):
            repo.swap_rotation_spots(
                rot.team_id, rot.season_id, rot.p[0], rot.p[6], "2024-05-01"
            )
