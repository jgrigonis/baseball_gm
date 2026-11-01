# src/league/awards.py
"""
Season awards. The pure part: who wins each award, from the season's stat
lines. src/api/services/awards.py runs it against the database.

Most awards go to one player in each of the two leagues (Atlantic and
Pacific), the way the majors give one in each league; a league without
divisions gives one for everyone. The Edgar Martinez Award (the best DH)
is given once, league-wide: there are rarely enough full-time DHs to give
two.

The "voters" go by value, a simple wins-above-replacement:

  hitters   batting runs above average (wOBA), base stealing, a position
            adjustment (a catcher's or shortstop's bat is worth more than a
            DH's), and replacement level by plate appearances
  pitchers  runs saved against a replacement pitcher, half by FIP and half
            by ERA, by innings pitched

MVP           most value; pitchers count for a little less, and a player on
              a winning team gets a little more, as with real voters
Cy Young      the pitcher with the most value, with a nod to wins
Rookie of     the most value among rookies: players with fewer than 130
  the Year    at-bats and 50 innings before this season. Not given in a
              league's first season, when nobody has a history yet
Reliever of   the reliever (fewer than half his games started) with the most
  the Year    value, with a nod to saves and holds
Hank Aaron    the best hitter: the most batting runs, position aside
Edgar         the best DH: the most batting runs among players who started
  Martinez    at least half their games at DH
Batting       the best average with 3.1 plate appearances per team game
  Champion
Pitching      the best ERA with an inning per team game
  Champion
GM of the     the GM whose team won the most, and improved the most on last
  Year        season, with a bonus for a division title
Semifinals    whoever on the winning side did the most in the series
  / Finals MVP
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Award:
    key: str
    name: str
    icon: str
    per_league: bool  # one in each of the two leagues, or one for everyone


AWARDS: list[Award] = [
    Award("mvp", "MVP", "🏆", True),
    Award("cy_young", "Cy Young", "🔥", True),
    Award("roy", "Rookie of the Year", "🌱", True),
    Award("reliever", "Reliever of the Year", "🧯", True),
    Award("hank_aaron", "Hank Aaron Award", "💪", True),
    Award("edgar_martinez", "Edgar Martinez Award", "🏏", False),
    Award("batting_champ", "Batting Champion", "🎯", True),
    Award("pitching_champ", "Pitching Champion", "🧊", True),
    Award("gm_of_year", "GM of the Year", "💼", True),
    Award("semis_mvp", "Semifinals MVP", "🥈", True),
    Award("finals_mvp", "Finals MVP", "🥇", False),
]
BY_KEY = {a.key: a for a in AWARDS}
# Decided when the regular season ends; the series MVPs come with the series.
REGULAR = [a.key for a in AWARDS if a.key not in ("semis_mvp", "finals_mvp")]

# Rookie limits: fewer than this many at-bats and outs before this season.
ROOKIE_AB = 130
ROOKIE_OUTS = 150
# Batting title: plate appearances per team game. ERA title: outs per game.
BATTING_TITLE_PA = 3.1
ERA_TITLE_OUTS = 3.0
# Edgar Martinez: share of a player's starts that were at DH.
DH_SHARE = 0.5

# Position adjustments in runs over a full season of starts (FanGraphs' scale).
FULL_SEASON = 162
POS_RUNS = {
    "c": 12.5,
    "ss": 7.5,
    "2b": 2.5,
    "cf": 2.5,
    "3b": 2.5,
    "lf": -7.5,
    "rf": -7.5,
    "1b": -12.5,
    "dh": -17.5,
}
WOBA_SCALE = 1.2
REPLACEMENT_RUNS_PER_PA = 20 / 600
RUNS_PER_WIN = 10
# A replacement pitcher allows this many more runs per nine than average.
REPLACEMENT_GAP_SP = 1.0
REPLACEMENT_GAP_RP = 0.6
# What voters weigh beyond value.
MVP_PITCHER_DISCOUNT = 0.8
MVP_TEAM_WEIGHT = 4.0  # a .600 team's player gets 0.4 wins of value
CY_WIN_WEIGHT = 0.05
RELIEF_SAVE_WEIGHT = 0.05
RELIEF_HOLD_WEIGHT = 0.03
GM_DIVISION_BONUS = 4.0


def _n(c: dict, k: str) -> int:
    return int(c.get(k) or 0)


def pa(c: dict) -> int:
    return (
        _n(c, "bat_ab") + _n(c, "bat_walks") + _n(c, "bat_hbp") + _n(c, "bat_sac_flys")
    )


def avg(c: dict) -> float:
    return _n(c, "bat_hits") / _n(c, "bat_ab") if _n(c, "bat_ab") else 0.0


def era(c: dict) -> float:
    return (
        27 * _n(c, "pitch_earned_runs") / _n(c, "pitch_outs")
        if _n(c, "pitch_outs")
        else 0.0
    )


def woba(c: dict) -> float:
    n = pa(c)
    if not n:
        return 0.0
    singles = (
        _n(c, "bat_hits")
        - _n(c, "bat_doubles")
        - _n(c, "bat_triples")
        - _n(c, "bat_home_runs")
    )
    num = (
        0.69 * _n(c, "bat_walks")
        + 0.72 * _n(c, "bat_hbp")
        + 0.89 * singles
        + 1.27 * _n(c, "bat_doubles")
        + 1.62 * _n(c, "bat_triples")
        + 2.10 * _n(c, "bat_home_runs")
    )
    return num / n


def _fip_raw(c: dict) -> float:
    outs = _n(c, "pitch_outs")
    if not outs:
        return 0.0
    raw = (
        13 * _n(c, "pitch_home_runs")
        + 3 * (_n(c, "pitch_walks") + _n(c, "pitch_hit_batters"))
        - 2 * _n(c, "pitch_strike_outs")
    )
    return raw / (outs / 3)


def is_hitter(c: dict) -> bool:
    """Mostly a hitter: more games at the plate than on the mound."""
    return _n(c, "bat_games_played") > _n(c, "pitch_games_played") and pa(c) > 0


def is_reliever(c: dict) -> bool:
    g = _n(c, "pitch_games_played")
    return g > 0 and 2 * _n(c, "pitch_games_started") < g


@dataclass
class League:
    """League-wide rates the values are measured against."""

    games: int  # games each team played
    woba: float
    era: float
    fip_const: float

    @classmethod
    def of(cls, cands: list[dict], games: int) -> League:
        pas = sum(pa(c) for c in cands)
        lg_woba = sum(woba(c) * pa(c) for c in cands) / pas if pas else 0.0
        outs = sum(_n(c, "pitch_outs") for c in cands)
        lg_era = (
            27 * sum(_n(c, "pitch_earned_runs") for c in cands) / outs if outs else 4.5
        )
        lg_fip = (
            sum(_fip_raw(c) * _n(c, "pitch_outs") for c in cands) / outs
            if outs
            else 0.0
        )
        return cls(max(1, games), lg_woba, lg_era, lg_era - lg_fip)


def batting_runs(c: dict, lg: League) -> float:
    """Runs above average at the plate and on the bases."""
    bat = (woba(c) - lg.woba) / WOBA_SCALE * pa(c)
    run = 0.2 * _n(c, "bat_stolen_bases") - 0.4 * _n(c, "bat_caught_stealing")
    return bat + run


def hitter_war(c: dict, lg: League) -> float:
    pos = (c.get("position") or "").lower()
    pos_runs = POS_RUNS.get(pos, 0.0) * _n(c, "pos_starts") / FULL_SEASON
    repl = REPLACEMENT_RUNS_PER_PA * pa(c)
    return (batting_runs(c, lg) + pos_runs + repl) / RUNS_PER_WIN


def pitcher_war(c: dict, lg: League) -> float:
    outs = _n(c, "pitch_outs")
    if not outs:
        return 0.0
    rate = 0.5 * (_fip_raw(c) + lg.fip_const) + 0.5 * era(c)
    gap = REPLACEMENT_GAP_RP if is_reliever(c) else REPLACEMENT_GAP_SP
    return (lg.era + gap - rate) * outs / 27 / RUNS_PER_WIN


def war(c: dict, lg: League) -> float:
    return hitter_war(c, lg) if is_hitter(c) else pitcher_war(c, lg)


def is_rookie(c: dict) -> bool:
    return _n(c, "prior_ab") < ROOKIE_AB and _n(c, "prior_outs") < ROOKIE_OUTS


# ── Lines ─────────────────────────────────────────────────────────────────────


def _rate3(x: float) -> str:
    return f"{x:.3f}".lstrip("0") if x < 1 else f"{x:.3f}"


def hitter_line(c: dict) -> str:
    return f"{_rate3(avg(c))}, {_n(c, 'bat_home_runs')} HR, {_n(c, 'bat_rbi')} RBI"


def pitcher_line(c: dict) -> str:
    if is_reliever(c) and (_n(c, "pitch_saves") or _n(c, "pitch_holds")):
        lead = (
            f"{_n(c, 'pitch_saves')} SV"
            if _n(c, "pitch_saves") >= _n(c, "pitch_holds")
            else f"{_n(c, 'pitch_holds')} HLD"
        )
        return f"{lead}, {era(c):.2f} ERA, {_n(c, 'pitch_strike_outs')} K"
    return (
        f"{_n(c, 'pitch_wins')}-{_n(c, 'pitch_losses')}, {era(c):.2f} ERA,"
        f" {_n(c, 'pitch_strike_outs')} K"
    )


def line(c: dict) -> str:
    return hitter_line(c) if is_hitter(c) else pitcher_line(c)


# ── Deciding ──────────────────────────────────────────────────────────────────


def _win(award: str, scope: str, c: dict, value: float, text: str) -> dict:
    return {
        "award": award,
        "scope": scope,
        "player_id": c["player_id"],
        "team_id": c["team_id"],
        "value": round(value, 3),
        "line": text,
    }


def _best(cands, key):
    """The candidate with the highest key, ties to the first by player id so
    the same season always gives the same answer."""
    cands = sorted(cands, key=lambda c: c["player_id"])
    return max(cands, key=key, default=None)


def regular_awards(
    cands: list[dict],
    games: int,
    team_pct: dict[str, float],
    first_season: bool = False,
) -> list[dict]:
    """The regular season's player awards. Each candidate is a player's
    season totals (the stat columns), with:

      player_id, team_id   the team he played the most games for
      scope                that team's league ('' without divisions)
      position             the position he started at most (lowercase,
                           'dh' included), or None
      pos_starts, starts   starts there, and in the lineup at all
      prior_ab, prior_outs his at-bats and outs in earlier seasons

    games is how many games each team played; team_pct each team's winning
    percentage. Returns one row per award won: award, scope, player_id,
    team_id, value and line."""
    lg = League.of(cands, games)
    for c in cands:
        c["_war"] = war(c, lg)
    out: list[dict] = []
    scopes = sorted({c["scope"] for c in cands})
    for scope in scopes:
        mine = [c for c in cands if c["scope"] == scope]
        hitters = [c for c in mine if is_hitter(c)]
        pitchers = [c for c in mine if not is_hitter(c) and _n(c, "pitch_outs")]

        def mvp_score(c):
            v = c["_war"] * (1 if is_hitter(c) else MVP_PITCHER_DISCOUNT)
            return v + (team_pct.get(c["team_id"], 0.5) - 0.5) * MVP_TEAM_WEIGHT

        if c := _best(hitters + pitchers, mvp_score):
            out.append(_win("mvp", scope, c, c["_war"], line(c)))

        if c := _best(
            pitchers, lambda c: c["_war"] + CY_WIN_WEIGHT * _n(c, "pitch_wins")
        ):
            out.append(_win("cy_young", scope, c, c["_war"], pitcher_line(c)))

        if not first_season:
            rookies = [c for c in hitters + pitchers if is_rookie(c)]
            if c := _best(rookies, lambda c: c["_war"]):
                out.append(_win("roy", scope, c, c["_war"], line(c)))

        relievers = [c for c in pitchers if is_reliever(c)]
        if c := _best(
            relievers,
            lambda c: (
                c["_war"]
                + RELIEF_SAVE_WEIGHT * _n(c, "pitch_saves")
                + RELIEF_HOLD_WEIGHT * _n(c, "pitch_holds")
            ),
        ):
            out.append(_win("reliever", scope, c, c["_war"], pitcher_line(c)))

        if c := _best(hitters, lambda c: batting_runs(c, lg)):
            out.append(
                _win("hank_aaron", scope, c, batting_runs(c, lg), hitter_line(c))
            )

        qualified = [c for c in hitters if pa(c) >= BATTING_TITLE_PA * lg.games]
        if c := _best(qualified, lambda c: (avg(c), _n(c, "bat_hits"))):
            out.append(_win("batting_champ", scope, c, avg(c), _rate3(avg(c))))

        qualified = [
            c for c in pitchers if _n(c, "pitch_outs") >= ERA_TITLE_OUTS * lg.games
        ]
        if c := _best(qualified, lambda c: (-era(c), _n(c, "pitch_outs"))):
            out.append(_win("pitching_champ", scope, c, era(c), f"{era(c):.2f} ERA"))

    dhs = [
        c
        for c in cands
        if is_hitter(c)
        and (c.get("position") or "").lower() == "dh"
        and _n(c, "pos_starts") >= DH_SHARE * max(1, _n(c, "starts"))
    ]
    if c := _best(dhs, lambda c: batting_runs(c, lg)):
        out.append(_win("edgar_martinez", "", c, batting_runs(c, lg), hitter_line(c)))
    for c in cands:
        c.pop("_war", None)
    return out


def gm_of_year(teams: list[dict]) -> list[dict]:
    """GM of the Year in each league. Each team: team_id, gm_id, scope,
    wins, losses, prev_wins and prev_losses (None for a first season) and
    division_title. The score is wins over .500 and wins gained on last
    season (both scaled to this season's length), plus a bonus for winning
    the division."""
    out = []
    for scope in sorted({t["scope"] for t in teams}):

        def score(t):
            g = t["wins"] + t["losses"]
            if not g:
                return float("-inf")
            pct = t["wins"] / g
            pg = (t.get("prev_wins") or 0) + (t.get("prev_losses") or 0)
            prev = t["prev_wins"] / pg if pg else 0.5
            s = 0.4 * (pct - 0.5) * g + 0.6 * (pct - prev) * g
            return s + (GM_DIVISION_BONUS if t.get("division_title") else 0)

        mine = sorted(
            (t for t in teams if t["scope"] == scope and t.get("gm_id")),
            key=lambda t: t["team_id"],
        )
        if not mine:
            continue
        t = max(mine, key=score)
        text = f"{t['wins']}-{t['losses']}"
        pg = (t.get("prev_wins") or 0) + (t.get("prev_losses") or 0)
        if pg:
            g = t["wins"] + t["losses"]
            gained = round(t["wins"] - t["prev_wins"] * g / pg)
            if gained > 0:
                text += f", up {gained} win{'s' if gained != 1 else ''}"
        if t.get("division_title"):
            text += ", division title"
        out.append(
            {
                "award": "gm_of_year",
                "scope": scope,
                "player_id": None,
                "team_id": t["team_id"],
                "gm_id": t["gm_id"],
                "value": round(score(t), 3),
                "line": text,
            }
        )
    return out


# ── Series MVPs ───────────────────────────────────────────────────────────────


def series_value(c: dict) -> float:
    """How much a player did in a series: total bases, runs, RBI, walks and
    steals at the plate; outs and strikeouts on the mound, less hits, walks
    and earned runs allowed (the All-Star Game MVP's measure)."""
    singles = (
        _n(c, "bat_hits")
        - _n(c, "bat_doubles")
        - _n(c, "bat_triples")
        - _n(c, "bat_home_runs")
    )
    tb = (
        singles
        + 2 * _n(c, "bat_doubles")
        + 3 * _n(c, "bat_triples")
        + 4 * _n(c, "bat_home_runs")
    )
    bat = (
        tb
        + _n(c, "bat_runs")
        + _n(c, "bat_rbi")
        + 0.5 * (_n(c, "bat_walks") + _n(c, "bat_stolen_bases"))
    )
    pitch = (
        0.5 * _n(c, "pitch_outs")
        + _n(c, "pitch_strike_outs")
        - 0.5 * (_n(c, "pitch_hits") + _n(c, "pitch_walks"))
        - 2 * _n(c, "pitch_earned_runs")
    )
    return bat + pitch


def series_line(c: dict) -> str:
    """A series in a few words: 9-for-24, 3 HR, 7 RBI or 2-0, 1.50 ERA,
    14 K."""
    bat_v = _n(c, "bat_ab") + _n(c, "bat_walks")
    if bat_v and (bat_v * 3 >= _n(c, "pitch_outs")):
        parts = [f"{_n(c, 'bat_hits')}-for-{_n(c, 'bat_ab')}"]
        for k, label in (
            ("bat_home_runs", "HR"),
            ("bat_rbi", "RBI"),
            ("bat_runs", "R"),
        ):
            if _n(c, k):
                parts.append(f"{_n(c, k)} {label}")
        return ", ".join(parts)
    outs = _n(c, "pitch_outs")
    parts = []
    if _n(c, "pitch_wins") or _n(c, "pitch_losses"):
        parts.append(f"{_n(c, 'pitch_wins')}-{_n(c, 'pitch_losses')}")
    if _n(c, "pitch_saves"):
        parts.append(f"{_n(c, 'pitch_saves')} SV")
    parts.append(f"{era(c):.2f} ERA")
    parts.append(f"{outs // 3}.{outs % 3} IP")
    if _n(c, "pitch_strike_outs"):
        parts.append(f"{_n(c, 'pitch_strike_outs')} K")
    return ", ".join(parts)


def series_mvp(lines: list[dict]) -> dict | None:
    """The MVP from the winning side's series totals, one per player."""
    c = _best(lines, series_value)
    if c is None:
        return None
    return {
        "player_id": c["player_id"],
        "team_id": c["team_id"],
        "value": round(series_value(c), 3),
        "line": series_line(c),
    }
