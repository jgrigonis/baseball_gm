# src/league/performance.py
"""
How a player's season stats compare to his ratings, in rating points: the
"stats" side of the stats-vs-scouting dial (plans/ai-gm-strategy.md,
section 6). A GM who gives stats a weight s sees a player as

    rating + s × form

where form is what his stats say his rating is, minus his rating, regressed
toward 0 by how much he's played. So a 40 at-bat hot streak barely moves
anyone, and a full season counts about half.

Hitters are judged by wOBA, pitchers by FIP (without the league constant).
Each is compared with what a player of his rating is expected to put up,
measured from the sim (thousands of simulated games):

    wOBA            = 0.0830 + 0.00349 × overall_offense
    FIP, starters   = 2.503 - 0.0249 × sp rating
    FIP, relievers  = 4.486 - 0.0602 × rp rating

Ratings and stats are both public, so this never uses hidden talent caps.
"""

from __future__ import annotations

from src.player.player_evaluator import PlayerEvaluator

WOBA_BASE = 0.0830
WOBA_PER_POINT = 0.00349
# (base, per point) of FIP, for starters and relievers.
FIP_STARTER = (2.503, -0.0249)
FIP_RELIEVER = (4.486, -0.0602)

# Regression: form counts n / (n + REGRESS) of what the stats say.
REGRESS_PA = 300
REGRESS_OUTS = 300  # 100 innings
# No player's form moves him more than this many points either way.
MAX_FORM = 15.0


def _regress(points: float, n: int, k: int) -> float:
    points *= n / (n + k)
    return max(-MAX_FORM, min(MAX_FORM, points))


def woba(t: dict) -> tuple[float, int]:
    """(wOBA, plate appearances) from season totals."""
    pa = t["bat_ab"] + t["bat_walks"] + t["bat_sac_flys"] + t["bat_hbp"]
    if not pa:
        return 0.0, 0
    singles = t["bat_hits"] - t["bat_doubles"] - t["bat_triples"] - t["bat_home_runs"]
    num = (
        0.69 * t["bat_walks"]
        + 0.72 * t["bat_hbp"]
        + 0.89 * singles
        + 1.27 * t["bat_doubles"]
        + 1.62 * t["bat_triples"]
        + 2.10 * t["bat_home_runs"]
    )
    return num / pa, pa


def fip(t: dict) -> tuple[float, int]:
    """(FIP without the league constant, outs) from season totals."""
    outs = t["pitch_outs"]
    if not outs:
        return 0.0, 0
    raw = (
        13 * t["pitch_home_runs"]
        + 3 * (t["pitch_walks"] + t["pitch_hit_batters"])
        - 2 * t["pitch_strike_outs"]
    )
    return raw / (outs / 3), outs


def hitter_form(offense: float, t: dict) -> float:
    """Rating points a hitter's wOBA puts him above (or below) his
    overall_offense, regressed."""
    actual, pa = woba(t)
    if not pa:
        return 0.0
    expected = WOBA_BASE + WOBA_PER_POINT * offense
    return _regress((actual - expected) / WOBA_PER_POINT, pa, REGRESS_PA)


def pitcher_form(sp: float, rp: float, t: dict) -> float:
    """Rating points a pitcher's FIP puts him above (or below) his rating as
    a starter or a reliever, whichever he's mostly been, regressed."""
    actual, outs = fip(t)
    if not outs:
        return 0.0
    starter = t["pitch_games_started"] * 2 >= max(1, t["pitch_games_played"])
    base, per_point = FIP_STARTER if starter else FIP_RELIEVER
    expected = base + per_point * (sp if starter else rp)
    return _regress((actual - expected) / per_point, outs, REGRESS_OUTS)


def form(ratings: dict, t: dict | None) -> tuple[float, float]:
    """(as a hitter, as a pitcher) form from a player's ratings
    (PlayerEvaluator.rate_player) and season totals."""
    if not t:
        return 0.0, 0.0
    return (
        hitter_form(ratings["overall_offense"], t),
        pitcher_form(ratings["sp"], ratings["rp"], t),
    )


def form_by_player(records, totals: dict[str, dict]) -> dict[str, tuple[float, float]]:
    """Form for each of these PlayerRecords that has played this season."""
    out = {}
    for p in records:
        t = totals.get(p.id)
        if t:
            out[p.id] = form(PlayerEvaluator.rate_player(p.skills, p.throws), t)
    return out
