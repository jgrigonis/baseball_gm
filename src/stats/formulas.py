# src/stats/formulas.py
"""
Standard baseball rate stats, computed from raw counting stats.

Every function returns 0.0 when its denominator is zero, so callers that
want a different placeholder ("—", None) check the denominator themselves.
Rounding and formatting are left to the caller.
"""

OUTS_PER_INNING = 3


def total_bases(hits: int, doubles: int, triples: int, home_runs: int) -> int:
    """Singles count once, doubles twice, triples three times, homers four."""
    return hits + doubles + 2 * triples + 3 * home_runs


def batting_average(hits: int, at_bats: int) -> float:
    return hits / at_bats if at_bats else 0.0


def on_base_pct(
    hits: int, walks: int, hit_by_pitch: int, at_bats: int, sac_flies: int
) -> float:
    denom = at_bats + walks + hit_by_pitch + sac_flies
    return (hits + walks + hit_by_pitch) / denom if denom else 0.0


def slugging_pct(total_bases: int, at_bats: int) -> float:
    return total_bases / at_bats if at_bats else 0.0


def innings(outs: int) -> float:
    """Innings pitched as a true number (7 outs -> 2.333...)."""
    return outs / OUTS_PER_INNING


def ip_str(outs: int) -> str:
    """Innings pitched in box score notation (7 outs -> "2.1")."""
    return f"{outs // OUTS_PER_INNING}.{outs % OUTS_PER_INNING}"


def per_nine(count: int, outs: int) -> float:
    """A count scaled to nine innings, e.g. K/9 or BB/9."""
    return count * 9 * OUTS_PER_INNING / outs if outs else 0.0


def era(earned_runs: int, outs: int) -> float:
    return per_nine(earned_runs, outs)


def whip(hits: int, walks: int, outs: int) -> float:
    return (hits + walks) / innings(outs) if outs else 0.0
