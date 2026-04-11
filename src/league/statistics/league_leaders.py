# scripts/league_leaders.py
"""
Display the stat leaders for various stats for a season, compare with expected
real-world ranges.

"""

import argparse
import logging

from src.league.season_resolver import resolve_season
from src.league.statistics.view_leaderboards import calculate_min_pa
from src.stats.analyzer import StatsAnalyzer
from src.stats.loader import StatsLoader

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def log_print(msg: str = "", logger: logging.Logger = None):
    print(msg)
    if logger:
        logger.info(msg)


# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(
        description="League-wide stat leaders for a season."
    )
    parser.add_argument("--id", "-i", help="Season ID (or partial name/year match)")
    parser.add_argument("--logs", action="store_true", help="Write output to log file.")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WIDTH = 72
TOP_N = 9  # compare 10th leader

# Higher-is-better: (lo, hi) with lo < hi
# Lower-is-better:  (lo, hi) with lo > hi  — lo = expected 10th, hi = expected leader
RANGES = {
    "home_runs": (25, 70),
    "triples": (5, 23),
    "doubles": (36, 60),
    "singles": (100, 150),
    "hits": (172, 260),
    "rbi": (100, 150),
    "sac_flys": (8, 14),
    "sac_bunts": (6, 15),
    "sb": (25, 73),
    "cs": (7, 14),
    "walks": (85, 140),
    "strikeouts": (150, 225),
    "k_per_ab": (0.090, 0.15),
    "ab_per_k": (10, 15),
    "avg": (0.289, 0.350),
    "obp": (0.360, 0.420),
    "slg": (0.480, 0.700),
    "ops": (0.840, 1.200),
    "runs": (100, 150),
    "hbp": (10, 20),
    "double_plays": (20, 40),
    "ip": (180, 230),
    "starts": (30, 35),
    "wins": (12, 22),
    "losses": (12, 22),
    "saves": (25, 50),
    "save_opps": (30, 100),
    "sv_per_svo": (0.80, 0.99),
    "p_walks": (70, 90),
    "p_strikeouts": (180, 220),
    "k_per_9": (9, 11),
    "balks": (2, 10),
    "wild_pitches": (5, 22),
    # Lower-is-better: lo > hi
    "era": (3.2, 1.8),
    "whip": (1.1, 0.9),
    "bb_per_9": (3.0, 1.5),
    # Fielding
    "putouts": (1, 2),
    "assists": (8.4, 10.4),
    "errors": (0.7, 0.5),  # lower is better
    "passed_balls": (0.08, 0.05),  # lower is better
    "fpct": (0.982, 0.986),
}


