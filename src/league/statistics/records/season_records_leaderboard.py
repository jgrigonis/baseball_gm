#!/usr/bin/env python3
# src/league/statistics/records/season_records_leaderboard.py
"""
Single-season records leaderboard. Queries the player_season_stats rollup
table — run build_season_stats.py first to populate it.

Qualification thresholds mirror league_leaders.py:
  - Batting rates: 3.1 PA per team game played that season
  - Pitching rates: 1.0 IP per team game played that season

Usage:
    python3 season_records.py                   # all-time best seasons
    python3 season_records.py --regular-season  # regular season only
    python3 season_records.py --batting
    python3 season_records.py --pitching
    python3 season_records.py --top 10
"""

import argparse
import sys

from src.db.connection import get_connection
from src.stats import formulas

PA_PER_GAME = 3.1
IP_PER_GAME = 1.0


# ── Formatting ────────────────────────────────────────────────────────────────


def fmt_ip(outs):
    return formulas.ip_str(outs or 0)


def print_section(title):
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def print_record(label, rows, value_label="Value"):
    if not rows:
        print(f"\n  {label}: (no data)")
        return
    print(f"\n  {label}")
    print(f"  {'#':<4} {'Player':<24} {'Team':<26} {'Season':<7} {value_label}")
    print(f"  {'-' * 4} {'-' * 24} {'-' * 26} {'-' * 7} {'-' * 10}")
    for i, row in enumerate(rows, 1):
        player, team, season, value = row
        print(f"  {i:<4} {player:<24} {team:<26} {season:<7} {value}")


# ── Helpers ───────────────────────────────────────────────────────────────────


def postseason_filter(args):
    """Filter value for is_postseason column."""
    # regular_season=True  → only is_postseason=0
    # regular_season=False → both (SUM across 0 and 1)
    return args.regular_season


def primary_team_expr():
    """
    Inline subquery: team the player appeared with most in this season/stint.
    References pss.player_id and pss.season_id from the outer query.
    """
    return """
        (
            SELECT t2.city || ' ' || t2.mascot
            FROM player_season_stats pss2
            JOIN teams t2 ON pss2.team_id = t2.id
            WHERE pss2.player_id = pss.player_id
              AND pss2.season_id = pss.season_id
            ORDER BY pss2.bat_games_played + pss2.pitch_games_played DESC
            LIMIT 1
        )
    """


def games_per_team_cte(regular_season):
    """
    CTE that yields (season_id, games_per_team) — the max games any team
    played in that season. Used for qualification thresholds.
    """
    series_clause = "AND series_id IS NULL" if regular_season else ""
    return f"""
        games_per_team AS (
            SELECT season_id, MAX(cnt) AS games_per_team
            FROM (
                SELECT season_id, home_team_id AS team_id, COUNT(*) AS cnt
                FROM games
                WHERE completed = 1 {series_clause}
                GROUP BY season_id, home_team_id
                UNION ALL
                SELECT season_id, away_team_id AS team_id, COUNT(*) AS cnt
                FROM games
                WHERE completed = 1 {series_clause}
                GROUP BY season_id, away_team_id
            )
            GROUP BY season_id
        )
    """


# ── Core query functions ──────────────────────────────────────────────────────


def counting_query(
    conn, args, select_expr, order_expr=None, bat_or_pitch="bat", fmt_fn=None
):
    """
    Aggregate a counting stat from player_season_stats across all seasons.
    For traded players, sums across all team stints within the season.
    """
    ps_filter = "AND NOT pss.is_postseason" if args.regular_season else ""
    order = order_expr or select_expr

    sql = f"""
        SELECT
            p.first_name || ' ' || p.last_name AS player,
            {primary_team_expr()} AS team,
            s.year AS season,
            {select_expr} AS value
        FROM player_season_stats pss
        JOIN players p ON pss.player_id = p.id
        JOIN seasons s ON pss.season_id = s.id
        WHERE {bat_or_pitch}_games_played > 0
          {ps_filter}
        GROUP BY pss.player_id, pss.season_id
        ORDER BY {order} DESC
        LIMIT {args.top}
    """
    rows = conn.execute(sql).fetchall()
    if fmt_fn:
        return [(p, t, str(s), fmt_fn(v)) for p, t, s, v in rows]
    return [(p, t, str(s), str(v) if v is not None else "—") for p, t, s, v in rows]


