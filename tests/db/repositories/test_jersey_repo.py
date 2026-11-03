import uuid

import pytest

from src.db.repositories.jersey_repo import JerseyRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.team_repo import TeamRepository
from src.player import jersey_numbers as jn
from src.player.player_skills import PlayerSkills


@pytest.fixture
def env(db_conn, factory):
    league = factory.league()
    team = factory.team()
    return db_conn, factory, league, team


def _player(env, prefs, *, level=50, age=27):
    """A player on the team with no number yet, wanting `prefs`."""
    db, factory, league, team = env
    p = factory.rated_player(team, league, level=level, age=age)
    db.execute("UPDATE players SET jersey_prefs = %s WHERE id = %s", (prefs, p.id))
    return p.id


def _join(env, pid):
    db, _, _, team = env
    return JerseyRepository(db).assign(team.id, pid)


def test_insert_stores_his_prefs(db_conn, factory):
    league = factory.league()
    pid = str(uuid.uuid4())
    PlayerRepository(db_conn).insert(
        pid, "Ted", "Number", "L", "R", "lf", PlayerSkills(), league.id
    )
    row = db_conn.execute(
        "SELECT jersey_prefs FROM players WHERE id = %s", (pid,)
    ).fetchone()
    assert row["jersey_prefs"] == jn.prefs_for(pid)


def test_add_player_gives_a_number(env):
    db, factory, league, team = env
    other = factory.team()
    pid = _player(env, ["7", "17"])
    TeamRepository(db).add_player(other.id, pid)
    assert JerseyRepository(db).number_of(other.id, pid) == "7"


def test_senior_player_keeps_his_number(env):
    first = _player(env, ["7", "17"])
    second = _player(env, ["7", "27"])
    assert _join(env, first) == "7"
    assert _join(env, second) == "27"


def test_falls_back_to_any_free_number_when_his_list_is_taken(env):
    a = _player(env, ["7"])
    b = _player(env, ["7"])
    _join(env, a)
    n = _join(env, b)
    assert n not in (None, "7")


def test_assign_is_idempotent(env):
    a = _player(env, ["7", "8"])
    assert _join(env, a) == "7"
    assert _join(env, a) == "7"


def test_aging_veteran_hands_his_number_to_an_incoming_star(env, monkeypatch):
    monkeypatch.setattr(jn, "DEFER_CHANCE", 1.0)
    db, _, _, team = env
    vet = _player(env, ["24", "42"], level=55, age=36)
    _join(env, vet)
    star = _player(env, ["24"], level=80, age=26)
    assert _join(env, star) == "24"
    assert JerseyRepository(db).number_of(team.id, vet) == "42"


def test_young_holder_keeps_his_number_from_a_star(env, monkeypatch):
    monkeypatch.setattr(jn, "DEFER_CHANCE", 1.0)
    db, _, _, team = env
    kid = _player(env, ["24"], level=55, age=25)
    _join(env, kid)
    star = _player(env, ["24", "5"], level=80, age=26)
    assert _join(env, star) == "5"
    assert JerseyRepository(db).number_of(team.id, kid) == "24"


def test_veteran_keeps_his_number_from_an_ordinary_newcomer(env, monkeypatch):
    monkeypatch.setattr(jn, "DEFER_CHANCE", 1.0)
    vet = _player(env, ["24"], level=55, age=36)
    _join(env, vet)
    newcomer = _player(env, ["24", "5"], level=58, age=26)
    assert _join(env, newcomer) == "5"


def test_numbers_are_unique_on_a_team(env):
    db, _, _, team = env
    pids = [_player(env, ["7", "17", "27"]) for _ in range(30)]
    for pid in pids:
        _join(env, pid)
    numbers = JerseyRepository(db).numbers_on_team(team.id)
    assert len(numbers) == 30


def test_leaving_frees_the_number(env):
    db, _, _, team = env
    a = _player(env, ["7"])
    _join(env, a)
    TeamRepository(db).remove_player(team.id, a)
    b = _player(env, ["7"])
    assert _join(env, b) == "7"


def test_backfill_goes_by_seniority(env):
    db, factory, league, team = env
    young = _player(env, ["7", "8"], age=24)
    old = _player(env, ["7", "9"], age=34)
    JerseyRepository(db).backfill_team(team.id)
    repo = JerseyRepository(db)
    assert repo.number_of(team.id, old) == "7"
    assert repo.number_of(team.id, young) == "8"


def test_backfill_counts_seasons_with_the_team_before_age(env):
    db, factory, league, team = env
    lifer = _player(env, ["7", "8"], age=26)
    newcomer = _player(env, ["7", "9"], age=34)
    for year in (2023, 2024):
        season = factory.season(year)
        db.execute(
            "INSERT INTO player_season_stats (player_id, season_id, team_id) VALUES (%s, %s, %s)",
            (lifer, season.id, team.id),
        )
    JerseyRepository(db).backfill_team(team.id)
    assert JerseyRepository(db).number_of(team.id, lifer) == "7"
    assert JerseyRepository(db).number_of(team.id, newcomer) == "9"


def test_backfill_uses_the_id_seeded_list_when_none_is_stored(env):
    db, factory, league, team = env
    pid = factory.rated_player(team, league).id
    JerseyRepository(db).backfill_team(team.id)
    assert JerseyRepository(db).number_of(team.id, pid) == jn.prefs_for(pid)[0]


def test_migration_backfills_prefs_and_numbers(env):
    from src.db.migration_files.migration_059_jersey_numbers import upgrade

    db, factory, league, team = env
    pids = [factory.rated_player(team, league).id for _ in range(5)]
    upgrade(db)
    rows = db.execute(
        """SELECT p.jersey_prefs, tp.jersey_number FROM team_players tp
           JOIN players p ON p.id = tp.player_id WHERE tp.team_id = %s""",
        (team.id,),
    ).fetchall()
    assert len(rows) == len(pids)
    assert all(r["jersey_prefs"] and r["jersey_number"] for r in rows)
    assert len({r["jersey_number"] for r in rows}) == len(pids)


def test_only_the_40_man_wears_numbers(env):
    db, factory, league, team = env
    p = factory.rated_player(team, league, status="minors")
    assert _join(env, p.id) is None
    assert JerseyRepository(db).number_of(team.id, p.id) is None


def test_call_up_gives_a_number_and_send_down_takes_it(env):
    from src.db.repositories.player_status_repo import PlayerStatusRepository

    db, factory, league, team = env
    pid = factory.rated_player(team, league, status="minors").id
    status = PlayerStatusRepository(db)
    status.set_status(pid, "40man")
    assert JerseyRepository(db).number_of(team.id, pid) is not None
    status.bulk_set({pid: "minors"})
    assert JerseyRepository(db).number_of(team.id, pid) is None


def test_a_huge_organization_never_runs_out(env):
    db, factory, league, team = env
    for i in range(110):
        factory.rated_player(team, league, status="40man" if i < 40 else "minors")
    JerseyRepository(db).backfill_team(team.id)
    assert len(JerseyRepository(db).numbers_on_team(team.id)) == 40


def test_migration_60_takes_numbers_back_from_minor_leaguers(env):
    from src.db.migration_files.migration_060_jersey_numbers_40man import upgrade

    db, factory, league, team = env
    minor = factory.rated_player(team, league, status="minors").id
    major = factory.rated_player(team, league, status="26man").id
    db.execute(
        "UPDATE team_players SET jersey_number = '99' WHERE player_id = %s", (minor,)
    )
    upgrade(db)
    repo = JerseyRepository(db)
    assert repo.number_of(team.id, minor) is None
    assert repo.number_of(team.id, major) is not None
