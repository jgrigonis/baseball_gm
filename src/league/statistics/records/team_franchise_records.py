# src/league/statistics/records/team_franchise_records.py
"""
Team franchise records — best team performances in a single game, full season,
or playoff series.

Without --team: shows league-wide records (which team holds each record).
With --team:    shows that team's own franchise records.

Usage:
    python3 team_franchise_records.py                        # league-wide, all scopes
    python3 team_franchise_records.py --team "Vienna Maestros"
    python3 team_franchise_records.py --team Vienna --regular-season
    python3 team_franchise_records.py --game                 # single-game only
    python3 team_franchise_records.py --season               # season only
    python3 team_franchise_records.py --series               # series only
    python3 team_franchise_records.py --top 10
    python3 team_franchise_records.py --teams
"""

import sqlite3
import argparse
import os
import sys

try:
    from src.util.locations import LEAGUE_FILES_DIR
except ImportError:
    LEAGUE_FILES_DIR = "leagues"

try:
    from src.util.team_resolver import resolve_team, list_teams, TeamResolverError
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
    from src.util.team_resolver import resolve_team, list_teams, TeamResolverError

DEFAULT_DB = os.path.join(LEAGUE_FILES_DIR, "league.db")


# ── Formatting ────────────────────────────────────────────────────────────────


def fmt_ip(outs):
    if outs is None:
        return "0.0"
    return f"{outs // 3}.{outs % 3}"


def print_section(title):
    print()
    print("=" * 82)
    print(f"  {title}")
    print("=" * 82)


def print_game_record(label, rows, value_label, team_col=True):
    """
    Rows: (team, date, season, value, innings)  when team_col=True
          (date, season, value, innings)         when team_col=False
    """
    if not rows:
        # print(f"\n  {label}: (no data)")
        return
    print(f"\n  {label}")
    if team_col:
        print(
            f"  {'#':<4} {'Team':<26} {'Date':<12} {'Season':<7} {value_label:<8} {'Inn'}"
        )
        print(f"  {'-'*4} {'-'*26} {'-'*12} {'-'*7} {'-'*8} {'-'*4}")
        for i, row in enumerate(rows, 1):
            team, date, season, value, innings = row
            print(
                f"  {i:<4} {team:<26} {date:<12} {season:<7} {str(value):<8} {innings}"
            )
    else:
        print(f"  {'#':<4} {'Date':<12} {'Season':<7} {value_label:<8} {'Inn'}")
        print(f"  {'-'*4} {'-'*12} {'-'*7} {'-'*8} {'-'*4}")
        for i, row in enumerate(rows, 1):
            date, season, value, innings = row
            print(f"  {i:<4} {date:<12} {season:<7} {str(value):<8} {innings}")


def print_season_record(label, rows, value_label, team_col=True):
    """
    Rows: (team, season, value)  when team_col=True
          (season, value)        when team_col=False
    """
    if not rows:
        print(f"\n  {label}: (no data)")
        return
    print(f"\n  {label}")
    if team_col:
        print(f"  {'#':<4} {'Team':<26} {'Season':<7} {value_label}")
        print(f"  {'-'*4} {'-'*26} {'-'*7} {'-'*10}")
        for i, row in enumerate(rows, 1):
            team, season, value = row
            print(f"  {i:<4} {team:<26} {season:<7} {value}")
    else:
        print(f"  {'#':<4} {'Season':<7} {value_label}")
        print(f"  {'-'*4} {'-'*7} {'-'*10}")
        for i, row in enumerate(rows, 1):
            season, value = row
            print(f"  {i:<4} {season:<7} {value}")


def print_series_record(label, rows, value_label, team_col=True):
    """
    Rows: (team, series_name, season, value)  when team_col=True
          (series_name, season, value)         when team_col=False
    """
    if not rows:
        print(f"\n  {label}: (no data)")
        return
    print(f"\n  {label}")
    if team_col:
        print(f"  {'#':<4} {'Team':<26} {'Series':<24} {'Season':<7} {value_label}")
        print(f"  {'-'*4} {'-'*26} {'-'*24} {'-'*7} {'-'*10}")
        for i, row in enumerate(rows, 1):
            team, series, season, value = row
            print(f"  {i:<4} {team:<26} {series:<24} {season:<7} {value}")
    else:
        print(f"  {'#':<4} {'Series':<24} {'Season':<7} {value_label}")
        print(f"  {'-'*4} {'-'*24} {'-'*7} {'-'*10}")
        for i, row in enumerate(rows, 1):
            series, season, value = row
            print(f"  {i:<4} {series:<24} {season:<7} {value}")


