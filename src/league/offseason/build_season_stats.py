# src/league/offseason/build_season_stats.py
"""
Populate the player_season_stats rollup table from player_game_stats.

Run after each season completes, or use --rebuild to fully reconstruct
from scratch (e.g. after a schema change or data correction).

Usage:
    # Incremental — build stats for one season
    python3 -m scripts.build_season_stats --season-id SEASON_UUID

    # Full rebuild — wipe and reconstruct all seasons
    python3 -m scripts.build_season_stats --rebuild

Hook into offseason_pipeline.py:
    pipeline.run(season_id) should call build_season(conn, season_id)
    before returning.
"""

import argparse
import sys

from src.db.connection import get_connection

# ── SQL ───────────────────────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS player_season_stats (
    player_id       TEXT    NOT NULL,
    season_id       TEXT    NOT NULL,
    team_id         TEXT    NOT NULL,
    is_postseason   INTEGER NOT NULL DEFAULT 0 CHECK (is_postseason IN (0, 1)),

    bat_games_played        INTEGER NOT NULL DEFAULT 0,
    bat_games_started       INTEGER NOT NULL DEFAULT 0,
    bat_ab                  INTEGER NOT NULL DEFAULT 0,
    bat_hits                INTEGER NOT NULL DEFAULT 0,
    bat_doubles             INTEGER NOT NULL DEFAULT 0,
    bat_triples             INTEGER NOT NULL DEFAULT 0,
    bat_home_runs           INTEGER NOT NULL DEFAULT 0,
    bat_rbi                 INTEGER NOT NULL DEFAULT 0,
    bat_runs                INTEGER NOT NULL DEFAULT 0,
    bat_walks               INTEGER NOT NULL DEFAULT 0,
    bat_strike_outs         INTEGER NOT NULL DEFAULT 0,
    bat_hbp                 INTEGER NOT NULL DEFAULT 0,
    bat_sac_flys            INTEGER NOT NULL DEFAULT 0,
    bat_sac_bunts           INTEGER NOT NULL DEFAULT 0,
    bat_gdp                 INTEGER NOT NULL DEFAULT 0,
    bat_gtp                 INTEGER NOT NULL DEFAULT 0,
    bat_stolen_bases        INTEGER NOT NULL DEFAULT 0,
    bat_caught_stealing     INTEGER NOT NULL DEFAULT 0,

    pitch_games_played      INTEGER NOT NULL DEFAULT 0,
    pitch_games_started     INTEGER NOT NULL DEFAULT 0,
    pitch_complete_games    INTEGER NOT NULL DEFAULT 0,
    pitch_shutouts          INTEGER NOT NULL DEFAULT 0,
    pitch_wins              INTEGER NOT NULL DEFAULT 0,
    pitch_losses            INTEGER NOT NULL DEFAULT 0,
    pitch_saves             INTEGER NOT NULL DEFAULT 0,
    pitch_holds             INTEGER NOT NULL DEFAULT 0,
    pitch_outs              INTEGER NOT NULL DEFAULT 0,
    pitch_hits              INTEGER NOT NULL DEFAULT 0,
    pitch_runs              INTEGER NOT NULL DEFAULT 0,
    pitch_earned_runs       INTEGER NOT NULL DEFAULT 0,
    pitch_home_runs         INTEGER NOT NULL DEFAULT 0,
    pitch_walks             INTEGER NOT NULL DEFAULT 0,
    pitch_strike_outs       INTEGER NOT NULL DEFAULT 0,
    pitch_hit_batters       INTEGER NOT NULL DEFAULT 0,
    pitch_doubles           INTEGER NOT NULL DEFAULT 0,
    pitch_triples           INTEGER NOT NULL DEFAULT 0,
    pitch_pickoffs          INTEGER NOT NULL DEFAULT 0,
    pitch_balks             INTEGER NOT NULL DEFAULT 0,
    pitch_wild_pitches      INTEGER NOT NULL DEFAULT 0,
    pitch_count             INTEGER NOT NULL DEFAULT 0,

    field_putouts           INTEGER NOT NULL DEFAULT 0,
    field_assists           INTEGER NOT NULL DEFAULT 0,
    field_errors            INTEGER NOT NULL DEFAULT 0,
    field_passed_balls      INTEGER NOT NULL DEFAULT 0,
    field_catcher_cs        INTEGER NOT NULL DEFAULT 0,
    field_catcher_sb        INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (player_id, season_id, team_id, is_postseason),

    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id)   REFERENCES teams(id)   ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pss_season_postseason
    ON player_season_stats(season_id, is_postseason);

