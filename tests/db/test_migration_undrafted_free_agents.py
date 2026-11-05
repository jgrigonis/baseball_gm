# tests/db/test_migration_undrafted_free_agents.py
"""Migration 073: last draft's leftover prospects become free agents in
leagues past their draft, and a league mid-draft keeps its pool."""

from src.db.migration_files import migration_073_undrafted_free_agents as migration
from src.db.repositories.player_status_repo import PlayerStatusRepository


def test_leftover_prospects_become_free_agents_after_the_draft(db_conn, factory):
    done = factory.league(state="season")
    drafting = factory.league(state="draft")
    left = factory.prospect(league_id=done.id)
    pool = factory.prospect(league_id=drafting.id)

    migration.upgrade(db_conn)

    status = PlayerStatusRepository(db_conn)
    assert status.get_status(left.id) == "free_agent"
    assert status.get_status(pool.id) == "prospect"
