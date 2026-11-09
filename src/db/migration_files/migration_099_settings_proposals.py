"""
Settings votes (Josh, 2026-11-09): in a league with more than one person, the
commissioner proposes settings changes and the other human GMs vote. One
Reject sinks it; a GM who doesn't vote counts as a yes; it passes when
everyone has said yes, or once two whole decision windows have gone by
(src/api/services/settings_votes.py). GMs hear about it as gm_notifications
kind 'settings'.
"""

VERSION = 99


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS settings_proposals (
               id            TEXT PRIMARY KEY,
               league_id     TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
               proposer_gm_id TEXT REFERENCES gms(id) ON DELETE SET NULL,
               changes       JSONB NOT NULL,
               status        TEXT NOT NULL DEFAULT 'open'
                   CHECK (status IN ('open', 'passed', 'rejected', 'withdrawn', 'void')),
               closes_period INTEGER NOT NULL,
               reason        TEXT,
               created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
               decided_at    TIMESTAMPTZ
           )"""
    )
    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_settings_proposals_open
           ON settings_proposals(league_id) WHERE status = 'open'"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS settings_votes (
               proposal_id TEXT NOT NULL REFERENCES settings_proposals(id) ON DELETE CASCADE,
               gm_id       TEXT NOT NULL REFERENCES gms(id) ON DELETE CASCADE,
               vote        BOOLEAN,
               voted_at    TIMESTAMPTZ,
               PRIMARY KEY (proposal_id, gm_id)
           )"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_settings_proposals_proposer
           ON settings_proposals(proposer_gm_id)"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_settings_votes_gm ON settings_votes(gm_id)"
    )
    conn.execute(
        "ALTER TABLE gm_notifications DROP CONSTRAINT IF EXISTS gm_notifications_kind_check"
    )
    conn.execute(
        """ALTER TABLE gm_notifications ADD CONSTRAINT gm_notifications_kind_check
           CHECK (kind IN ('injury', 'returned', 'roster', 'trade', 'rust', 'settings'))"""
    )
