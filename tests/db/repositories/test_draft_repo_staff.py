# tests/db/repositories/test_draft_repo_staff.py
"""DraftRepository.get_staff_groups: which pitchers a team uses in its
rotation (sp) and bullpen (rp), from active assignments only."""

from src.db.repositories.draft_repo import DraftRepository


def _rotation(db, team, season, player, date, end=None):
    db.execute(
        """INSERT INTO team_rotations
               (team_id, season_id, player_id, rotation_order, effective_date, end_date)
           VALUES (%s, %s, %s, 1, %s, %s)""",
        (team.id, season.id, player.id, date, end),
    )


def _bullpen(db, team, season, player, date, end=None):
    db.execute(
        """INSERT INTO bullpen_roles
               (team_id, player_id, season_id, role, effective_date, end_date)
           VALUES (%s, %s, %s, 'Closer', %s, %s)""",
        (team.id, player.id, season.id, date, end),
    )


def test_staff_groups(db_conn, factory):
    season = factory.season()
    team, other = factory.team(), factory.team()
    starter, closer, moved, ended, elsewhere = (factory.player_row() for _ in range(5))
    _rotation(db_conn, team, season, starter, "2025-04-01")
    _bullpen(db_conn, team, season, closer, "2025-04-01")
    # Started, then moved to the bullpen without the old row being ended
    _rotation(db_conn, team, season, moved, "2025-04-01")
    _bullpen(db_conn, team, season, moved, "2025-06-01")
    # No longer in the rotation
    _rotation(db_conn, team, season, ended, "2025-04-01", end="2025-05-01")
    _rotation(db_conn, other, season, elsewhere, "2025-04-01")

    groups = DraftRepository(db_conn).get_staff_groups([team.id])

    assert groups == {starter.id: "sp", closer.id: "rp", moved.id: "rp"}
