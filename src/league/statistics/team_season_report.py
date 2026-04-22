# src/league/statistics/team_season_report.py
"""
Generate batting and pitching CSV reports for a single team (or all teams) in a given season.

Usage:
    python team_season_report.py --id <season> --team milan
    python team_season_report.py --id <season> --all
"""

import argparse
import csv
from pathlib import Path

from src.db.connection import get_connection
from src.db.repositories.team_repo import TeamRepository
from src.league.season_resolver import resolve_season
from src.util.locations import TEMP_FILES
from src.util.team_resolver import resolve_team_id, TeamResolverError

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

BATTING_QUERY = """
SELECT
    p.id                                            AS player_id,
    p.first_name || ' ' || p.last_name              AS name,
    p.position,
    p.bats,

    SUM(pgs.bat_game_played)                        AS G,
    SUM(pgs.bat_game_started)                       AS GS,
    SUM(pgs.bat_ab)                                 AS AB,
    SUM(pgs.bat_ab + pgs.bat_walks + pgs.bat_hbp + pgs.bat_sac_flys + pgs.bat_sac_bunts)
                                                    AS PA,
    SUM(pgs.bat_hits)                               AS H,
    SUM(pgs.bat_doubles)                            AS "2B",
    SUM(pgs.bat_triples)                            AS "3B",
    SUM(pgs.bat_home_runs)                          AS HR,
    SUM(pgs.bat_rbi)                                AS RBI,
    SUM(pgs.bat_runs)                               AS R,
    SUM(pgs.bat_walks)                              AS BB,
    SUM(pgs.bat_strike_outs)                        AS SO,
    SUM(pgs.bat_stolen_bases)                       AS SB,
    SUM(pgs.bat_caught_stealing)                    AS CS,
    SUM(pgs.bat_hbp)                                AS HBP,
    SUM(pgs.bat_sac_flys)                           AS SF,
    SUM(pgs.bat_sac_bunts)                          AS SH,
    SUM(pgs.bat_gdp)                                AS GIDP,

    CASE
        WHEN SUM(pgs.bat_ab) > 0
        THEN ROUND(CAST(SUM(pgs.bat_hits) AS REAL) / SUM(pgs.bat_ab), 3)
        ELSE NULL
    END                                             AS AVG,

    CASE
        WHEN SUM(pgs.bat_ab + pgs.bat_walks + pgs.bat_hbp + pgs.bat_sac_flys + pgs.bat_sac_bunts) > 0
        THEN ROUND(
            CAST(SUM(pgs.bat_hits) + SUM(pgs.bat_walks) + SUM(pgs.bat_hbp) AS REAL)
            / SUM(pgs.bat_ab + pgs.bat_walks + pgs.bat_hbp + pgs.bat_sac_flys + pgs.bat_sac_bunts), 3)
        ELSE NULL
    END                                             AS OBP,

    CASE
        WHEN SUM(pgs.bat_ab) > 0
        THEN ROUND(
            CAST(
                SUM(pgs.bat_hits)
                + SUM(pgs.bat_doubles)
                + 2 * SUM(pgs.bat_triples)
                + 3 * SUM(pgs.bat_home_runs)
            AS REAL) / SUM(pgs.bat_ab), 3)
        ELSE NULL
    END                                             AS SLG

FROM players p
JOIN player_game_stats pgs ON p.id = pgs.player_id
JOIN games g               ON pgs.game_id = g.id
WHERE g.season_id  = %(season_id)s
  AND g.completed  = 1
  AND pgs.team_id  = %(team_id)s
  AND (pgs.bat_ab > 0 OR pgs.bat_game_played > 0)
GROUP BY p.id, p.first_name, p.last_name, p.position, p.bats
ORDER BY SUM(pgs.bat_ab + pgs.bat_walks + pgs.bat_hbp + pgs.bat_sac_flys + pgs.bat_sac_bunts) DESC,
         p.last_name, p.first_name
"""