def fetch_leaders(players, min_pa=0, min_ip=0) -> dict:
    analyzer = StatsAnalyzer(players)
    d = {}

    # Batting counting
    for attr, key in [
        ("leaderboard_home_runs", "home_runs"),
        ("leaderboard_triples", "triples"),
        ("leaderboard_doubles", "doubles"),
        ("leaderboard_singles", "singles"),
        ("leaderboard_hits", "hits"),
        ("leaderboard_rbi", "rbi"),
        ("leaderboard_sac_flys", "sac_flys"),
        ("leaderboard_sac_bunts", "sac_bunts"),
        ("leaderboard_stolen_bases", "sb"),
        ("leaderboard_caught_stealing", "cs"),
        ("leaderboard_walks", "walks"),
        ("leaderboard_batting_strikeouts", "strikeouts"),
        ("leaderboard_runs", "runs"),
        ("leaderboard_hbp", "hbp"),
        ("leaderboard_double_plays", "double_plays"),
    ]:
        rows = getattr(analyzer, attr)()
        d[key] = (rows[TOP_N][key], rows[0][key])

    # Batting rates (need min_pa qualifier)
    k_per_ab = analyzer.leaderboard_batting_strikeouts_per_ab(min_at_bats=min_pa)
    d["k_per_ab"] = (k_per_ab[TOP_N]["k_per_ab"], k_per_ab[0]["k_per_ab"])

    ab_per_k = analyzer.leaderboard_batting_at_bats_per_k(min_at_bats=min_pa)
    d["ab_per_k"] = (ab_per_k[TOP_N]["ab_per_k"], ab_per_k[0]["ab_per_k"])

    avg = analyzer.leaderboard_batting_average(min_at_bats=min_pa)
    d["avg"] = (avg[TOP_N]["avg"], avg[0]["avg"])

    obp = analyzer.leaderboard_on_base_percentage(min_plate_appearances=min_pa)
    d["obp"] = (obp[TOP_N]["obp"], obp[0]["obp"])

    slg = analyzer.leaderboard_slugging_percentage(min_at_bats=min_pa)
    d["slg"] = (slg[TOP_N]["slg"], slg[0]["slg"])

    ops = analyzer.leaderboard_ops(min_at_bats=min_pa)
    d["ops"] = (ops[TOP_N]["ops"], ops[0]["ops"])

    # Pitching counting
    ip = analyzer.leaderboard_innings_pitched()
    d["ip"] = (ip[TOP_N]["innings_pitched"], ip[0]["innings_pitched"])

    # starts = analyzer.leaderboard_game_starts()
    # d["starts"] = (starts[TOP_N]["starts"], starts[0]["starts"])

    wins = analyzer.leaderboard_wins()
    d["wins"] = (wins[TOP_N]["wins"], wins[0]["wins"])

    losses = analyzer.leaderboard_losses()
    d["losses"] = (losses[TOP_N]["losses"], losses[0]["losses"])

    saves = analyzer.leaderboard_saves()
    d["saves"] = (saves[TOP_N]["saves"], saves[0]["saves"])

    # save_opps = analyzer.leaderboard_save_opportunities()
    # d["save_opps"] = (save_opps[TOP_N]["save_opps"], save_opps[0]["save_opps"])

    p_walks = analyzer.leaderboard_pitch_walks()
    d["p_walks"] = (p_walks[TOP_N]["walks"], p_walks[0]["walks"])

    p_strikeouts = analyzer.leaderboard_pitch_strikeouts()
    d["p_strikeouts"] = (
        p_strikeouts[TOP_N]["strike_outs"],
        p_strikeouts[0]["strike_outs"],
    )

    balks = analyzer.leaderboard_balks()
    d["balks"] = (balks[TOP_N]["balks"], balks[0]["balks"])

    wild_pitches = analyzer.leaderboard_wild_pitches()
    d["wild_pitches"] = (
        wild_pitches[TOP_N]["wild_pitches"],
        wild_pitches[0]["wild_pitches"],
    )

    # Pitching rates (lower is better; leaderboards sort ascending so index 0 = best/lowest)
    era = analyzer.leaderboard_era(min_innings=min_ip)
    d["era"] = (era[TOP_N]["era"], era[0]["era"])

    whip = analyzer.leaderboard_whip(min_innings=min_ip)
    d["whip"] = (whip[TOP_N]["whip"], whip[0]["whip"])

    # bb_per_9 = analyzer.leaderboard_bb_per_9(min_ip=min_ip)
    # d["bb_per_9"] = (bb_per_9[TOP_N]["bb_per_9"], bb_per_9[0]["bb_per_9"])

    # k_per_9 = analyzer.leaderboard_k_per_9(min_ip=min_ip)
    # d["k_per_9"] = (k_per_9[TOP_N]["k_per_9"], k_per_9[0]["k_per_9"])

    # sv_per_svo = analyzer.leaderboard_sv_per_svo()
    # d["sv_per_svo"] = (sv_per_svo[TOP_N]["sv_per_svo"], sv_per_svo[0]["sv_per_svo"])

    return d


def _indicators(tenth_val, leader_val, key: str) -> str:
    """
    Two-character indicator for (10th place, leader).
    Each character: ✓ in range, ↑ above range (bad for lower-is-better),
                    ↓ below range (bad for higher-is-better).

    Direction is encoded in RANGES:
      lo < hi  →  higher is better
      lo > hi  →  lower is better (e.g. ERA: 3.2 → 1.8)
    """
    if key not in RANGES:
        return "  "

    lo, hi = RANGES[key]

    if lo <= hi:
        # Higher is better. ↓ = too low, ↑ = too high.
        def sym(v):
            if v < lo:
                return "↓"
            if v > hi:
                return "↑"
            return "✓"

    else:
        # Lower is better. Valid range is [hi, lo].
        # ↑ = too high (bad), ↓ = unrealistically low.
        def sym(v):
            if v > lo:
                return "↑"
            if v < hi:
                return "↓"
            return "✓"

    return sym(tenth_val) + sym(leader_val)


def _range_str(key: str, fmt: str = ".3f") -> str:
    if key not in RANGES:
        return ""
    lo, hi = RANGES[key]
    # Always display as [better–worse] for clarity
    better, worse = (lo, hi) if lo <= hi else (hi, lo)
    return f"[{better:{fmt}} - {worse:{fmt}}]"


def _header(section: str) -> str:
    return (
        f"\n{section:<24}  {'10th':>8}  {'Leader':>6}  {'':2}  Expected\n" + "-" * WIDTH
    )


def _count_row(label: str, tenth, leader, key: str) -> str:
    ind = _indicators(tenth, leader, key)
    rng = _range_str(key, ".0f")
    return f"  {label:<22}  {tenth:>8,}  {leader:>6,}  {ind}  {rng}"


