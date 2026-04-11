#!/usr/bin/env python3
# src/league/statistics/records/single_game_records_leaderboard.py
"""
Single-game records leaderboard.

Usage:
    python3 records.py                              # all-time, all games
    python3 records.py --regular-season             # all-time, regular season only
    python3 records.py --season 2027                # season 2027, all games
    python3 records.py --season 2027 --regular-season
    python3 records.py --series SERIES_ID
    python3 records.py --batting
    python3 records.py --pitching
    python3 records.py --top 10
"""

import argparse

from src.db.connection import get_connection


# ── Formatting helpers ────────────────────────────────────────────────────────


def fmt_ip(outs):
    if outs is None:
        return "0.0"
    return f"{outs // 3}.{outs % 3}"


def print_section(title):
    print()
    print("=" * 74)
    print(f"  {title}")
    print("=" * 74)


def print_record(label, rows, value_label="Value", show_innings=True):
    if not rows:
        # print(f"\n  {label}: (no data)")
        return
    print(f"\n  {label}")
    if show_innings:
        print(
            f"  {'#':<4} {'Player':<24} {'Team':<26} {'Date':<12} {'Season':<7} {value_label:<8} {'Inn'}"
        )
        print(f"  {'-'*4} {'-'*24} {'-'*26} {'-'*12} {'-'*7} {'-'*8} {'-'*4}")
        for i, row in enumerate(rows, 1):
            player, team, date, season, value, innings = row
            print(
                f"  {i:<4} {player:<24} {team:<26} {date:<12} {season:<7} {str(value):<8} {innings}"
            )
    else:
        print(
            f"  {'#':<4} {'Player':<24} {'Team':<26} {'Date':<12} {'Season':<7} {value_label}"
        )
        print(f"  {'-'*4} {'-'*24} {'-'*26} {'-'*12} {'-'*7} {'-'*8}")
        for i, row in enumerate(rows, 1):
            player, team, date, season, value, _innings = row
            print(
                f"  {i:<4} {player:<24} {team:<26} {date:<12} {season:<7} {str(value)}"
            )


# ── Query builder ─────────────────────────────────────────────────────────────


def build_game_filter(args):
    clauses = ["g.completed = 1"]
    params = []

    if args.regular_season:
        clauses.append("g.series_id IS NULL")
    elif hasattr(args, "series") and args.series:
        clauses.append("g.series_id = %s")
        params.append(args.series)

    if args.season:
        clauses.append("s.year = %s")
        params.append(args.season)

    return clauses, params


def add_innings_filter(clauses, innings_filter):
    if innings_filter == 9:
        clauses.append("g.innings_played = 9")
    elif innings_filter == "extra":
        clauses.append("g.innings_played > 9")


TOTAL_BASES_EXPR = (
    "(pgs.bat_hits - pgs.bat_doubles - pgs.bat_triples - pgs.bat_home_runs)"
    " + (2 * pgs.bat_doubles)"
    " + (3 * pgs.bat_triples)"
    " + (4 * pgs.bat_home_runs)"
)


def run_query(
    conn, select_expr, order_expr, where_clauses, params, top, min_value=None
):
    where = " AND ".join(where_clauses)
    # having = f"HAVING {select_expr} > {min_value}" if min_value is not None else ""
    # For expressions with aliases we need a subquery approach for HAVING
    sql = f"""
        SELECT
            p.first_name || ' ' || p.last_name,
            t.city || ' ' || t.mascot,
            g.game_date,
            s.year,
            {select_expr} as val,
            g.innings_played
        FROM player_game_stats pgs
        JOIN players p ON pgs.player_id = p.id
        JOIN teams t ON pgs.team_id = t.id
        JOIN games g ON pgs.game_id = g.id
        JOIN seasons s ON g.season_id = s.id
        WHERE {where}
        {"AND (" + select_expr + ") > " + str(min_value) if min_value is not None else ""}
        ORDER BY {order_expr} DESC
        LIMIT {top}
    """
    return conn.execute(sql, params).fetchall()


def get_top_value(conn, select_expr, where_clauses, params):
    """Return the single top value for a record — used to filter extra-inning results."""
    where = " AND ".join(where_clauses)
    sql = f"""
        SELECT {select_expr} as val
        FROM player_game_stats pgs
        JOIN players p ON pgs.player_id = p.id
        JOIN teams t ON pgs.team_id = t.id
        JOIN games g ON pgs.game_id = g.id
        JOIN seasons s ON g.season_id = s.id
        WHERE {where}
        ORDER BY val DESC
        LIMIT 1
    """
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


# ── Record definitions ────────────────────────────────────────────────────────

