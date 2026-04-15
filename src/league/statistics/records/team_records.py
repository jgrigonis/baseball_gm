# src/league/statistics/records/team_records.py
"""
All-time records for a specific team — both single-game and season bests.
Only counts stats accrued while the player was on that team.

Usage:
    python3 team_records.py --team "Vienna Maestros"
    python3 team_records.py --team Vienna
    python3 team_records.py --team Maestros
    python3 team_records.py --team <UUID>
    python3 team_records.py --team Vienna --regular-season
    python3 team_records.py --team Vienna --batting
    python3 team_records.py --team Vienna --pitching
    python3 team_records.py --team Vienna --top 10
    python3 team_records.py --teams          # list all teams and exit
"""

import argparse
import sys

from src.db.connection import get_connection
from src.util.team_resolver import resolve_team, list_teams, TeamResolverError

PA_PER_GAME = 3.1
IP_PER_GAME = 1.0


# ── Formatting ────────────────────────────────────────────────────────────────


def fmt_ip(outs):
    if outs is None:
        return "0.0"
    return f"{outs // 3}.{outs % 3}"


def print_section(title):
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def print_record(label, rows, value_label="Value", show_date=False, show_innings=False):
    """
    Rows are one of:
      (player, season, value)                        — season records
      (player, date, season, value)                  — single-game, no innings
      (player, date, season, value, innings)         — single-game, with innings
    """
    if not rows:
        # print(f"\n  {label}: (no data)")
        return
    print(f"\n  {label}")
    if show_innings:
        print(
            f"  {'#':<4} {'Player':<24} {'Date':<12} {'Season':<7} {value_label:<8} {'Inn'}"
        )
        print(f"  {'-'*4} {'-'*24} {'-'*12} {'-'*7} {'-'*8} {'-'*4}")
        for i, row in enumerate(rows, 1):
            player, date, season, value, innings = row
            print(
                f"  {i:<4} {player:<24} {date:<12} {season:<7} {str(value):<8} {innings}"
            )
    elif show_date:
        print(f"  {'#':<4} {'Player':<24} {'Date':<12} {'Season':<7} {value_label}")
        print(f"  {'-'*4} {'-'*24} {'-'*12} {'-'*7} {'-'*10}")
        for i, row in enumerate(rows, 1):
            player, date, season, value = row
            print(f"  {i:<4} {player:<24} {date:<12} {season:<7} {value}")
    else:
        print(f"  {'#':<4} {'Player':<24} {'Season':<7} {value_label}")
        print(f"  {'-'*4} {'-'*24} {'-'*7} {'-'*10}")
        for i, row in enumerate(rows, 1):
            player, season, value = row
            print(f"  {i:<4} {player:<24} {season:<7} {value}")


# ── Game filter helpers ───────────────────────────────────────────────────────


def game_clauses(args):
    """Base WHERE clauses and params for game-level queries."""
    clauses = ["g.completed = 1"]
    params = []
    if args.regular_season:
        clauses.append("g.series_id IS NULL")
    return clauses, params


def games_per_team_cte(regular_season):
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


# ── Single-game queries ───────────────────────────────────────────────────────


def single_game_bat_query(conn, args, team_id, field, innings_filter=None, top=5):
    clauses, params = game_clauses(args)
    clauses.append("pgs.team_id = %s")
    params.append(team_id)
    if innings_filter == 9:
        clauses.append("g.innings_played = 9")
    elif innings_filter == "extra":
        clauses.append("g.innings_played > 9")
    where = " AND ".join(clauses)

    sql = f"""
        SELECT
            p.first_name || ' ' || p.last_name,
            g.game_date,
            s.year,
            {field},
            g.innings_played
        FROM player_game_stats pgs
        JOIN players p ON pgs.player_id = p.id
        JOIN games g ON pgs.game_id = g.id
        JOIN seasons s ON g.season_id = s.id
        WHERE {where}
        ORDER BY {field} DESC
        LIMIT {top}
    """
    return conn.execute(sql, params).fetchall()


def single_game_pitch_query(
    conn, args, team_id, field, innings_filter=None, top=5, fmt_fn=None
):
    clauses, params = game_clauses(args)
    clauses.append("pgs.team_id = %s")
    clauses.append("pgs.pitch_game_played = 1")
    params.append(team_id)
    if innings_filter == 9:
        clauses.append("g.innings_played = 9")
    elif innings_filter == "extra":
        clauses.append("g.innings_played > 9")
    where = " AND ".join(clauses)

    sql = f"""
        SELECT
            p.first_name || ' ' || p.last_name,
            g.game_date,
            s.year,
            {field},
            g.innings_played
        FROM player_game_stats pgs
        JOIN players p ON pgs.player_id = p.id
        JOIN games g ON pgs.game_id = g.id
        JOIN seasons s ON g.season_id = s.id
        WHERE {where}
        ORDER BY {field} DESC
        LIMIT {top}
    """
    raw = conn.execute(sql, params).fetchall()
    if fmt_fn:
        return [(p, d, str(s), fmt_fn(v), inn) for p, d, s, v, inn in raw]
    return [(p, d, str(s), str(v), inn) for p, d, s, v, inn in raw]