def rate_query_desc(
    conn, args, select_expr, bat_or_pitch="bat", qualify_expr=None, fmt=".3f"
):
    """
    Qualified rate stat — higher is better (AVG, OBP, SLG).
    qualify_expr is a HAVING clause fragment using aggregated columns.
    """
    ps_filter = "AND NOT pss.is_postseason" if args.regular_season else ""
    having = f"HAVING {qualify_expr}" if qualify_expr else ""

    sql = f"""
        WITH {games_per_team_cte(args.regular_season)}
        SELECT
            p.first_name || ' ' || p.last_name AS player,
            {primary_team_expr()} AS team,
            s.year AS season,
            {select_expr} AS value
        FROM player_season_stats pss
        JOIN players p ON pss.player_id = p.id
        JOIN seasons s ON pss.season_id = s.id
        JOIN games_per_team gpt ON gpt.season_id = pss.season_id
        WHERE {bat_or_pitch}_games_played > 0
          {ps_filter}
        GROUP BY pss.player_id, pss.season_id
        {having}
        ORDER BY {select_expr} DESC
        LIMIT {args.top}
    """
    rows = conn.execute(sql).fetchall()
    return [
        (p, t, str(s), f"{float(v):{fmt}}" if v is not None else "—")
        for p, t, s, v in rows
    ]


def rate_query_asc(conn, args, select_expr, qualify_expr, fmt=".2f"):
    """
    Qualified rate stat — lower is better (ERA, WHIP).
    """
    ps_filter = "AND NOT pss.is_postseason" if args.regular_season else ""

    sql = f"""
        WITH {games_per_team_cte(args.regular_season)}
        SELECT
            p.first_name || ' ' || p.last_name AS player,
            {primary_team_expr()} AS team,
            s.year AS season,
            {select_expr} AS value
        FROM player_season_stats pss
        JOIN players p ON pss.player_id = p.id
        JOIN seasons s ON pss.season_id = s.id
        JOIN games_per_team gpt ON gpt.season_id = pss.season_id
        WHERE pitch_games_played > 0
          {ps_filter}
        GROUP BY pss.player_id, pss.season_id
        HAVING {qualify_expr}
        ORDER BY {select_expr} ASC
        LIMIT {args.top}
    """
    rows = conn.execute(sql).fetchall()
    return [
        (p, t, str(s), f"{float(v):{fmt}}" if v is not None else "—")
        for p, t, s, v in rows
    ]


# ── Stat definitions ──────────────────────────────────────────────────────────

BATTING_COUNTING = [
    ("Most At Bats", "SUM(pss.bat_ab)", "AB"),
    ("Most Hits", "SUM(pss.bat_hits)", "H"),
    ("Most Doubles", "SUM(pss.bat_doubles)", "2B"),
    ("Most Triples", "SUM(pss.bat_triples)", "3B"),
    ("Most Home Runs", "SUM(pss.bat_home_runs)", "HR"),
    ("Most RBI", "SUM(pss.bat_rbi)", "RBI"),
    ("Most Runs", "SUM(pss.bat_runs)", "R"),
    ("Most Walks", "SUM(pss.bat_walks)", "BB"),
    ("Most Stolen Bases", "SUM(pss.bat_stolen_bases)", "SB"),
    ("Most Strikeouts", "SUM(pss.bat_strike_outs)", "K"),
    (
        "Most Total Bases",
        "(SUM(pss.bat_hits) - SUM(pss.bat_doubles) - SUM(pss.bat_triples) - SUM(pss.bat_home_runs))"
        " + (2 * SUM(pss.bat_doubles))"
        " + (3 * SUM(pss.bat_triples))"
        " + (4 * SUM(pss.bat_home_runs))",
        "TB",
    ),
]

# Qualification: PA >= PA_PER_GAME * games_per_team
BAT_PA_EXPR = (
    "SUM(pss.bat_ab) + SUM(pss.bat_walks) + SUM(pss.bat_hbp) + SUM(pss.bat_sac_flys)"
)
BAT_QUALIFY = f"({BAT_PA_EXPR}) >= {PA_PER_GAME} * gpt.games_per_team"

BATTING_RATES = [
    (
        "Highest AVG",
        "CAST(SUM(pss.bat_hits) AS REAL) / NULLIF(SUM(pss.bat_ab), 0)",
        "AVG",
        ".3f",
    ),
    (
        "Highest OBP",
        f"CAST(SUM(pss.bat_hits) + SUM(pss.bat_walks) + SUM(pss.bat_hbp) AS REAL)"
        f" / NULLIF({BAT_PA_EXPR}, 0)",
        "OBP",
        ".3f",
    ),
    (
        "Highest SLG",
        "CAST("
        "  (SUM(pss.bat_hits) - SUM(pss.bat_doubles) - SUM(pss.bat_triples) - SUM(pss.bat_home_runs))"
        "  + (2 * SUM(pss.bat_doubles))"
        "  + (3 * SUM(pss.bat_triples))"
        "  + (4 * SUM(pss.bat_home_runs))"
        " AS REAL) / NULLIF(SUM(pss.bat_ab), 0)",
        "SLG",
        ".3f",
    ),
]

