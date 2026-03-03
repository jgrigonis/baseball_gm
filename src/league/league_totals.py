# scripts/league_totals.py
"""
Display aggregate league-wide stats for a season with expected real-world ranges.

Usage:
    python league_totals.py --db leagues/league.db --id <season_id>
    python league_totals.py --db leagues/league.db  # auto-selects if one season
"""

import argparse
import sqlite3

from src.league.season_resolver import resolve_season

WIDTH = 72

# ---------------------------------------------------------------------------
# Expected ranges (per team per game)
# ---------------------------------------------------------------------------

RANGES = {
    # Batting counting
    "hits": (8.0, 9.4),
    "runs": (4.0, 4.9),
    "singles": (5.1, 6.2),
    "doubles": (1.5, 1.9),
    "triples": (0.12, 0.20),
    "home_runs": (0.85, 1.4),
    "walks": (2.88, 3.42),
    "strikeouts": (6.3, 8.8),
    "rbi": (3.86, 4.63),
    "hbp": (0.3, 0.4),
    "sac_flies": (0.22, 0.31),
    "sac_bunts": (0.1, 0.34),
    "double_plays": (0.64, 0.82),
    # Batting rates
    "avg": (0.243, 0.269),
    "obp": (0.312, 0.337),
    "slg": (0.386, 0.435),
    "ops": (0.700, 0.768),
    # Pitching
    "balks": (0.02, 0.05),
    "wild_pitches": (0.29, 0.38),
    "whip": (1.27, 1.408),
    # Baserunning
    "stolen_bases": (0.46, 0.74),
    "caught_stealing": (0.15, 0.29),
    "pickoffs": (0.06, 0.09),
    "sb_pct": (0.682, 0.802),
    # Fielding
    "assists": (8.4, 10.4),
    "errors": (0.5, 0.7),
    "passed_balls": (0.05, 0.08),
    "fpct": (0.982, 0.986),
}


def _indicator(value: float, key: str) -> str:
    """Return ✓, ↑, or ↓ based on whether value is in expected range."""
    if key not in RANGES:
        return " "
    lo, hi = RANGES[key]
    if value < lo:
        return "↓"
    if value > hi:
        return "↑"
    return "✓"


def _range_str(key: str) -> str:
    if key not in RANGES:
        return ""
    lo, hi = RANGES[key]
    return f"[{lo}-{hi}]"


# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(
        description="League-wide stat totals for a season."
    )
    parser.add_argument(
        "--file", "-f", default="league.db", help="Set the league db filename."
    )
    parser.add_argument("--id", "-i", help="Season ID (or partial name/year match)")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def fetch_totals(conn, season_id: str) -> dict:
    cur = conn.cursor()

    cur.execute(
        """
        SELECT COUNT(*) as games
        FROM games
        WHERE season_id = ? AND completed = 1
        """,
        (season_id,),
    )
    games = cur.fetchone()["games"] or 1

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
            SUM(pgs.pitch_walks)                                        as p_walks,
            SUM(pgs.pitch_hits)                                         as p_hits,
            SUM(pgs.pitch_outs)                                         as p_outs,
            SUM(pgs.pitch_balks)                                        as balks,
            SUM(pgs.pitch_wild_pitches)                                 as wild_pitches,
            SUM(pgs.pitch_pickoffs)                                     as pickoffs,
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

    sb = row["stolen_bases"] or 0
    cs = row["caught_stealing"] or 0
    sba = sb + cs

    return {
        "games": games,
        "hits": hits,
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
        "avg": avg,
        "obp": obp,
        "slg": slg,
        "ops": ops,
        "balks": row["balks"] or 0,
        "wild_pitches": row["wild_pitches"] or 0,
        "whip": whip,
        "stolen_bases": sb,
        "caught_stealing": cs,
        "pickoffs": row["pickoffs"] or 0,
        "sb_pct": sb / sba if sba else 0,
        "stolen_base_attempts": sba,
        "putouts": row["putouts"] or 0,
        "assists": row["assists"] or 0,
        "errors": row["errors"] or 0,
        "passed_balls": row["passed_balls"] or 0,
    }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _count_row(label: str, total: int, pgm: float, key: str) -> str:
    ind = _indicator(pgm, key)
    rng = _range_str(key)
    return f"  {label:<22}  {total:>8,}  {pgm:>6.2f}/g  {ind}  {rng}"


