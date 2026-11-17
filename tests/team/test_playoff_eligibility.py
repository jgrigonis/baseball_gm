# tests/team/test_playoff_eligibility.py
"""Long Form's September 1 rule (Josh, 2026-11-16): only the 40-man on
September 1 can play in the playoffs, plus one replacement for each eligible
player who's hurt."""

from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.team import playoff_eligibility as pe
from src.team.roster_limits import enforce_active_roster


def _setup(db_conn, factory, mode="longform"):
    league = factory.league(state="season", mode=mode)
    season = factory.season(year=2025)
    factory.league_season(league, season)
    team = factory.team()
    factory.league_season_team(league, season, team)
    factory.gm(team=team, league=league, is_ai=True)
    active = [factory.rated_player(team, league, 55, status="26man") for _ in range(13)]
    active += [
        factory.rated_player(team, league, 55, status="26man", pitcher=True)
        for _ in range(13)
    ]
    reserve = [factory.rated_player(team, league, 50, status="40man") for _ in range(4)]
    return league, season, team, active, reserve


def test_the_list_is_taken_on_september_1(db_conn, factory):
    league, season, team, active, reserve = _setup(db_conn, factory)
    assert pe.snapshot(db_conn, league.id, season.id, "2025-08-31") == 0
    assert pe.eligible(db_conn, season.id, team.id) is None  # everyone, until then
    assert pe.snapshot(db_conn, league.id, season.id, "2025-09-01") == 30
    assert pe.snapshot(db_conn, league.id, season.id, "2025-09-02") == 0  # once
    late = factory.rated_player(team, league, 90, status="40man")
    elig = pe.eligible(db_conn, season.id, team.id)
    assert {p.id for p in active + reserve} == elig and late.id not in elig


def test_blitz_leagues_have_no_rule(db_conn, factory):
    league, season, team, *_ = _setup(db_conn, factory, mode="blitz")
    assert pe.snapshot(db_conn, league.id, season.id, "2025-09-01") == 0


def test_a_late_signing_sits_in_the_playoffs_unless_he_replaces_a_hurt_player(
    db_conn, factory
):
    league, season, team, active, reserve = _setup(db_conn, factory)
    pe.snapshot(db_conn, league.id, season.id, "2025-09-01")
    late = factory.rated_player(team, league, 90, status="26man")
    status = PlayerStatusRepository(db_conn)
    status.set_status(active[0].id, "40man")  # he took this spot
    db_conn.execute("UPDATE leagues SET state = 'playoffs' WHERE id = %s", (league.id,))
    problem = pe.problem(
        db_conn, league.id, season.id, team.id,
        status.get_by_team_and_status(team.id, "26man"),
    )  # fmt: skip
    assert "Not playoff eligible" in problem
    moves = enforce_active_roster(db_conn, league.id, team.id, "2025-10-01", True)
    assert status.get_status(late.id) == "40man"
    assert any(m["why"] == "not_eligible" for m in moves)

    # An eligible player gets hurt: the late signing may replace him.
    log = db_conn.execute(
        """INSERT INTO player_injury_log (player_id, team_id, injury_date, severity, games_missed)
           VALUES (%s, %s, '2025-09-30', 'moderate', 30) RETURNING id""",
        (active[1].id, team.id),
    ).fetchone()["id"]
    db_conn.execute(
        """INSERT INTO player_injuries (player_id, league_id, return_date, log_id)
           VALUES (%s, %s, '2099-01-01', %s)""",
        (active[1].id, league.id, log),
    )
    elig = pe.eligible(db_conn, season.id, team.id)
    assert pe.replacements_allowed(db_conn, league.id, team.id, elig, "2025-10-01") == 1
    status.set_status(late.id, "26man")
    assert (
        pe.problem(
            db_conn,
            league.id,
            season.id,
            team.id,
            status.get_by_team_and_status(team.id, "26man"),
        )  # fmt: skip
        is None
    )