# ── Query helpers ─────────────────────────────────────────────────────────────

TOTAL_BASES_EXPR = (
    "(SUM(pgs.bat_hits) - SUM(pgs.bat_doubles) - SUM(pgs.bat_triples) - SUM(pgs.bat_home_runs))"
    " + (2 * SUM(pgs.bat_doubles))"
    " + (3 * SUM(pgs.bat_triples))"
    " + (4 * SUM(pgs.bat_home_runs))"
)

# Batting stats aggregated from player_game_stats by team+game
GAME_BAT_RECORDS = [
    ("Most Hits", "SUM(pgs.bat_hits)", "H"),
    ("Most Doubles", "SUM(pgs.bat_doubles)", "2B"),
    ("Most Triples", "SUM(pgs.bat_triples)", "3B"),
    ("Most Home Runs", "SUM(pgs.bat_home_runs)", "HR"),
    ("Most Runs", "SUM(pgs.bat_runs)", "R"),
    ("Most Walks", "SUM(pgs.bat_walks)", "BB"),
    ("Most Stolen Bases", "SUM(pgs.bat_stolen_bases)", "SB"),
    ("Most RBI", "SUM(pgs.bat_rbi)", "RBI"),
    ("Most Strikeouts", "SUM(pgs.bat_strike_outs)", "K"),
    ("Most Total Bases", TOTAL_BASES_EXPR, "TB"),
]

GAME_PITCH_RECORDS = [
    ("Most K (pitching)", "SUM(pgs.pitch_strike_outs)", "K"),
    ("Most BB Allowed", "SUM(pgs.pitch_walks)", "BB"),
    ("Most HR Allowed", "SUM(pgs.pitch_home_runs)", "HR"),
    ("Most Hits Allowed", "SUM(pgs.pitch_hits)", "H"),
]