PITCHING_QUERY = """
SELECT
    p.id                                            AS player_id,
    p.first_name || ' ' || p.last_name              AS name,
    p.throws,

    SUM(pgs.pitch_game_played)                      AS G,
    SUM(pgs.pitch_game_started)                     AS GS,
    SUM(pgs.pitch_win)                              AS W,
    SUM(pgs.pitch_loss)                             AS L,
    SUM(pgs.pitch_save)                             AS SV,

    SUM(pgs.pitch_outs) / 3                         AS IP_full,
    SUM(pgs.pitch_outs) % 3                         AS IP_partial,

    SUM(pgs.pitch_hits)                             AS H,
    SUM(pgs.pitch_runs)                             AS R,
    SUM(pgs.pitch_earned_runs)                      AS ER,
    SUM(pgs.pitch_walks)                            AS BB,
    SUM(pgs.pitch_strike_outs)                      AS SO,
    SUM(pgs.pitch_home_runs)                        AS HR,
    SUM(pgs.pitch_count)                            AS PC,
    SUM(pgs.pitch_hit_batters)                      AS HBP,

    CASE
        WHEN SUM(pgs.pitch_outs) > 0
        THEN ROUND(9.0 * SUM(pgs.pitch_earned_runs) / (SUM(pgs.pitch_outs) / 3.0), 2)
        ELSE NULL
    END                                             AS ERA,

    CASE
        WHEN SUM(pgs.pitch_outs) > 0
        THEN ROUND(
            CAST(SUM(pgs.pitch_hits) + SUM(pgs.pitch_walks) AS REAL)
            / (SUM(pgs.pitch_outs) / 3.0), 3)
        ELSE NULL
    END                                             AS WHIP,

    CASE
        WHEN SUM(pgs.pitch_outs) > 0
        THEN ROUND(9.0 * SUM(pgs.pitch_strike_outs) / (SUM(pgs.pitch_outs) / 3.0), 2)
        ELSE NULL
    END                                             AS "K/9",

    CASE
        WHEN SUM(pgs.pitch_outs) > 0
        THEN ROUND(9.0 * SUM(pgs.pitch_walks) / (SUM(pgs.pitch_outs) / 3.0), 2)
        ELSE NULL
    END                                             AS "BB/9",

    CASE
        WHEN SUM(pgs.pitch_game_played) > 0
        THEN ROUND(CAST(SUM(pgs.pitch_count) AS REAL) / SUM(pgs.pitch_game_played), 1)
        ELSE NULL
    END                                             AS "PC/G"

FROM players p
JOIN player_game_stats pgs ON p.id = pgs.player_id
JOIN games g               ON pgs.game_id = g.id
WHERE g.season_id  = %(season_id)s
  AND g.completed  = 1
  AND pgs.team_id  = %(team_id)s
  AND pgs.pitch_outs > 0
GROUP BY p.id, p.first_name, p.last_name, p.throws
ORDER BY SUM(pgs.pitch_outs) DESC, p.last_name, p.first_name
"""