CREATE INDEX IF NOT EXISTS idx_pss_player_season
    ON player_season_stats(player_id, season_id);

CREATE INDEX IF NOT EXISTS idx_pss_team_season
    ON player_season_stats(team_id, season_id);
"""

INSERT_SQL = """
INSERT INTO player_season_stats (
    player_id, season_id, team_id, is_postseason,

    bat_games_played, bat_games_started,
    bat_ab, bat_hits, bat_doubles, bat_triples, bat_home_runs,
    bat_rbi, bat_runs, bat_walks, bat_strike_outs, bat_hbp,
    bat_sac_flys, bat_sac_bunts, bat_gdp, bat_gtp,
    bat_stolen_bases, bat_caught_stealing,

    pitch_games_played, pitch_games_started, pitch_complete_games, pitch_shutouts,
    pitch_wins, pitch_losses, pitch_saves, pitch_holds,
    pitch_outs, pitch_hits, pitch_runs, pitch_earned_runs, pitch_home_runs,
    pitch_walks, pitch_strike_outs, pitch_hit_batters,
    pitch_doubles, pitch_triples, pitch_pickoffs, pitch_balks, pitch_wild_pitches,
    pitch_count,

    field_putouts, field_assists, field_errors,
    field_passed_balls, field_catcher_cs, field_catcher_sb
)
SELECT
    pgs.player_id,
    g.season_id,
    pgs.team_id,
    CASE WHEN g.series_id IS NULL THEN 0 ELSE 1 END AS is_postseason,

    SUM(pgs.bat_game_played),
    SUM(pgs.bat_game_started),
    SUM(pgs.bat_ab),
    SUM(pgs.bat_hits),
    SUM(pgs.bat_doubles),
    SUM(pgs.bat_triples),
    SUM(pgs.bat_home_runs),
    SUM(pgs.bat_rbi),
    SUM(pgs.bat_runs),
    SUM(pgs.bat_walks),
    SUM(pgs.bat_strike_outs),
    SUM(pgs.bat_hbp),
    SUM(pgs.bat_sac_flys),
    SUM(pgs.bat_sac_bunts),
    SUM(pgs.bat_gdp),
    SUM(pgs.bat_gtp),
    SUM(pgs.bat_stolen_bases),
    SUM(pgs.bat_caught_stealing),

    SUM(pgs.pitch_game_played),
    SUM(pgs.pitch_game_started),
    SUM(pgs.pitch_complete_game),
    SUM(pgs.pitch_shutout),
    SUM(pgs.pitch_win),
    SUM(pgs.pitch_loss),
    SUM(pgs.pitch_save),
    SUM(pgs.pitch_hold),
    SUM(pgs.pitch_outs),
    SUM(pgs.pitch_hits),
    SUM(pgs.pitch_runs),
    SUM(pgs.pitch_earned_runs),
    SUM(pgs.pitch_home_runs),
    SUM(pgs.pitch_walks),
    SUM(pgs.pitch_strike_outs),
    SUM(pgs.pitch_hit_batters),
    SUM(pgs.pitch_doubles),
    SUM(pgs.pitch_triples),
    SUM(pgs.pitch_pickoffs),
    SUM(pgs.pitch_balks),
    SUM(pgs.pitch_wild_pitches),
    SUM(pgs.pitch_count),

    SUM(pgs.field_putouts),
    SUM(pgs.field_assists),
    SUM(pgs.field_errors),
    SUM(pgs.passed_balls),
    SUM(pgs.catcher_cs),
    SUM(pgs.catcher_sb)

