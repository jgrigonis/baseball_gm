"""
Draft need chips go from four levels (Off, Low, Med, High as 0-3) to three
(Low, Med, High as 0-2), with Low adding nothing as Off did. Saved strategies
move over: Off stays 0 (Low), the old Low and Med become Med (1), and High
becomes 2 (see src/league/offseason/draft_strategy.py).
"""

VERSION = 30


def upgrade(conn):
    conn.execute("""
        UPDATE draft_strategies SET chips = (
            SELECT COALESCE(
                jsonb_object_agg(
                    key,
                    CASE WHEN value::int >= 3 THEN 2
                         WHEN value::int >= 1 THEN 1
                         ELSE 0 END
                ),
                '{}'::jsonb
            )
            FROM jsonb_each_text(chips)
        )
        WHERE chips <> '{}'::jsonb
        """)