SEASON_BAT_RECORDS = [
    ("Most Hits", "SUM(pss.bat_hits)", "H"),
    ("Most Doubles", "SUM(pss.bat_doubles)", "2B"),
    ("Most Triples", "SUM(pss.bat_triples)", "3B"),
    ("Most Home Runs", "SUM(pss.bat_home_runs)", "HR"),
    ("Most Runs", "SUM(pss.bat_runs)", "R"),
    ("Most Walks", "SUM(pss.bat_walks)", "BB"),
    ("Most Stolen Bases", "SUM(pss.bat_stolen_bases)", "SB"),
    ("Most RBI", "SUM(pss.bat_rbi)", "RBI"),
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

SEASON_PITCH_RECORDS = [
    ("Most K (pitching)", "SUM(pss.pitch_strike_outs)", "K"),
    ("Most Wins", "SUM(pss.pitch_wins)", "W"),
    ("Most Saves", "SUM(pss.pitch_saves)", "SV"),
    ("Most BB Allowed", "SUM(pss.pitch_walks)", "BB"),
    ("Most HR Allowed", "SUM(pss.pitch_home_runs)", "HR"),
    ("Most Hits Allowed", "SUM(pss.pitch_hits)", "H"),
]


# ── Single-game queries ───────────────────────────────────────────────────────


def game_records_query(
    conn, args, agg_expr, team_id=None, pitching=False, innings_filter=None, top=5
):
    """
    Best single-game team performance for a given aggregated stat.
    Returns (team_name, date, season, value, innings).
    """
    clauses = ["g.completed = 1"]
    params = []

    if args.regular_season:
        clauses.append("g.series_id IS NULL")
    if team_id:
        clauses.append("pgs.team_id = ?")
        params.append(team_id)
    if innings_filter == 9:
        clauses.append("g.innings_played = 9")
    elif innings_filter == "extra":
        clauses.append("g.innings_played > 9")
    if pitching:
        clauses.append("pgs.pitch_game_played = 1")

    where = " AND ".join(clauses)

    sql = f"""
        SELECT
            t.city || ' ' || t.mascot AS team,
            g.date,
            s.year,
            {agg_expr} AS value,
            g.innings_played
        FROM player_game_stats pgs
        JOIN games g ON pgs.game_id = g.id
        JOIN seasons s ON g.season_id = s.id
        JOIN teams t ON pgs.team_id = t.id
        WHERE {where}
        GROUP BY pgs.team_id, pgs.game_id
        ORDER BY value DESC
        LIMIT {top}
    """
    return conn.execute(sql, params).fetchall()


def get_game_9inn_best(conn, args, agg_expr, team_id=None, pitching=False):
    """Top value in 9-inning games — floor for extra-inning display."""
    clauses = ["g.completed = 1", "g.innings_played = 9"]
    params = []
    if args.regular_season:
        clauses.append("g.series_id IS NULL")
    if team_id:
        clauses.append("pgs.team_id = ?")
        params.append(team_id)
    if pitching:
        clauses.append("pgs.pitch_game_played = 1")
    where = " AND ".join(clauses)

    sql = f"""
        SELECT {agg_expr} AS value
        FROM player_game_stats pgs
        JOIN games g ON pgs.game_id = g.id
        WHERE {where}
        GROUP BY pgs.team_id, pgs.game_id
        ORDER BY value DESC LIMIT 1
    """
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def game_records_extra_query(
    conn, args, agg_expr, nine_best, team_id=None, pitching=False, top=5
):
    """Extra-inning game records that beat the 9-inning best."""
    clauses = ["g.completed = 1", "g.innings_played > 9"]
    params = []
    if args.regular_season:
        clauses.append("g.series_id IS NULL")
    if team_id:
        clauses.append("pgs.team_id = ?")
        params.append(team_id)
    if pitching:
        clauses.append("pgs.pitch_game_played = 1")
    where = " AND ".join(clauses)

    having = f"HAVING value > {nine_best}" if nine_best is not None else ""

    sql = f"""
        SELECT
            t.city || ' ' || t.mascot AS team,
            g.date,
            s.year,
            {agg_expr} AS value,
            g.innings_played
        FROM player_game_stats pgs
        JOIN games g ON pgs.game_id = g.id
        JOIN seasons s ON g.season_id = s.id
        JOIN teams t ON pgs.team_id = t.id
        WHERE {where}
        GROUP BY pgs.team_id, pgs.game_id
        {having}
        ORDER BY value DESC
        LIMIT {top}
    """
    return conn.execute(sql, params).fetchall()


# ── Season queries ────────────────────────────────────────────────────────────


def season_records_query(
    conn, args, agg_expr, team_id=None, bat_or_pitch="bat", top=5, fmt_fn=None
):
    """
    Best single-season team total for a stat.
    Returns (team_name, season_year, value).
    """
    ps_filter = "AND pss.is_postseason = 0" if args.regular_season else ""
    team_filter = "AND pss.team_id = ?" if team_id else ""
    params = [team_id] if team_id else []

    sql = f"""
        SELECT
            t.city || ' ' || t.mascot AS team,
            s.year,
            {agg_expr} AS value
        FROM player_season_stats pss
        JOIN teams t ON pss.team_id = t.id
        JOIN seasons s ON pss.season_id = s.id
        WHERE pss.{bat_or_pitch}_games_played > 0
          {ps_filter}
          {team_filter}
        GROUP BY pss.team_id, pss.season_id
        ORDER BY value DESC
        LIMIT {top}
    """
    rows = conn.execute(sql, params).fetchall()
    if fmt_fn:
        return [(t, str(s), fmt_fn(v)) for t, s, v in rows]
    return [(t, str(s), str(v) if v is not None else "—") for t, s, v in rows]


# ── Series queries ────────────────────────────────────────────────────────────


def series_records_query(
    conn, args, agg_expr, team_id=None, pitching=False, top=5, fmt_fn=None
):
    """
    Best team total across an entire playoff series.
    Returns (team_name, series_name, season_year, value).
    """
    clauses = ["g.series_id IS NOT NULL", "g.completed = 1"]
    params = []
    if team_id:
        clauses.append("pgs.team_id = ?")
        params.append(team_id)
    if pitching:
        clauses.append("pgs.pitch_game_played = 1")
    where = " AND ".join(clauses)

    sql = f"""
        SELECT
            t.city || ' ' || t.mascot AS team,
            sr.name AS series_name,
            s.year,
            {agg_expr} AS value
        FROM player_game_stats pgs
        JOIN games g ON pgs.game_id = g.id
        JOIN seasons s ON g.season_id = s.id
        JOIN series sr ON g.series_id = sr.id
        JOIN teams t ON pgs.team_id = t.id
        WHERE {where}
        GROUP BY pgs.team_id, g.series_id
        ORDER BY value DESC
        LIMIT {top}
    """
    rows = conn.execute(sql, params).fetchall()
    if fmt_fn:
        return [(t, sn, str(s), fmt_fn(v)) for t, sn, s, v in rows]
    return [(t, sn, str(s), str(v) if v is not None else "—") for t, sn, s, v in rows]


# ── Section runners ───────────────────────────────────────────────────────────


def run_game_records(args, conn, team_id):
    team_col = team_id is None

    def run_batting_9inn():
        print_section("TEAM SINGLE GAME — BATTING (9 INNINGS)")
        for name, expr, val_label in GAME_BAT_RECORDS:
            raw = game_records_query(
                conn, args, expr, team_id, innings_filter=9, top=args.top
            )
            if team_col:
                rows = [(t, d, str(s), str(v), inn) for t, d, s, v, inn in raw]
            else:
                rows = [(d, str(s), str(v), inn) for _, d, s, v, inn in raw]
            print_game_record(name, rows, val_label, team_col=team_col)

    def run_batting_extra():
        print_section("TEAM SINGLE GAME — BATTING (EXTRA INNINGS 10+)")
        for name, expr, val_label in GAME_BAT_RECORDS:
            nine_best = get_game_9inn_best(conn, args, expr, team_id)
            raw = game_records_extra_query(
                conn, args, expr, nine_best, team_id, top=args.top
            )
            if team_col:
                rows = [(t, d, str(s), str(v), inn) for t, d, s, v, inn in raw]
            else:
                rows = [(d, str(s), str(v), inn) for _, d, s, v, inn in raw]
            print_game_record(name, rows, val_label, team_col=team_col)

    def run_pitching_9inn():
        print_section("TEAM SINGLE GAME — PITCHING (9 INNINGS)")
        for name, expr, val_label in GAME_PITCH_RECORDS:
            raw = game_records_query(
                conn, args, expr, team_id, pitching=True, innings_filter=9, top=args.top
            )
            if team_col:
                rows = [(t, d, str(s), str(v), inn) for t, d, s, v, inn in raw]
            else:
                rows = [(d, str(s), str(v), inn) for _, d, s, v, inn in raw]
            print_game_record(name, rows, val_label, team_col=team_col)

    def run_pitching_extra():
        print_section("TEAM SINGLE GAME — PITCHING (EXTRA INNINGS 10+)")
        for name, expr, val_label in GAME_PITCH_RECORDS:
            nine_best = get_game_9inn_best(conn, args, expr, team_id, pitching=True)
            raw = game_records_extra_query(
                conn, args, expr, nine_best, team_id, pitching=True, top=args.top
            )
            if team_col:
                rows = [(t, d, str(s), str(v), inn) for t, d, s, v, inn in raw]
            else:
                rows = [(d, str(s), str(v), inn) for _, d, s, v, inn in raw]
            print_game_record(name, rows, val_label, team_col=team_col)

    run_batting_9inn()
    run_batting_extra()
    run_pitching_9inn()
    run_pitching_extra()


def run_season_records(args, conn, team_id):
    team_col = team_id is None

    # Check rollup table available
    has_rollup = (
        conn.execute(
            "SELECT COUNT(*) FROM sqlite_master"
            " WHERE type='table' AND name='player_season_stats'"
        ).fetchone()[0]
        > 0
    )

    if not has_rollup:
        print("\n  (Season records unavailable — run build_season_stats.py --rebuild)")
        return

    print_section("TEAM SEASON — BATTING RECORDS")
    for name, expr, val_label in SEASON_BAT_RECORDS:
        rows = season_records_query(
            conn, args, expr, team_id, bat_or_pitch="bat", top=args.top
        )
        if not team_col:
            rows = [(s, v) for _, s, v in rows]
        print_season_record(name, rows, val_label, team_col=team_col)

    print_section("TEAM SEASON — PITCHING RECORDS")
    for name, expr, val_label in SEASON_PITCH_RECORDS:
        rows = season_records_query(
            conn, args, expr, team_id, bat_or_pitch="pitch", top=args.top
        )
        if not team_col:
            rows = [(s, v) for _, s, v in rows]
        print_season_record(name, rows, val_label, team_col=team_col)

    # IP
    rows = season_records_query(
        conn,
        args,
        "SUM(pss.pitch_outs)",
        team_id,
        bat_or_pitch="pitch",
        top=args.top,
        fmt_fn=lambda v: fmt_ip(int(v)) if v else "—",
    )
    if not team_col:
        rows = [(s, v) for _, s, v in rows]
    print_season_record("Most Innings Pitched", rows, "IP", team_col=team_col)


def run_series_records(args, conn, team_id):
    team_col = team_id is None

    print_section("TEAM SERIES — BATTING RECORDS")
    for name, expr, val_label in GAME_BAT_RECORDS:
        rows = series_records_query(conn, args, expr, team_id, top=args.top)
        if not team_col:
            rows = [(sn, s, v) for _, sn, s, v in rows]
        print_series_record(name, rows, val_label, team_col=team_col)

    print_section("TEAM SERIES — PITCHING RECORDS")
    for name, expr, val_label in GAME_PITCH_RECORDS:
        rows = series_records_query(
            conn, args, expr, team_id, pitching=True, top=args.top
        )
        if not team_col:
            rows = [(sn, s, v) for _, sn, s, v in rows]
        print_series_record(name, rows, val_label, team_col=team_col)

    # IP in series
    rows = series_records_query(
        conn,
        args,
        "SUM(pgs.pitch_outs)",
        team_id,
        pitching=True,
        top=args.top,
        fmt_fn=lambda v: fmt_ip(int(v)) if v else "—",
    )
    if not team_col:
        rows = [(sn, s, v) for _, sn, s, v in rows]
    print_series_record("Most Innings Pitched", rows, "IP", team_col=team_col)


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Team franchise records — single game, season, and series"
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help=f"Path to SQLite database (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--team",
        "-t",
        help="Filter to a specific team — city, mascot, full name, or UUID",
    )
    parser.add_argument("--teams", action="store_true", help="List all teams and exit")
    parser.add_argument(
        "--regular-season",
        action="store_true",
        help="Regular season games only (excludes playoffs)",
    )
    parser.add_argument(
        "--game", action="store_true", help="Show single-game records only"
    )
    parser.add_argument(
        "--season", action="store_true", help="Show season records only"
    )
    parser.add_argument(
        "--series", action="store_true", help="Show series records only"
    )
    parser.add_argument(
        "--top", type=int, default=5, help="Number of entries per record (default: 5)"
    )
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"Error: database not found at '{args.db}'")
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    if args.teams:
        teams = list_teams(conn)
        print(f"\n  {'City':<20} {'Mascot':<20} {'ID'}")
        print(f"  {'-'*20} {'-'*20} {'-'*36}")
        for t in teams:
            print(f"  {t['city']:<20} {t['mascot']:<20} {t['id']}")
        conn.close()
        return

    # Resolve team if provided
    team_id = None
    team_name = "All Teams"
    if args.team:
        try:
            team = resolve_team(conn, args.team)
            team_id = team["id"]
            team_name = team["name"].upper()
        except TeamResolverError as e:
            print(f"Error: {e}")
            sys.exit(1)

    # Default: show all scopes if none specified
    if not args.game and not args.season and not args.series:
        args.game = True
        args.season = True
        args.series = True

    scope_parts = [team_name]
    scope_parts.append("Regular Season" if args.regular_season else "All Games")
    scope = "  |  ".join(scope_parts)

    print(f"\n{'━' * 82}")
    print(f"  TEAM RECORDS  —  {scope}")
    print(f"{'━' * 82}")

    if args.game:
        run_game_records(args, conn, team_id)
    if args.season:
        run_season_records(args, conn, team_id)
    if args.series:
        run_series_records(args, conn, team_id)

    conn.close()
    print()


if __name__ == "__main__":
    main()
