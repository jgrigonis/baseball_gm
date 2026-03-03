# scripts/league_leaders.py
"""
Display the stat leaders for various stats for a season, compar with expected
real-world ranges.

Usage:
    python league_leaders.py --db leagues/league.db --id <season_id>
    python league_leaders.py --db leagues/league.db  # auto-selects if one season

Stat leader categories to compare to expected:
Batting:
- Home Runs
- Triples
- Doubles
- Singles
- Hits
- RBI
- Sac Flies
- Sac Bunts
- Stolen Bases
- Caught Stealing
(SB% already in league_totals)
- Walks (batting)
- Strikeouts (batting)
- lowest K/AB
or (depending on available data)
- highest AB/K
- batting averages
- OBP
- Slugging
- OPS
- Runs
- HBP
- Double Plays

Pitching:
- Innings Pitched
- Game Starts
- ERA
- Wins
- Losses
- Saves
- Save Opps
- SV / SVO
- WHIP
- K/9
- BB/9
- Balks
- Wild Pitches
- pickoffs

Fielding (By positions):
- Putouts
- Assists
- Errors
- Passed Balls
- FPCT
"""

import argparse
import sqlite3

from src.league.season_resolver import resolve_season
from src.league.view_leaderboards import calculate_min_pa
from src.stats.analyzer import StatsAnalyzer
from src.stats.loader import StatsLoader

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(
        description="League-wide stat leaders for a season."
    )
    parser.add_argument(
        "--file", "-f", default="league.db", help="Set the league db filename."
    )
    parser.add_argument("--id", "-i", help="Season ID (or partial name/year match)")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Expected ranges (per season for leaders)
# ---------------------------------------------------------------------------

WIDTH = 72
TOP_N = 9  # compare 10th leader

RANGES = {
    # Batting counting
    "home_runs": (25, 70),
    "triples": (7, 15),
    "doubles": (20, 50),
    "singles": (5.1, 6.2),
    "hits": (110, 300),
    "rbi": (3.86, 4.63),
    "sac_flys": (0.22, 0.31),
    "sac_bunts": (0.1, 0.34),
    "sb": (0.46, 0.74),
    "cs": (0.15, 0.29),
    "walks": (2.88, 3.42),
    "strikeouts": (6.3, 8.8),
    "k_per_ab": (1, 2),
    "ab_per_k": (1, 2),
    "avg": (0.243, 0.269),
    "obp": (0.312, 0.337),
    "slg": (0.386, 0.435),
    "ops": (0.700, 0.768),
    "runs": (4.0, 4.9),
    "hbp": (0.3, 0.4),
    "double_plays": (0.64, 0.82),
    "woba": (1, 2),
    "wrc": (1, 2),
    # Pitching
    "ip": (1, 2),
    "starts": (1, 2),
    "era": (1, 2),
    "wins": (1, 2),
    "losses": (1, 2),
    "saves": (1, 2),
    "save_opps": (1, 2),
    "sv_per_svo": (1, 2),
    "whip": (1.27, 1.408),
    "k_per_9": (1, 2),
    "bb_per_9": (1, 2),
    "balks": (0.02, 0.05),
    "wild_pitches": (0.29, 0.38),
    "pickoffs": (0.06, 0.09),
    # Fielding
    "putouts": (1, 2),
    "assists": (8.4, 10.4),
    "errors": (0.5, 0.7),
    "passed_balls": (0.05, 0.08),
    "fpct": (0.982, 0.986),
}

# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def fetch_leaders(players, min_pa=0, min_ip=0) -> dict:
    """
    Fetch a dictionary of leaders, it should look something like this:

    {
        "home_runs": (38, 50),
    }
    where 38 is the 10th best home run hitter's total for the season
    and 50 is the league leader's total

    """

    analyzer = StatsAnalyzer(players)
    return_dict = {}

    hr = analyzer.leaderboard_home_runs()
    return_dict["home_runs"] = (
        hr[TOP_N]["home_runs"],
        hr[0]["home_runs"],
    )
    triples = analyzer.leaderboard_triples()
    return_dict["triples"] = (
        triples[TOP_N]["triples"],
        triples[0]["triples"],
    )
    doubles = analyzer.leaderboard_doubles()
    return_dict["doubles"] = (
        doubles[TOP_N]["doubles"],
        doubles[0]["doubles"],
    )
    singles = analyzer.leaderboard_singles()
    return_dict["singles"] = (
        singles[TOP_N]["singles"],
        singles[0]["singles"],
    )
    hits = analyzer.leaderboard_hits()
    return_dict["hits"] = (
        hits[TOP_N]["hits"],
        hits[0]["hits"],
    )
    sacf = analyzer.leaderboard_sac_flys()
    return_dict["sac_flys"] = (
        sacf[TOP_N]["sac_flys"],
        sacf[0]["sac_flys"],
    )
    sacb = analyzer.leaderboard_sac_bunts()
    return_dict["sac_bunts"] = (
        sacb[TOP_N]["sac_bunts"],
        sacb[0]["sac_bunts"],
    )
    sb = analyzer.leaderboard_stolen_bases()
    return_dict["sb"] = (
        sb[TOP_N]["sb"],
        sb[0]["sb"],
    )
    cs = analyzer.leaderboard_caught_stealing()
    return_dict["cs"] = (
        cs[TOP_N]["cs"],
        cs[0]["cs"],
    )
    bb = analyzer.leaderboard_walks()
    return_dict["walks"] = (
        bb[TOP_N]["walks"],
        bb[0]["walks"],
    )
    ks = analyzer.leaderboard_batting_strikeouts()
    return_dict["strikeouts"] = (
        ks[TOP_N]["strikeouts"],
        ks[0]["strikeouts"],
    )
    k_per_ab = analyzer.leaderboard_batting_strikeouts_per_ab(min_at_bats=min_pa)
    return_dict["k_per_ab"] = (
        k_per_ab[TOP_N]["k_per_ab"],
        k_per_ab[0]["k_per_ab"],
    )
    ab_per_k = analyzer.leaderboard_batting_at_bats_per_k(min_at_bats=min_pa)
    return_dict["ab_per_k"] = (
        ab_per_k[TOP_N]["ab_per_k"],
        ab_per_k[0]["ab_per_k"],
    )
    avg = analyzer.leaderboard_batting_average(min_at_bats=min_pa)
    return_dict["avg"] = (
        avg[TOP_N]["avg"],
        avg[0]["avg"],
    )
    obp = analyzer.leaderboard_on_base_percentage(min_plate_appearances=min_pa)
    return_dict["obp"] = (
        obp[TOP_N]["obp"],
        obp[0]["obp"],
    )
    slg = analyzer.leaderboard_slugging_percentage(min_at_bats=min_pa)
    return_dict["slg"] = (
        slg[TOP_N]["slg"],
        slg[0]["slg"],
    )
    ops = analyzer.leaderboard_ops(min_at_bats=min_pa)
    return_dict["ops"] = (
        ops[TOP_N]["ops"],
        ops[0]["ops"],
    )
    runs = analyzer.leaderboard_runs()
    return_dict["runs"] = (
        runs[TOP_N]["runs"],
        runs[0]["runs"],
    )
    hbp = analyzer.leaderboard_hbp()
    return_dict["hbp"] = (
        hbp[TOP_N]["hbp"],
        hbp[0]["hbp"],
    )
    double_plays = analyzer.leaderboard_double_plays()
    return_dict["double_plays"] = (
        double_plays[TOP_N]["double_plays"],
        double_plays[0]["double_plays"],
    )
    # Pitching leaders
    ip = analyzer.leaderboard_innings_pitched()
    return_dict["ip"] = (
        ip[TOP_N]["innings_pitched"],
        ip[0]["innings_pitched"],
    )
    # starts = analyzer.leaderboard_game_starts()
    # return_dict["starts"] = (
    #     starts[TOP_N]["starts"],
    #     starts[0]["starts"],
    # )
    era = analyzer.leaderboard_era()
    return_dict["era"] = (
        era[TOP_N]["era"],
        era[0]["era"],
    )
    wins = analyzer.leaderboard_wins()
    return_dict["wins"] = (
        wins[TOP_N]["wins"],
        wins[0]["wins"],
    )
    losses = analyzer.leaderboard_losses()
    return_dict["losses"] = (
        losses[TOP_N]["losses"],
        losses[0]["losses"],
    )
    saves = analyzer.leaderboard_saves()
    return_dict["saves"] = (
        saves[TOP_N]["saves"],
        saves[0]["saves"],
    )
    # save_opps = analyzer.leaderboard_save_opportunities()
    # return_dict["save_opps"] = (
    #     save_opps[TOP_N]["save_opps"],
    #     save_opps[0]["save_opps"],
    # )

    print(return_dict)

    return return_dict


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _count_row(label: str, min: int, max: int, key: str) -> str:
    ind = _indicators(min, max, key)
    rng = _range_str(key)
    return f"  {label:<22}  {min:>8,}  {max:>6}  {ind}  {rng}"


# def _rate_row(label: str, value: float, key: str, fmt: str = ".3f") -> str:
#     ind = _indicator(value, key)
#     rng = _range_str(key)
#     return f"  {label:<22}  {value:{fmt}}{'':>14}  {ind}  {rng}"