PITCHING_COUNTING = [
    ("Most Strikeouts", "SUM(pss.pitch_strike_outs)", "K"),
    ("Most Wins", "SUM(pss.pitch_wins)", "W"),
    ("Most Saves", "SUM(pss.pitch_saves)", "SV"),
    ("Most Walks Allowed", "SUM(pss.pitch_walks)", "BB"),
    ("Most HR Allowed", "SUM(pss.pitch_home_runs)", "HR"),
    ("Most Hits Allowed", "SUM(pss.pitch_hits)", "H"),
]

# Qualification: IP >= IP_PER_GAME * games_per_team
PITCH_QUALIFY = f"(SUM(pss.pitch_outs) / 3.0) >= {IP_PER_GAME} * gpt.games_per_team"

ERA_EXPR = (
    "CAST(SUM(pss.pitch_earned_runs) AS REAL) / NULLIF(SUM(pss.pitch_outs), 0) * 27"
)
WHIP_EXPR = (
    "CAST(SUM(pss.pitch_walks) + SUM(pss.pitch_hits) AS REAL)"
    " / NULLIF(SUM(pss.pitch_outs) / 3.0, 0)"
)


# ── Section runners ───────────────────────────────────────────────────────────


def run_batting(args, conn):
    print_section("BATTING — SINGLE SEASON RECORDS")

    for name, expr, val_label in BATTING_COUNTING:
        rows = counting_query(conn, args, expr, bat_or_pitch="bat")
        print_record(name, rows, val_label)

    for name, expr, val_label, fmt in BATTING_RATES:
        rows = rate_query_desc(
            conn, args, expr, bat_or_pitch="bat", qualify_expr=BAT_QUALIFY, fmt=fmt
        )
        print_record(name, rows, val_label)


def run_pitching(args, conn):
    print_section("PITCHING — SINGLE SEASON RECORDS")

    for name, expr, val_label in PITCHING_COUNTING:
        rows = counting_query(conn, args, expr, bat_or_pitch="pitch")
        print_record(name, rows, val_label)

    # Innings pitched
    rows = counting_query(
        conn,
        args,
        "SUM(pss.pitch_outs)",
        bat_or_pitch="pitch",
        fmt_fn=lambda v: fmt_ip(int(v)) if v else "—",
    )
    print_record("Most Innings Pitched", rows, "IP")

    rows = rate_query_asc(conn, args, ERA_EXPR, PITCH_QUALIFY)
    print_record("Best ERA (qualified)", rows, "ERA")

    rows = rate_query_asc(conn, args, WHIP_EXPR, PITCH_QUALIFY, fmt=".3f")
    print_record("Best WHIP (qualified)", rows, "WHIP")


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Baseball single-season records leaderboard"
    )
    parser.add_argument(
        "--regular-season",
        action="store_true",
        help="Regular season only — excludes playoff series games",
    )
    parser.add_argument(
        "--batting", action="store_true", help="Show batting records only"
    )
    parser.add_argument(
        "--pitching", action="store_true", help="Show pitching records only"
    )
    parser.add_argument(
        "--top", type=int, default=5, help="Number of entries per record (default: 5)"
    )
    args = parser.parse_args()

    if not args.batting and not args.pitching:
        args.batting = True
        args.pitching = True

    # Check rollup table exists and has data
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='player_season_stats'"
    ).fetchone()
    if not row or row["count"] == 0:
        print("Error: player_season_stats table not found.")
        print("Run: python3 -m src.league.offseason.build_season_stats --rebuild")
        sys.exit(1)

    row = conn.execute("SELECT COUNT(*) FROM player_season_stats").fetchone()
    if not row or row["count"] == 0:
        print("Error: player_season_stats is empty.")
        print("Run: python3 -m src.league.offseason.build_season_stats --rebuild")
        sys.exit(1)

    scope = "Regular Season" if args.regular_season else "All Games (inc. Playoffs)"
    print(f"\n{'━' * 78}")
    print(f"  SINGLE SEASON RECORDS  —  {scope}")
    print(f"{'━' * 78}")

    if args.batting:
        run_batting(args, conn)
    if args.pitching:
        run_pitching(args, conn)

    conn.close()
    print()


if __name__ == "__main__":
    main()
