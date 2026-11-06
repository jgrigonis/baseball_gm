# src/stats/advanced.py
"""
Advanced rate stats from season totals (player_season_stats rows, or any
dict with the same bat_* / pitch_* keys).

  wOBA   weighted on-base average: each way of reaching base by its run
         value, per plate appearance (fixed weights, FanGraphs-style)
  wRC+   runs created per plate appearance against the league, 100 = average
  OPS+   OBP and SLG against the league's, 100 = average
  ISO    isolated power, SLG - AVG
  BABIP  batting average on balls in play
  K%/BB% strikeouts and walks per plate appearance (for a pitcher, per
         batter faced, counted as outs + hits + walks + hit batters)
  FIP    fielding-independent pitching: HR, BB, HBP and K per inning,
         scaled so the league's FIP equals its ERA
  ERA+   league ERA over his ERA, 100 = average

There are no ballparks, so nothing is park-adjusted. The "+" stats and
FIP's constant always use the league's regular season, even for
postseason lines.
"""

from __future__ import annotations

from dataclasses import dataclass

WOBA_WEIGHTS = {
    "bb": 0.69,
    "hbp": 0.72,
    "1b": 0.89,
    "2b": 1.27,
    "3b": 1.62,
    "hr": 2.10,
}
WOBA_SCALE = 1.2


def _n(c: dict, k: str) -> int:
    return int(c.get(k) or 0)


# ── Hitting ──────────────────────────────────────────────────────────────────


def pa(c: dict) -> int:
    """Plate appearances that count for OBP and wOBA (no sac bunts)."""
    return (
        _n(c, "bat_ab") + _n(c, "bat_walks") + _n(c, "bat_hbp") + _n(c, "bat_sac_flys")
    )


def singles(c: dict) -> int:
    return (
        _n(c, "bat_hits")
        - _n(c, "bat_doubles")
        - _n(c, "bat_triples")
        - _n(c, "bat_home_runs")
    )


def woba(c: dict) -> float:
    n = pa(c)
    if not n:
        return 0.0
    w = WOBA_WEIGHTS
    num = (
        w["bb"] * _n(c, "bat_walks")
        + w["hbp"] * _n(c, "bat_hbp")
        + w["1b"] * singles(c)
        + w["2b"] * _n(c, "bat_doubles")
        + w["3b"] * _n(c, "bat_triples")
        + w["hr"] * _n(c, "bat_home_runs")
    )
    return num / n


def _obp(c: dict) -> float:
    n = pa(c)
    return (_n(c, "bat_hits") + _n(c, "bat_walks") + _n(c, "bat_hbp")) / n if n else 0.0


def _slg(c: dict) -> float:
    ab = _n(c, "bat_ab")
    if not ab:
        return 0.0
    tb = (
        _n(c, "bat_hits")
        + _n(c, "bat_doubles")
        + 2 * _n(c, "bat_triples")
        + 3 * _n(c, "bat_home_runs")
    )
    return tb / ab


def _avg(c: dict) -> float:
    ab = _n(c, "bat_ab")
    return _n(c, "bat_hits") / ab if ab else 0.0


def babip(c: dict) -> float | None:
    hr = _n(c, "bat_home_runs")
    denom = _n(c, "bat_ab") - _n(c, "bat_strike_outs") - hr + _n(c, "bat_sac_flys")
    return (_n(c, "bat_hits") - hr) / denom if denom > 0 else None


# ── Pitching ─────────────────────────────────────────────────────────────────


def fip_raw(c: dict) -> float:
    """FIP before the league constant is added."""
    outs = _n(c, "pitch_outs")
    if not outs:
        return 0.0
    raw = (
        13 * _n(c, "pitch_home_runs")
        + 3 * (_n(c, "pitch_walks") + _n(c, "pitch_hit_batters"))
        - 2 * _n(c, "pitch_strike_outs")
    )
    return raw / (outs / 3)