def get_9inn_best(conn, args, team_id, field, pitching=False):
    """Top value in 9-inning games — used as floor for extra-inning display."""
    clauses, params = game_clauses(args)
    clauses.append("pgs.team_id = %s")
    clauses.append("g.innings_played = 9")
    params.append(team_id)
    if pitching:
        clauses.append("pgs.pitch_game_played = 1")
    where = " AND ".join(clauses)
    sql = f"""
        SELECT {field} FROM player_game_stats pgs
        JOIN games g ON pgs.game_id = g.id
        WHERE {where}
        ORDER BY {field} DESC LIMIT 1
    """
    row = conn.execute(sql, params).fetchone()
    return row[field] if row else None


TOTAL_BASES_EXPR = (
    "(pgs.bat_hits - pgs.bat_doubles - pgs.bat_triples - pgs.bat_home_runs)"
    " + (2 * pgs.bat_doubles)"
    " + (3 * pgs.bat_triples)"
    " + (4 * pgs.bat_home_runs)"
)

SINGLE_GAME_BAT = [
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

SINGLE_GAME_PITCH = [
    ("Most Strikeouts", "pgs.pitch_strike_outs", "K"),
    ("Most Walks Allowed", "pgs.pitch_walks", "BB"),
    ("Most HR Allowed", "pgs.pitch_home_runs", "HR"),
    ("Most Hits Allowed", "pgs.pitch_hits", "H"),
]


def run_single_game_batting(args, conn, team_id):
    print_section("SINGLE GAME BATTING — 9 INNINGS")
    for name, field, val_label in SINGLE_GAME_BAT:
        rows = single_game_bat_query(
            conn, args, team_id, field, innings_filter=9, top=args.top
        )
        rows = [(p, d, str(s), str(v), inn) for p, d, s, v, inn in rows]
        print_record(
            name, [(p, d, s, v) for p, d, s, v, _ in rows], val_label, show_date=True
        )

    print_section("SINGLE GAME BATTING — EXTRA INNINGS (10+)")
    for name, field, val_label in SINGLE_GAME_BAT:
        nine_best = get_9inn_best(conn, args, team_id, field)
        clauses, params = game_clauses(args)
        clauses.append("pgs.team_id = %s")
        clauses.append("g.innings_played > 9")
        if nine_best is not None:
            clauses.append(f"{field} > %s")
            params.extend([team_id, nine_best])
        else:
            params.append(team_id)
        where = " AND ".join(clauses)
        sql = f"""
            SELECT p.first_name || ' ' || p.last_name, g.game_date, s.year,
                   {field}, g.innings_played
            FROM player_game_stats pgs
            JOIN players p ON pgs.player_id = p.id
            JOIN games g ON pgs.game_id = g.id
            JOIN seasons s ON g.season_id = s.id
            WHERE {where}
            ORDER BY {field} DESC LIMIT {args.top}
        """
        raw = conn.execute(sql, params).fetchall()
        rows = [(p, d, str(s), str(v)) for p, d, s, v, _ in raw]
        print_record(name, rows, val_label, show_date=True)


def run_single_game_pitching(args, conn, team_id):
    print_section("SINGLE GAME PITCHING — 9 INNINGS")
    for name, field, val_label in SINGLE_GAME_PITCH:
        rows = single_game_pitch_query(
            conn, args, team_id, field, innings_filter=9, top=args.top
        )
        print_record(
            name, [(p, d, s, v) for p, d, s, v, _ in rows], val_label, show_date=True
        )

    # IP in 9-inning games (suppress — always 9.0)

    print_section("SINGLE GAME PITCHING — EXTRA INNINGS (10+)")
    for name, field, val_label in SINGLE_GAME_PITCH:
        nine_best = get_9inn_best(conn, args, team_id, field, pitching=True)
        clauses, params = game_clauses(args)
        clauses.append("pgs.team_id = %s")
        clauses.append("pgs.pitch_game_played = 1")
        clauses.append("g.innings_played > 9")
        if nine_best is not None:
            clauses.append(f"{field} > %s")
            params.extend([team_id, nine_best])
        else:
            params.append(team_id)
        where = " AND ".join(clauses)
        sql = f"""
            SELECT p.first_name || ' ' || p.last_name, g.game_date, s.year,
                   {field}, g.innings_played
            FROM player_game_stats pgs
            JOIN players p ON pgs.player_id = p.id
            JOIN games g ON pgs.game_id = g.id
            JOIN seasons s ON g.season_id = s.id
            WHERE {where}
            ORDER BY {field} DESC LIMIT {args.top}
        """
        raw = conn.execute(sql, params).fetchall()
        rows = [(p, d, str(s), str(v), inn) for p, d, s, v, inn in raw]
        print_record(
            name, [(p, d, s, v) for p, d, s, v, _ in rows], val_label, show_date=True
        )

    # IP in extra innings
    nine_best_outs = get_9inn_best(conn, args, team_id, "pgs.pitch_outs", pitching=True)
    clauses, params = game_clauses(args)
    clauses.append("pgs.team_id = %s")
    clauses.append("pgs.pitch_game_played = 1")
    clauses.append("g.innings_played > 9")
    if nine_best_outs is not None:
        clauses.append("pgs.pitch_outs > %s")
        params.extend([team_id, nine_best_outs])
    else:
        params.append(team_id)
    where = " AND ".join(clauses)
    sql = f"""
        SELECT p.first_name || ' ' || p.last_name, g.game_date, s.year,
               pgs.pitch_outs, g.innings_played
        FROM player_game_stats pgs
        JOIN players p ON pgs.player_id = p.id
        JOIN games g ON pgs.game_id = g.id
        JOIN seasons s ON g.season_id = s.id
        WHERE {where}
        ORDER BY pgs.pitch_outs DESC LIMIT {args.top}
    """
    raw = conn.execute(sql, params).fetchall()
    ip_rows = [(p, d, str(s), fmt_ip(v)) for p, d, s, v, _ in raw]
    print_record("Most Innings Pitched", ip_rows, "IP", show_date=True)


# ── Season queries ────────────────────────────────────────────────────────────

BAT_PA_EXPR = (
    "SUM(pss.bat_ab) + SUM(pss.bat_walks) + SUM(pss.bat_hbp) + SUM(pss.bat_sac_flys)"
)
BAT_QUALIFY = f"({BAT_PA_EXPR}) >= {PA_PER_GAME} * gpt.games_per_team"
PITCH_QUALIFY = f"(SUM(pss.pitch_outs) / 3.0) >= {IP_PER_GAME} * gpt.games_per_team"

SEASON_BAT_COUNTING = [
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

SEASON_BAT_RATES = [
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

SEASON_PITCH_COUNTING = [
    ("Most Strikeouts", "SUM(pss.pitch_strike_outs)", "K"),
    ("Most Wins", "SUM(pss.pitch_wins)", "W"),
    ("Most Saves", "SUM(pss.pitch_saves)", "SV"),
    ("Most Walks Allowed", "SUM(pss.pitch_walks)", "BB"),
    ("Most HR Allowed", "SUM(pss.pitch_home_runs)", "HR"),
    ("Most Hits Allowed", "SUM(pss.pitch_hits)", "H"),
]

ERA_EXPR = (
    "CAST(SUM(pss.pitch_earned_runs) AS REAL)" " / NULLIF(SUM(pss.pitch_outs), 0) * 27"
)
WHIP_EXPR = (
    "CAST(SUM(pss.pitch_walks) + SUM(pss.pitch_hits) AS REAL)"
    " / NULLIF(SUM(pss.pitch_outs) / 3.0, 0)"
)


def season_counting(conn, args, team_id, expr, bat_or_pitch="bat", fmt_fn=None):
    ps_filter = "AND NOT pss.is_postseason" if args.regular_season else ""
    sql = f"""
        SELECT
            p.first_name || ' ' || p.last_name,
            s.year,
            {expr} AS value
        FROM player_season_stats pss
        JOIN players p ON pss.player_id = p.id
        JOIN seasons s ON pss.season_id = s.id
        WHERE pss.team_id = %s
          AND pss.{bat_or_pitch}_games_played > 0
          {ps_filter}
        GROUP BY pss.player_id, pss.season_id
        ORDER BY value DESC
        LIMIT {args.top}
    """
    rows = conn.execute(sql, (team_id,)).fetchall()
    if fmt_fn:
        return [(p, str(s), fmt_fn(v)) for p, s, v in rows]
    return [(p, str(s), str(v) if v is not None else "—") for p, s, v in rows]


def season_rate_desc(conn, args, team_id, expr, qualify_expr, fmt=".3f"):
    ps_filter = "AND NOT pss.is_postseason" if args.regular_season else ""
    sql = f"""
        WITH {games_per_team_cte(args.regular_season)}
        SELECT
            p.first_name || ' ' || p.last_name,
            s.year,
            {expr} AS value
        FROM player_season_stats pss
        JOIN players p ON pss.player_id = p.id
        JOIN seasons s ON pss.season_id = s.id
        JOIN games_per_team gpt ON gpt.season_id = pss.season_id
        WHERE pss.team_id = %s
          AND pss.bat_games_played > 0
          {ps_filter}
        GROUP BY pss.player_id, pss.season_id
        HAVING {qualify_expr}
        ORDER BY value DESC
        LIMIT {args.top}
    """
    rows = conn.execute(sql, (team_id,)).fetchall()
    return [
        (p, str(s), f"{float(v):{fmt}}" if v is not None else "—") for p, s, v in rows
    ]


def season_rate_asc(conn, args, team_id, expr, qualify_expr, fmt=".2f"):
    ps_filter = "AND NOT pss.is_postseason" if args.regular_season else ""
    sql = f"""
        WITH {games_per_team_cte(args.regular_season)}
        SELECT
            p.first_name || ' ' || p.last_name,
            s.year,
            {expr} AS value
        FROM player_season_stats pss
        JOIN players p ON pss.player_id = p.id
        JOIN seasons s ON pss.season_id = s.id
        JOIN games_per_team gpt ON gpt.season_id = pss.season_id
        WHERE pss.team_id = %s
          AND pss.pitch_games_played > 0
          {ps_filter}
        GROUP BY pss.player_id, pss.season_id
        HAVING {qualify_expr}
        ORDER BY value ASC
        LIMIT {args.top}
    """
    rows = conn.execute(sql, (team_id,)).fetchall()
    return [
        (p, str(s), f"{float(v):{fmt}}" if v is not None else "—") for p, s, v in rows
    ]


def run_season_batting(args, conn, team_id):
    print_section("SEASON BATTING RECORDS")

    for name, expr, val_label in SEASON_BAT_COUNTING:
        rows = season_counting(conn, args, team_id, expr, bat_or_pitch="bat")
        print_record(name, rows, val_label)

    for name, expr, val_label, fmt in SEASON_BAT_RATES:
        rows = season_rate_desc(conn, args, team_id, expr, BAT_QUALIFY, fmt=fmt)
        print_record(name, rows, val_label)


def run_season_pitching(args, conn, team_id):
    print_section("SEASON PITCHING RECORDS")

    for name, expr, val_label in SEASON_PITCH_COUNTING:
        rows = season_counting(conn, args, team_id, expr, bat_or_pitch="pitch")
        print_record(name, rows, val_label)

    rows = season_counting(
        conn,
        args,
        team_id,
        "SUM(pss.pitch_outs)",
        bat_or_pitch="pitch",
        fmt_fn=lambda v: fmt_ip(int(v)) if v else "—",
    )
    print_record("Most Innings Pitched", rows, "IP")

    rows = season_rate_asc(conn, args, team_id, ERA_EXPR, PITCH_QUALIFY)
    print_record("Best ERA (qualified)", rows, "ERA")

    rows = season_rate_asc(conn, args, team_id, WHIP_EXPR, PITCH_QUALIFY, fmt=".3f")
    print_record("Best WHIP (qualified)", rows, "WHIP")


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="All-time records for a specific team")
    parser.add_argument(
        "--team", "-t", help="Team to look up — city, mascot, full name, or UUID"
    )
    parser.add_argument("--teams", action="store_true", help="List all teams and exit")
    parser.add_argument(
        "--regular-season",
        action="store_true",
        help="Regular season only — excludes playoff games",
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

    conn = get_connection()

    if args.teams:
        teams = list_teams(conn)
        print(f"\n  {'City':<20} {'Mascot':<20} {'ID'}")
        print(f"  {'-'*20} {'-'*20} {'-'*36}")
        for t in teams:
            print(f"  {t['city']:<20} {t['mascot']:<20} {t['id']}")
        conn.close()
        return

    if not args.team:
        print("Error: provide --team or use --teams to list available teams")
        sys.exit(1)

    try:
        team = resolve_team(conn, args.team)
    except TeamResolverError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if not args.batting and not args.pitching:
        args.batting = True
        args.pitching = True

    # Check rollup table for season records
    has_rollup = (
        conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='player_season_stats'"
        ).fetchone()["count"]
        > 0
    )

    scope = "Regular Season" if args.regular_season else "All Games (inc. Playoffs)"

    print(f"\n{'━' * 78}")
    print(f"  {team['name'].upper()} — ALL-TIME RECORDS  |  {scope}")
    print(f"{'━' * 78}")

    # Single-game records (always available)
    if args.batting:
        run_single_game_batting(args, conn, team["id"])
    if args.pitching:
        run_single_game_pitching(args, conn, team["id"])

    # Season records (requires rollup)
    if has_rollup:
        if args.batting:
            run_season_batting(args, conn, team["id"])
        if args.pitching:
            run_season_pitching(args, conn, team["id"])
    else:
        print("\n  (Season records unavailable — run build_season_stats.py --rebuild)")

    conn.close()
    print()


if __name__ == "__main__":
    main()