FROM player_game_stats pgs
JOIN games g ON pgs.game_id = g.id
{where_clause}
GROUP BY
    pgs.player_id,
    g.season_id,
    pgs.team_id,
    CASE WHEN g.series_id IS NULL THEN 0 ELSE 1 END
"""


# ── Core functions ────────────────────────────────────────────────────────────


def ensure_table(conn) -> None:
    """Create player_season_stats and its indexes if they don't exist."""
    for stmt in CREATE_TABLE_SQL.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    conn.commit()


def delete_season_rows(conn, season_id: str) -> int:
    """Delete existing rollup rows for a season. Returns rows deleted."""
    cur = conn.execute(
        "DELETE FROM player_season_stats WHERE season_id = %s", (season_id,)
    )
    conn.commit()
    return cur.rowcount


def delete_all(conn) -> int:
    """Wipe the entire rollup table. Returns rows deleted."""
    cur = conn.execute("DELETE FROM player_season_stats")
    conn.commit()
    return cur.rowcount


def build_season(conn, season_id: str) -> int:
    """
    Build rollup rows for a single season.
    Deletes existing rows for that season first to make it safe to re-run.
    Returns number of rows inserted.
    """
    deleted = delete_season_rows(conn, season_id)
    if deleted:
        print(f"  Cleared {deleted} existing rows for season {season_id}")

    sql = INSERT_SQL.format(where_clause="WHERE g.season_id = %s")
    cur = conn.execute(sql, (season_id,))
    conn.commit()
    return cur.rowcount


def build_all(conn) -> int:
    """
    Full rebuild — wipe and reconstruct every season.
    Returns total rows inserted.
    """
    deleted = delete_all(conn)
    if deleted:
        print(f"  Cleared {deleted} existing rows")

    sql = INSERT_SQL.format(where_clause="")
    cur = conn.execute(sql)
    conn.commit()
    return cur.rowcount


def get_all_season_ids(conn) -> list[tuple[str, int]]:
    """Return all (season_id, year) pairs ordered by year."""
    rows = conn.execute("SELECT id, year FROM seasons ORDER BY year").fetchall()
    return [(r["id"], r["year"]) for r in rows]


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args():
    p = argparse.ArgumentParser(
        description="Build the player_season_stats rollup table."
    )
    p.add_argument(
        "--season-id", "-i", help="Season UUID to build stats for (incremental)"
    )
    p.add_argument(
        "--rebuild",
        action="store_true",
        help="Full rebuild — wipe and reconstruct all seasons",
    )
    return p.parse_args()


def main():
    args = parse_args()

    if not args.season_id and not args.rebuild:
        print(
            "Error: provide --season-id for incremental build, or --rebuild for full reconstruction"
        )
        sys.exit(1)

    conn = get_connection()
    ensure_table(conn)

    if args.rebuild:
        print("Rebuilding player_season_stats from scratch...")
        seasons = get_all_season_ids(conn)
        total = 0
        for season_id, year in seasons:
            n = build_season(conn, season_id)
            print(f"  Season {year} ({season_id[:8]}...): {n} rows")
            total += n
        print(f"\nDone. {total} total rows inserted across {len(seasons)} seasons.")

    else:
        season_id = args.season_id
        # Verify the season exists
        row = conn.execute(
            "SELECT year FROM seasons WHERE id = %s", (season_id,)
        ).fetchone()
        if not row:
            print(f"Error: season '{season_id}' not found in database")
            sys.exit(1)
        year = row["year"]

        print(f"Building player_season_stats for Season {year} ({season_id})...")
        n = build_season(conn, season_id)
        print(f"Done. {n} rows inserted.")

    conn.close()


if __name__ == "__main__":
    main()