def era(c: dict) -> float:
    outs = _n(c, "pitch_outs")
    return 27 * _n(c, "pitch_earned_runs") / outs if outs else 0.0


def batters_faced(c: dict) -> int:
    """Close to batters faced: everyone who made an out, got a hit, walked
    or was hit. Errors and fielder's choices aren't counted apart, so it
    runs a touch low."""
    return (
        _n(c, "pitch_outs")
        + _n(c, "pitch_hits")
        + _n(c, "pitch_walks")
        + _n(c, "pitch_hit_batters")
    )


# ── League ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LeagueRates:
    """The league's regular season rates the "+" stats are measured against."""

    woba: float
    obp: float
    slg: float
    runs_per_pa: float
    era: float
    fip_const: float

    @classmethod
    def of(cls, totals: dict) -> LeagueRates | None:
        """From the league's summed bat_* and pitch_* totals (one dict).
        None when the season has no games yet."""
        if not pa(totals) or not _n(totals, "bat_ab"):
            return None
        lg_era = era(totals) if _n(totals, "pitch_outs") else 4.5
        return cls(
            woba=woba(totals),
            obp=_obp(totals),
            slg=_slg(totals),
            runs_per_pa=_n(totals, "bat_runs") / pa(totals),
            era=lg_era,
            fip_const=lg_era - fip_raw(totals),
        )


def win_values(c: dict, side: str) -> dict:
    """WPA and RE24 for "bat" or "pitch". Both None for games from before
    they were tracked (exactly zero; a real line is never exactly 0)."""
    wpa, re24 = c.get(f"{side}_wpa") or 0.0, c.get(f"{side}_re24") or 0.0
    if not wpa and not re24:
        return {"WPA": None, "RE24": None}
    return {"WPA": round(float(wpa), 2), "RE24": round(float(re24), 1)}


def batting(c: dict, lg: LeagueRates | None) -> dict:
    """The advanced hitting line: wOBA, wRC+, OPS+, ISO, BABIP, K%, BB%.
    The league-relative ones are None without league rates."""
    n = pa(c)
    w = woba(c)
    out = {
        "wOBA": round(w, 3) if n else None,
        "ISO": round(_slg(c) - _avg(c), 3) if _n(c, "bat_ab") else None,
        "BABIP": round(babip(c), 3) if babip(c) is not None else None,
        "K_PCT": round(100 * _n(c, "bat_strike_outs") / n, 1) if n else None,
        "BB_PCT": round(100 * _n(c, "bat_walks") / n, 1) if n else None,
        "wRC_PLUS": None,
        "OPS_PLUS": None,
    }
    if lg and n:
        if lg.runs_per_pa > 0:
            wraa_pa = (w - lg.woba) / WOBA_SCALE
            out["wRC_PLUS"] = round(100 * (wraa_pa + lg.runs_per_pa) / lg.runs_per_pa)
        if lg.obp > 0 and lg.slg > 0:
            out["OPS_PLUS"] = round(100 * (_obp(c) / lg.obp + _slg(c) / lg.slg - 1))
    return out


def pitching(c: dict, lg: LeagueRates | None) -> dict:
    """The advanced pitching line: FIP, ERA+, K%, BB%. FIP and ERA+ are
    None without league rates; ERA+ is None at a 0.00 ERA."""
    bf = batters_faced(c)
    outs = _n(c, "pitch_outs")
    out = {
        "FIP": None,
        "ERA_PLUS": None,
        "K_PCT": round(100 * _n(c, "pitch_strike_outs") / bf, 1) if bf else None,
        "BB_PCT": round(100 * _n(c, "pitch_walks") / bf, 1) if bf else None,
    }
    if lg and outs:
        out["FIP"] = round(fip_raw(c) + lg.fip_const, 2)
        e = era(c)
        out["ERA_PLUS"] = round(100 * lg.era / e) if e > 0 else None
    return out