def _rate_row(label: str, tenth, leader, key: str, fmt: str = ".3f") -> str:
    ind = _indicators(tenth, leader, key)
    rng = _range_str(key, fmt)
    return f"  {label:<22}  {tenth:>8{fmt}}  {leader:>6{fmt}}  {ind}  {rng}"


def display(totals: dict, season_label: str, logger: logging.Logger = None):
    lines = []
    lines.append("")
    lines.append("=" * WIDTH)
    lines.append(f"  LEAGUE LEADER EVALUATION — {season_label}")
    lines.append("=" * WIDTH)

    lines.append(_header("BATTING"))
    for label, key in [
        ("Hits", "hits"),
        ("Runs", "runs"),
        ("Singles", "singles"),
        ("Doubles", "doubles"),
        ("Triples", "triples"),
        ("Home Runs", "home_runs"),
        ("RBI", "rbi"),
        ("Walks", "walks"),
        ("Strikeouts", "strikeouts"),
        ("HBP", "hbp"),
        ("Sac Flies", "sac_flys"),
        ("Sac Bunts", "sac_bunts"),
        ("Double Plays", "double_plays"),
    ]:
        tenth, leader = totals[key]
        lines.append(_count_row(label, tenth, leader, key))

    lines.append(_header("BATTING RATES"))
    for label, key, fmt in [
        ("AVG", "avg", ".3f"),
        ("OBP", "obp", ".3f"),
        ("SLG", "slg", ".3f"),
        ("OPS", "ops", ".3f"),
        ("AB/K", "ab_per_k", ".1f"),
        ("K/AB", "k_per_ab", ".3f"),
    ]:
        tenth, leader = totals[key]
        lines.append(_rate_row(label, tenth, leader, key, fmt))

    lines.append(_header("BASERUNNING"))
    for label, key in [
        ("Stolen Bases", "sb"),
        ("Caught Stealing", "cs"),
    ]:
        tenth, leader = totals[key]
        lines.append(_count_row(label, tenth, leader, key))

    lines.append(_header("PITCHING"))
    for label, key in [
        # ("Game Starts",     "starts"),
        ("Wins", "wins"),
        ("Losses", "losses"),
        ("Saves", "saves"),
        # ("Save Opps",       "save_opps"),
        ("Walks", "p_walks"),
        ("Strikeouts", "p_strikeouts"),
        ("Balks", "balks"),
        ("Wild Pitches", "wild_pitches"),
    ]:
        tenth, leader = totals[key]
        lines.append(_count_row(label, tenth, leader, key))

    lines.append(_header("PITCHING RATES"))
    for label, key, fmt in [
        ("Innings Pitched", "ip", ".0f"),
        ("ERA", "era", ".2f"),
        ("WHIP", "whip", ".3f"),
        # ("K/9",    "k_per_9",  ".2f"),
        # ("BB/9",   "bb_per_9", ".2f"),
        # ("SV/SVO", "sv_per_svo", ".3f"),
    ]:
        tenth, leader = totals[key]
        lines.append(_rate_row(label, tenth, leader, key, fmt))

    # Fielding stubbed — uncomment when fielding leaderboards are available
    # lines.append(_header("FIELDING"))
    # for label, key in [
    #     ("Putouts",      "putouts"),
    #     ("Assists",      "assists"),
    #     ("Errors",       "errors"),
    #     ("Passed Balls", "passed_balls"),
    # ]:
    #     tenth, leader = totals[key]
    #     lines.append(_count_row(label, tenth, leader, key))
    # tenth, leader = totals["fpct"]
    # lines.append(_rate_row("Fielding %", tenth, leader, "fpct", ".4f"))

    lines.append("")
    output = "\n".join(lines)
    print(output)
    if logger:
        logger.info(output)


def main():
    args = parse_args()
    season_id, season_label = resolve_season(args.id)

    logger = None
    if args.logs:
        from src.util.logger import setup_logger
        import logging

        logger = setup_logger(
            name="league_leaders",
            level=logging.INFO,
            console_level=logging.WARNING,
            log_id="league_leaders",
            log_to_file=True,
        )

    min_pa, min_ip = calculate_min_pa(season_id, logger=logger)

    with StatsLoader() as loader:
        all_players = loader.load_season_players_with_stats(season_id)

    # print(f"DEBUG: loaded {len(all_players)} players for season {season_id}")
    # if all_players:
    #     sample = all_players[0]
    #     print(f"DEBUG: sample player {sample.name}, AB={sample.game_stats.batting.at_bats}")

    totals = fetch_leaders(all_players, min_pa=min_pa, min_ip=min_ip)
    display(totals, season_label, logger=logger)


if __name__ == "__main__":
    main()
