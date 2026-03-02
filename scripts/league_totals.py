"""
Display aggregate league-wide stats for a season.

Usage:
    python league_totals.py --db leagues/league.db --id <season_id>
    python league_totals.py --db leagues/league.db  # auto-selects if one season
"""

import argparse
import sqlite3
from pathlib import Path

WIDTH = 58

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(
        description="League-wide stat totals for a season."
    )
    parser.add_argument(
        "--db", default="leagues/league.db", help="Path to SQLite database"
    )
    parser.add_argument("--id", "-i", help="Season ID (or partial name/year match)")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Season resolution
# ---------------------------------------------------------------------------


def resolve_season(conn, season_arg: str | None) -> tuple[str, str]:
    """Return (season_id, season_label). Exits if ambiguous or not found."""
    cur = conn.cursor()
    cur.execute("SELECT id, year, name FROM seasons ORDER BY year")
    seasons = cur.fetchall()

    if not seasons:
        print("No seasons found in database.")
        raise SystemExit(1)

    if season_arg:
        for s in seasons:
            if (
                str(s["year"]) == season_arg
                or s["name"] == season_arg
                or s["id"] == season_arg
            ):
                return s["id"], f"{s['name']} ({s['year']})"
        print(f"Season '{season_arg}' not found. Available:")
        for s in seasons:
            print(f"  id={s['id']}  year={s['year']}  name={s['name']}")
        raise SystemExit(1)

    if len(seasons) == 1:
        s = seasons[0]
        return s["id"], f"{s['name']} ({s['year']})"

    print("Multiple seasons found — use --season to specify:")
    for s in seasons:
        print(f"  id={s['id']}  year={s['year']}  name={s['name']}")
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def fetch_totals(conn, season_id: str) -> dict:
    cur = conn.cursor()

    # Games played (completed)
    cur.execute(
        """
        SELECT COUNT(*) as games
        FROM games
        WHERE season_id = ? AND completed = 1
        """,
        (season_id,),
    )
    games = cur.fetchone()["games"] or 1  # avoid division by zero

    # Batting + pitching aggregates from player_game_stats
    cur.execute(
        """
        SELECT
            SUM(pgs.bat_hits)                                           as hits,
            SUM(pgs.bat_runs)                                           as runs,
            SUM(pgs.bat_doubles)                                        as doubles,
            SUM(pgs.bat_triples)                                        as triples,
            SUM(pgs.bat_home_runs)                                      as home_runs,
            SUM(pgs.bat_hits - pgs.bat_doubles - pgs.bat_triples
                - pgs.bat_home_runs)                                    as singles,
            SUM(pgs.bat_walks)                                          as walks,
            SUM(pgs.bat_strike_outs)                                    as strikeouts,
            SUM(pgs.bat_rbi)                                            as rbi,
            SUM(pgs.bat_sac_flys)                                       as sac_flies,
            SUM(pgs.bat_sac_bunts)                                      as sac_bunts,
            SUM(pgs.bat_gdp)                                            as double_plays,
            SUM(pgs.bat_stolen_bases)                                   as stolen_bases,
            SUM(pgs.bat_caught_stealing)                                as caught_stealing,
            SUM(pgs.bat_hbp)                                            as hbp,
            SUM(pgs.bat_ab)                                             as at_bats,

            -- Pitching
            SUM(pgs.pitch_walks)                                        as p_walks,
            SUM(pgs.pitch_hits)                                         as p_hits,
            SUM(pgs.pitch_outs)                                         as p_outs,
            SUM(pgs.pitch_balks)                                        as balks,
            SUM(pgs.pitch_wild_pitches)                                 as wild_pitches,
            SUM(pgs.pitch_pickoffs)                                       as pickoffs,


            -- Fielding
            SUM(pgs.field_putouts)                                      as putouts,
            SUM(pgs.field_assists)                                      as assists,
            SUM(pgs.field_errors)                                       as errors,
            SUM(pgs.passed_balls)                                       as passed_balls
        FROM player_game_stats pgs
        JOIN games g ON g.id = pgs.game_id
        WHERE g.season_id = ? AND g.completed = 1
        """,
        (season_id,),
    )
    row = cur.fetchone()

    # OBP / AVG / SLG / WHIP
    ab = row["at_bats"] or 1
    hits = row["hits"] or 0
    walks = row["walks"] or 0
    hbp = row["hbp"] or 0
    sf = row["sac_flies"] or 0
    doubles = row["doubles"] or 0
    triples = row["triples"] or 0
    hrs = row["home_runs"] or 0

    obp_denom = ab + walks + hbp + sf
    avg = hits / ab
    obp = (hits + walks + hbp) / obp_denom if obp_denom else 0
    slg = (hits + doubles + 2 * triples + 3 * hrs) / ab
    ops = obp + slg

    p_outs = row["p_outs"] or 1
    p_ip = p_outs / 3
    whip = (row["p_walks"] + row["p_hits"]) / p_ip if p_ip else 0

    return {
        "games": games,
        # Batting counting
        "hits": row["hits"] or 0,
        "runs": row["runs"] or 0,
        "singles": row["singles"] or 0,
        "doubles": doubles,
        "triples": triples,
        "home_runs": hrs,
        "walks": walks,
        "strikeouts": row["strikeouts"] or 0,
        "rbi": row["rbi"] or 0,
        "sac_flies": sf,
        "sac_bunts": row["sac_bunts"] or 0,
        "double_plays": row["double_plays"] or 0,
        "hbp": hbp,
        # Batting rate
        "avg": avg,
        "obp": obp,
        "slg": slg,
        "ops": ops,
        # Pitching
        "balks": row["balks"] or 0,
        "wild_pitches": row["wild_pitches"] or 0,
        "whip": whip,
        # Baserunning
        "stolen_bases": row["stolen_bases"] or 0,
        "caught_stealing": row["caught_stealing"] or 0,
        "pickoffs": row["pickoffs"] or 0,
        # Fielding
        "putouts": row["putouts"] or 0,
        "assists": row["assists"] or 0,
        "errors": row["errors"] or 0,
        "passed_balls": row["passed_balls"] or 0,
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def _pgm(value: int, games: int) -> str:
    """Format a value and its per-game rate."""
    return f"{value:>8,}  ({value / games / 2.0:>6.2f}/g)"


def display(totals: dict, season_label: str):
    g = totals["games"]

    print()
    print("=" * WIDTH)
    print(f"  LEAGUE TOTALS — {season_label}")
    print(f"  {g} games played")
    print("=" * WIDTH)

    print("\nBATTING                       Total    Per Game")
    print("-" * WIDTH)
    for label, key in [
        ("Hits", "hits"),
        ("Runs", "runs"),
        ("Singles", "singles"),
        ("Doubles", "doubles"),
        ("Triples", "triples"),
        ("Home Runs", "home_runs"),
        ("Walks", "walks"),
        ("Strikeouts", "strikeouts"),
        ("RBI", "rbi"),
        ("HBP", "hbp"),
        ("Sac Flies", "sac_flies"),
        ("Sac Bunts", "sac_bunts"),
        ("Double Plays", "double_plays"),
    ]:
        print(f"  {label:<24}  {_pgm(totals[key], g)}")

    print("\nBATTING RATES")
    print("-" * WIDTH)
    print(f"  {'AVG':<24}  {totals['avg']:.3f}")
    print(f"  {'OBP':<24}  {totals['obp']:.3f}")
    print(f"  {'SLG':<24}  {totals['slg']:.3f}")
    print(f"  {'OPS':<24}  {totals['ops']:.3f}")

    print("\nPITCHING                      Total    Per Game")
    print("-" * WIDTH)
    for label, key in [
        ("Balks", "balks"),
        ("Wild Pitches", "wild_pitches"),
    ]:
        print(f"  {label:<24}  {_pgm(totals[key], g)}")
    print(f"  {'WHIP':<24}  {totals['whip']:.3f}")

    print("\nBASERUNNING                   Total    Per Game")
    print("-" * WIDTH)
    for label, key in [
        ("Stolen Bases", "stolen_bases"),
        ("Caught Stealing", "caught_stealing"),
        ("Pickoffs", "pickoffs"),
    ]:
        print(f"  {label:<24}  {_pgm(totals[key], g)}")

    sb = totals["stolen_bases"]
    sba = sb + totals["caught_stealing"]
    sbp = sb / sba if sba else 0
    print(f"  {'SB%':<24}  {sbp:.3f}  ({sb}/{sba})")

    print("\nFIELDING                      Total    Per Game")
    print("-" * WIDTH)
    for label, key in [
        ("Putouts", "putouts"),
        ("Assists", "assists"),
        ("Errors", "errors"),
        ("Passed Balls", "passed_balls"),
    ]:
        print(f"  {label:<24}  {_pgm(totals[key], g)}")

    tc = totals["putouts"] + totals["assists"] + totals["errors"]
    fpct = (totals["putouts"] + totals["assists"]) / tc if tc else 0
    print(f"  {'Fielding %':<24}  {fpct:.4f}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    args = parse_args()
    db_path = Path(args.db)

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        raise SystemExit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    season_id, season_label = resolve_season(conn, args.id)
    totals = fetch_totals(conn, season_id)
    conn.close()

    display(totals, season_label)


if __name__ == "__main__":
    main()