ALL_TEAMS_QUERY = """
SELECT id, city, mascot FROM teams ORDER BY city, mascot
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# def get_team_name(conn, team_id: str) -> str:
#     row = conn.execute(
#         "SELECT city, mascot FROM teams WHERE id = %s", (team_id,)
#     ).fetchone()
#     return f"{row['city']} {row['mascot']}" if row else team_id


def write_batting_csv(conn, season_id: str, team_id: str, out_path: Path) -> int:
    rows = conn.execute(
        BATTING_QUERY, {"season_id": season_id, "team_id": team_id}
    ).fetchall()
    if not rows:
        return 0

    fields = [
        "player_id",
        "name",
        "position",
        "bats",
        "G",
        "GS",
        "AB",
        "PA",
        "H",
        "2B",
        "3B",
        "HR",
        "RBI",
        "R",
        "BB",
        "SO",
        "SB",
        "CS",
        "HBP",
        "SF",
        "SH",
        "GIDP",
        "AVG",
        "OBP",
        "SLG",
        "OPS",
    ]

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            d = dict(row)
            obp = d.get("OBP")
            slg = d.get("SLG")
            d["OPS"] = (
                round(obp + slg, 3) if obp is not None and slg is not None else None
            )
            writer.writerow({k: d.get(k) for k in fields})

    return len(rows)


def write_pitching_csv(conn, season_id: str, team_id: str, out_path: Path) -> int:
    rows = conn.execute(
        PITCHING_QUERY, {"season_id": season_id, "team_id": team_id}
    ).fetchall()
    if not rows:
        return 0

    fields = [
        "player_id",
        "name",
        "throws",
        "G",
        "GS",
        "W",
        "L",
        "SV",
        "IP",
        "H",
        "R",
        "BB",
        "SO",
        "HR",
        "PC",
        "HBP",
        "ERA",
        "WHIP",
        "K/9",
        "BB/9",
        "PC/G",
    ]

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            d = dict(row)
            full = d.pop("IP_full", 0)
            partial = d.pop("IP_partial", 0)
            d["IP"] = f"{full}.{partial}"
            writer.writerow({k: d.get(k) for k in fields})

    return len(rows)


def report_one_team(
    conn, season_id: str, team_id: str, season_slug: str, out_dir: Path
) -> None:
    """Generate batting and pitching CSVs for a single team."""
    team_repo = TeamRepository(conn)
    team_name = team_repo.get_city_mascot(team_id)
    #team_name = get_team_name(conn, team_id)
    slug = team_name.lower().replace(" ", "_")

    batting_path = out_dir / f"{slug}_{season_slug}_batting.csv"
    pitching_path = out_dir / f"{slug}_{season_slug}_pitching.csv"

    n_bat = write_batting_csv(conn, season_id, team_id, batting_path)
    n_pit = write_pitching_csv(conn, season_id, team_id, pitching_path)

    bat_str = f"{n_bat} players" if n_bat else "no data"
    pit_str = f"{n_pit} pitchers" if n_pit else "no data"
    print(f"  {team_name:<30}  batting: {bat_str:<12}  pitching: {pit_str}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def get_args():
    p = argparse.ArgumentParser(
        description="Generate batting and pitching CSVs for a team (or all teams) in a season."
    )
    p.add_argument(
        "--id", "-i", required=True, help="Season ID (or partial name/year match)"
    )
    p.add_argument("--team", "-t", default=None, help="Team name (city or mascot)")
    p.add_argument(
        "--all", "-a", action="store_true", help="Generate reports for all teams"
    )
    p.add_argument("--out-dir", "-o", default=f"{TEMP_FILES}", help="Output directory")
    return p.parse_args()


def main():
    args = get_args()

    if not args.team and not args.all:
        print("❌ Provide --team <name> or --all")
        return

    season_id, season_label = resolve_season(args.id)
    conn = get_connection()

    season_slug = (
        season_label.lower().replace(" ", "_").replace("(", "").replace(")", "")
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"📋 {season_label} Season Reports → {out_dir}/")

    if args.all:
        teams = conn.execute(ALL_TEAMS_QUERY).fetchall()
        print(f"   Generating reports for {len(teams)} teams...\n")
        for team in teams:
            report_one_team(conn, season_id, team["id"], season_slug, out_dir)
    else:
        try:
            team_id = resolve_team_id(conn, args.team)
        except TeamResolverError as e:
            print(f"❌ {e}")
            conn.close()
            return
        report_one_team(conn, season_id, team_id, season_slug, out_dir)

    conn.close()
    print(f"\n✅ Done. {len(list(out_dir.glob('*.csv')))} CSV files in {out_dir}/")


if __name__ == "__main__":
    main()
