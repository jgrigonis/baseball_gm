# tests/db/test_migration_149_starter_leash_tens.py

from src.db.migration_files import migration_149_starter_leash_tens as m
from src.db.repositories.gm_repo import GMRepository


def test_old_leashes_move_one_step_longer(db_conn, factory):
    league = factory.league(state="season")
    teams = [factory.team() for _ in range(5)]
    gms = [factory.gm(team=t, league=league, is_ai=True) for t in teams]
    arm_id = factory.player_row().id
    db_conn.execute(
        "ALTER TABLE gm_profiles DROP CONSTRAINT gm_profiles_starter_usage_check"
    )
    db_conn.execute(
        "ALTER TABLE pitcher_leashes DROP CONSTRAINT pitcher_leashes_pitches_check"
    )
    old = ("75", "85", "95", "105", "115")
    for gm, usage in zip(gms, old):
        db_conn.execute(
            "UPDATE gm_profiles SET starter_usage = %s WHERE gm_id = %s",
            (usage, gm.id),
        )
    db_conn.execute(
        "INSERT INTO pitcher_leashes (team_id, player_id, pitches) VALUES (%s, %s, '75')",
        (teams[0].id, arm_id),
    )

    m.upgrade(db_conn)

    got = [GMRepository(db_conn).get_profile(g.id)["starter_usage"] for g in gms]
    assert got == ["90", "100", "110", "120", "120"]
    assert GMRepository(db_conn).pitcher_leashes(teams[0].id) == {arm_id: "90"}