BATTING_RECORDS = [
    ("Most At Bats", "pgs.bat_ab", "AB"),
    ("Most Hits", "pgs.bat_hits", "H"),
    ("Most Doubles", "pgs.bat_doubles", "2B"),
    ("Most Triples", "pgs.bat_triples", "3B"),
    ("Most Home Runs", "pgs.bat_home_runs", "HR"),
    ("Most RBI", "pgs.bat_rbi", "RBI"),
    ("Most Walks", "pgs.bat_walks", "BB"),
    ("Most Stolen Bases", "pgs.bat_stolen_bases", "SB"),
    ("Most Strikeouts", "pgs.bat_strike_outs", "K"),
    ("Most Total Bases", TOTAL_BASES_EXPR, "TB"),
]

PITCHING_RECORDS = [
    ("Most Strikeouts", "pgs.pitch_strike_outs", "K"),
    ("Most Walks Allowed", "pgs.pitch_walks", "BB"),
    ("Most HR Allowed", "pgs.pitch_home_runs", "HR"),
    ("Most Hits Allowed", "pgs.pitch_hits", "H"),
    ("Most Innings Pitched", "pgs.pitch_outs", "IP"),  # handled specially
]


# ── Section runners ───────────────────────────────────────────────────────────


def run_batting_9inn(args, conn):
    print_section("BATTING — 9 INNINGS")
    for name, field, val_label in BATTING_RECORDS:
        clauses, params = build_game_filter(args)
        add_innings_filter(clauses, 9)
        rows = run_query(conn, field, field, clauses, params, args.top)
        print_record(name, rows, val_label, show_innings=False)


def run_batting_extra(args, conn):
    print_section("BATTING — EXTRA INNINGS (10+)")
    for name, field, val_label in BATTING_RECORDS:
        # Get the 9-inning record to use as the floor
        nine_clauses, nine_params = build_game_filter(args)
        add_innings_filter(nine_clauses, 9)
        nine_best = get_top_value(conn, field, nine_clauses, nine_params)

        clauses, params = build_game_filter(args)
        add_innings_filter(clauses, "extra")
        rows = run_query(
            conn, field, field, clauses, params, args.top, min_value=nine_best
        )
        print_record(name, rows, val_label, show_innings=True)


def run_pitching_9inn(args, conn):
    print_section("PITCHING — 9 INNINGS")
    for name, field, val_label in PITCHING_RECORDS:
        if name == "Most Innings Pitched":
            continue  # suppress — always 9.0 in a 9-inning game
        clauses, params = build_game_filter(args)
        clauses.append("pgs.pitch_game_played = 1")
        add_innings_filter(clauses, 9)
        rows = run_query(conn, field, field, clauses, params, args.top)
        print_record(name, rows, val_label, show_innings=False)


def run_pitching_extra(args, conn):
    print_section("PITCHING — EXTRA INNINGS (10+)")
    for name, field, val_label in PITCHING_RECORDS:
        clauses, params = build_game_filter(args)
        clauses.append("pgs.pitch_game_played = 1")
        add_innings_filter(clauses, "extra")

        if name == "Most Innings Pitched":
            # Get 9-inning floor (27 outs = 9.0 IP)
            nine_clauses, nine_params = build_game_filter(args)
            nine_clauses.append("pgs.pitch_game_played = 1")
            add_innings_filter(nine_clauses, 9)
            nine_best = get_top_value(conn, field, nine_clauses, nine_params)
            raw = run_query(
                conn, field, field, clauses, params, args.top, min_value=nine_best
            )
            ip_rows = [(p, t, d, y, fmt_ip(v), inn) for p, t, d, y, v, inn in raw]
            print_record(name, ip_rows, val_label, show_innings=True)
        else:
            # Get 9-inning floor
            nine_clauses, nine_params = build_game_filter(args)
            nine_clauses.append("pgs.pitch_game_played = 1")
            add_innings_filter(nine_clauses, 9)
            nine_best = get_top_value(conn, field, nine_clauses, nine_params)
            rows = run_query(
                conn, field, field, clauses, params, args.top, min_value=nine_best
            )
            print_record(name, rows, val_label, show_innings=True)


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Baseball single-game records leaderboard"
    )
    parser.add_argument(
        "--season",
        type=int,
        help="Filter to a specific season year (includes playoffs)",
    )
    parser.add_argument(
        "--regular-season",
        action="store_true",
        help="Regular season only — excludes playoff series games",
    )
    parser.add_argument("--series", help="Filter to a specific playoff series ID")
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


    conn = get_connection()

    scope_parts = []
    if args.season:
        scope_parts.append(f"Season {args.season}")
    else:
        scope_parts.append("All Time")
    if args.regular_season:
        scope_parts.append("Regular Season")
    elif args.series:
        scope_parts.append(f"Series {args.series}")
    scope = " | ".join(scope_parts)

    print(f"\n{'━' * 74}")
    print(f"  SINGLE GAME RECORDS  —  {scope}")
    print(f"{'━' * 74}")

    # Order: batting 9inn → batting extra → pitching 9inn → pitching extra
    if args.batting:
        run_batting_9inn(args, conn)
        run_batting_extra(args, conn)
    if args.pitching:
        run_pitching_9inn(args, conn)
        run_pitching_extra(args, conn)

    conn.close()
    print()


if __name__ == "__main__":
    main()