def _rate_row(label: str, value: float, key: str, fmt: str = ".3f") -> str:
    ind = _indicator(value, key)
    rng = _range_str(key)
    return f"  {label:<22}  {value:{fmt}}{'':>14}  {ind}  {rng}"


def _header(section: str, show_pgm: bool = True) -> str:
    pgm_col = "Per T/G" if show_pgm else ""
    return (
        f"\n{section:<24}  {'Total':>8}  {pgm_col:>7}   {'':1}  Expected\n"
        + "-" * WIDTH
    )


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def display(totals: dict, season_label: str):
    g = totals["games"]
    tpg = g * 2  # two teams per game → per-team-per-game divisor

    print()
    print("=" * WIDTH)
    print(f"  LEAGUE TOTALS — {season_label}")
    print(f"  {g} games played")
    print("=" * WIDTH)

    # --- Batting counting ---
    print(_header("BATTING"))
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
        v = totals[key]
        print(_count_row(label, v, v / tpg, key))

    # --- Batting rates ---
    print(f"\n{'BATTING RATES':<24}  {'Value':>8}{'':>11}   {'':1}  Expected")
    print("-" * WIDTH)
    for label, key in [("AVG", "avg"), ("OBP", "obp"), ("SLG", "slg"), ("OPS", "ops")]:
        print(_rate_row(label, totals[key], key))

    # --- Pitching ---
    print(_header("PITCHING"))
    for label, key in [("Balks", "balks"), ("Wild Pitches", "wild_pitches")]:
        v = totals[key]
        print(_count_row(label, v, v / tpg, key))
    print(_rate_row("WHIP", totals["whip"], "whip"))

    # --- Baserunning ---
    print(_header("BASERUNNING"))
    for label, key in [
        ("Stolen Bases", "stolen_bases"),
        ("Caught Stealing", "caught_stealing"),
        ("Pickoffs", "pickoffs"),
    ]:
        v = totals[key]
        print(_count_row(label, v, v / tpg, key))

    sb = totals["stolen_bases"]
    sba = totals["stolen_base_attempts"]
    sbp = totals["sb_pct"]
    ind = _indicator(sbp, "sb_pct")
    lo, hi = RANGES["sb_pct"]
    print(
        f"  {'SB%':<22}  {sbp:>8.3f}{'':>10}  {ind}  [{lo:.3f}–{hi:.3f}]  ({sb}/{sba})"
    )

    # --- Fielding ---
    print(_header("FIELDING"))
    v = totals["putouts"]
    print(f"  {'Putouts':<22}  {v:>8,}  {v / tpg:>6.2f}/g")
    for label, key in [
        ("Assists", "assists"),
        ("Errors", "errors"),
        ("Passed Balls", "passed_balls"),
    ]:
        v = totals[key]
        print(_count_row(label, v, v / tpg, key))

    tc = totals["putouts"] + totals["assists"] + totals["errors"]
    fpct = (totals["putouts"] + totals["assists"]) / tc if tc else 0
    ind = _indicator(fpct, "fpct")
    rng = _range_str("fpct")
    print(f"  {'Fielding %':<22}  {fpct:.4f}{'':>12}  {ind}  {rng}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    args = parse_args()
    db_path, season_id, season_label = resolve_season(args.file, args.id)

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        raise SystemExit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    totals = fetch_totals(conn, season_id)
    conn.close()

    display(totals, season_label)


if __name__ == "__main__":
    main()