def _header(section: str) -> str:
    return (
        f"\n{section:<24}  {'10th':>8}   {'Leader':>1}  Expected\n"
        + "-" * WIDTH
    )


def _indicators(min, max, key: str) -> str:
    """
    Return a pair of ✓, ↑, or ↓ based on whether values are in expected range.

    If the high is in the range and the low is in the range: ✓✓
    If the high is lower than the bottom: ↓↓
    If the low is higher than the bottom: ↑↑
    If the high is higher than the top and the low is higher than the bottom: ↑✓
    If the low is lower than the bottom and the high is lower than the top: ↓✓
    If the high is higher than the top and the low is lower than the bottom: ↓↑

    """
    if key not in RANGES:
        return " "
    lo, hi = RANGES[key]

    if max < lo:
        return "↓↓"
    if min > hi:
        return "↑↑"
    if max > hi and min > lo:
        return "↑✓"
    if min < lo and max < hi:
        return "↓✓"
    if max > hi and min < lo:
        return "↓↑"
    return "✓✓"


def _range_str(key: str) -> str:
    if key not in RANGES:
        return ""
    lo, hi = RANGES[key]
    return f"[{lo}-{hi}]"


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def display(totals: dict, season_label: str):
    # g = totals["games"]
    # tpg = g * 2  # two teams per game → per-team-per-game divisor

    print()
    print("=" * WIDTH)
    print(f"  LEAGUE LEADER EVALUATION — {season_label}")
    # print(f"  {g} games played")
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
        #("RBI", "rbi"),
        ("HBP", "hbp"),
        ("Sac Flys", "sac_flys"),
        ("Sac Bunts", "sac_bunts"),
        ("Double Plays", "double_plays"),
    ]:
        # v = totals[key]
        min = totals[key][0]
        max = totals[key][1]
        print(_count_row(label, min, max, key))
    return
    # # --- Batting rates ---
    # print(f"\n{'BATTING RATES':<24}  {'Value':>8}{'':>11}   {'':1}  Expected")
    # print("-" * WIDTH)
    # for label, key in [("AVG", "avg"), ("OBP", "obp"), ("SLG", "slg"), ("OPS", "ops")]:
    #     print(_rate_row(label, totals[key], key))

    # # --- Pitching ---
    # print(_header("PITCHING"))
    # for label, key in [("Balks", "balks"), ("Wild Pitches", "wild_pitches")]:
    #     v = totals[key]
    #     print(_count_row(label, v, v / tpg, key))
    # print(_rate_row("WHIP", totals["whip"], "whip"))

    # # --- Baserunning ---
    # print(_header("BASERUNNING"))
    # for label, key in [
    #     ("Stolen Bases", "stolen_bases"),
    #     ("Caught Stealing", "caught_stealing"),
    #     ("Pickoffs", "pickoffs"),
    # ]:
    #     v = totals[key]
    #     print(_count_row(label, v, v / tpg, key))

    # sb = totals["stolen_bases"]
    # sba = totals["stolen_base_attempts"]
    # sbp = totals["sb_pct"]
    # ind = _indicator(sbp, "sb_pct")
    # lo, hi = RANGES["sb_pct"]
    # print(
    #     f"  {'SB%':<22}  {sbp:>8.3f}{'':>10}  {ind}  [{lo:.3f}–{hi:.3f}]  ({sb}/{sba})"
    # )

    # # --- Fielding ---
    # print(_header("FIELDING"))
    # v = totals["putouts"]
    # print(f"  {'Putouts':<22}  {v:>8,}  {v / tpg:>6.2f}/g")
    # for label, key in [
    #     ("Assists", "assists"),
    #     ("Errors", "errors"),
    #     ("Passed Balls", "passed_balls"),
    # ]:
    #     v = totals[key]
    #     print(_count_row(label, v, v / tpg, key))

    # tc = totals["putouts"] + totals["assists"] + totals["errors"]
    # fpct = (totals["putouts"] + totals["assists"]) / tc if tc else 0
    # ind = _indicator(fpct, "fpct")
    # rng = _range_str("fpct")
    # print(f"  {'Fielding %':<22}  {fpct:.4f}{'':>12}  {ind}  {rng}")

    # print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    args = parse_args()
    db_path, season_id, season_label = resolve_season(args.file, args.id)

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        raise SystemExit(1)

    min_pa, min_ip = calculate_min_pa(db_path, season_id)

    with StatsLoader(str(db_path)) as loader:
        all_players = loader.load_season_players_with_stats(season_id)

    totals = fetch_leaders(all_players, min_pa=min_pa, min_ip=min_ip)

    display(totals, season_label)


if __name__ == "__main__":
    main()
