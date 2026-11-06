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
ERA Champion  the best ERA with an inning per team game
Wins Champion the most wins, ties to the better ERA
Gold Glove    at each position (pitchers included), the best fielder among
              players with a third of their team's starts there: mostly his
              defense rating there, then his range (a catcher's
              caught-stealing rate) and how rarely he makes errors
Platinum      the Gold Glove winner who saved the most runs, a simple
  Glove       SDI-style defensive score: his defense rating against the
              others at his position, scaled by how much that position
              matters and how much he played, plus plays made, errors
              avoided and (catchers) runners thrown out beyond the
              position's average. Pitchers play few innings and get few
              chances, so they almost never win it
Silver        at each position and DH, voted by the league's GMs: each
  Slugger     ranks three hitters by what that GM values at the plate (the
              persona dials, src/league/personas.py), for 5, 3 and 1 points
GM of the     the GM whose team won the most, and improved the most on last
  Year        season, with a bonus for a division title
Semifinals    whoever on the winning side did the most in the series
  / Finals MVP
"""

from __future__ import annotations

from dataclasses import dataclass

from src.stats import qualifiers
from src.stats.advanced import WOBA_SCALE, fip_raw as _fip_raw, pa, woba


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
    Award("era_champ", "ERA Champion", "🧊", True),
    Award("wins_champ", "Wins Champion", "✌️", True),
    Award("gold_glove", "Gold Glove", "🧤", True),
    Award("platinum_glove", "Platinum Glove", "💠", True),
    Award("silver_slugger", "Silver Slugger", "🪵", True),
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
BATTING_TITLE_PA = qualifiers.BAT_PA_PER_GAME
ERA_TITLE_OUTS = 3 * qualifiers.PITCH_IP_PER_GAME
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


def avg(c: dict) -> float:
    return _n(c, "bat_hits") / _n(c, "bat_ab") if _n(c, "bat_ab") else 0.0


def era(c: dict) -> float:
    return (
        27 * _n(c, "pitch_earned_runs") / _n(c, "pitch_outs")
        if _n(c, "pitch_outs")
        else 0.0
    )


def is_hitter(c: dict) -> bool:
    """Mostly a hitter: more games at the plate than on the mound."""
    return _n(c, "bat_games_played") > _n(c, "pitch_games_played") and pa(c) > 0


def is_reliever(c: dict) -> bool:
    return qualifiers.is_reliever(
        _n(c, "pitch_games_played"), _n(c, "pitch_games_started")
    )


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


def _win(
    award: str, scope: str, c: dict, value: float, text: str, position: str = ""
) -> dict:
    return {
        "award": award,
        "scope": scope,
        "position": position,
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
            out.append(_win("era_champ", scope, c, era(c), f"{era(c):.2f} ERA"))

        if c := _best(pitchers, lambda c: (_n(c, "pitch_wins"), -era(c))):
            if _n(c, "pitch_wins"):
                text = (
                    f"{_n(c, 'pitch_wins')}-{_n(c, 'pitch_losses')}, {era(c):.2f} ERA"
                )
                out.append(_win("wins_champ", scope, c, _n(c, "pitch_wins"), text))

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


# ── Gold Gloves ───────────────────────────────────────────────────────────────

FIELD_POSITIONS = ("c", "1b", "2b", "3b", "ss", "lf", "cf", "rf")
POSITION_NAMES = {
    "p": "P", "c": "C", "1b": "1B", "2b": "2B", "3b": "3B", "ss": "SS",
    "lf": "LF", "cf": "CF", "rf": "RF", "dh": "DH",
}  # fmt: skip
# Enough of the team's games started at the position (pitchers: the ERA
# title's inning a game).
GLOVE_STARTS_SHARE = 1 / 3
GLOVE_RATING_WEIGHT = 0.6
GLOVE_RANGE_WEIGHT = 0.25
GLOVE_SURE_WEIGHT = 0.15


def _zs(values: list[float]) -> list[float]:
    if not values:
        return []
    m = sum(values) / len(values)
    sd = (sum((v - m) ** 2 for v in values) / len(values)) ** 0.5
    return [(v - m) / sd if sd else 0.0 for v in values]


def _glove_scores(group: list[dict], pos: str) -> list[float]:
    """Each fielder's Gold Glove score among those at his position: z-scores
    of his defense rating there, his range (chances a start; a catcher's
    caught-stealing rate; a pitcher's chances a nine innings) and his sure
    hands (fewer errors a chance). Pitchers have no defense rating, so for
    them it's the stats alone."""
    rating = _zs([float((c.get("ratings") or {}).get(pos, 0)) for c in group])
    rng, sure = [], []
    for c in group:
        po, a = _n(c, "field_putouts"), _n(c, "field_assists")
        e = _n(c, "field_errors")
        if pos == "c":
            cs, sb = _n(c, "field_catcher_cs"), _n(c, "field_catcher_sb")
            rng.append(cs / (cs + sb) if cs + sb else 0.0)
        elif pos == "p":
            rng.append((po + a) * 27 / max(1, _n(c, "pitch_outs")))
        else:
            chances = po + a + _n(c, "field_double_plays")
            rng.append(chances / max(1, _n(c, "pos_starts")))
        sure.append(-e / (po + a + e) if po + a + e else 0.0)
    if not any(rating):
        return [0.6 * g + 0.4 * s for g, s in zip(_zs(rng), _zs(sure))]
    return [
        GLOVE_RATING_WEIGHT * r + GLOVE_RANGE_WEIGHT * g + GLOVE_SURE_WEIGHT * s
        for r, g, s in zip(rating, _zs(rng), _zs(sure))
    ]


# The Platinum Glove's defensive runs. Runs a season for each point of
# defense rating above the position's average, for an everyday player: the
# sim leans hardest on the middle infield, catcher and center field.
# Pitchers have no defense rating (the sim doesn't use one for them).
PLAT_RATING_RUNS = {
    "ss": 0.6, "2b": 0.5, "c": 0.5, "cf": 0.5, "3b": 0.4,
    "rf": 0.3, "lf": 0.3, "1b": 0.15, "p": 0.0,
}  # fmt: skip
PLAT_PLAY_RUNS = 0.1  # an extra play made (many chances are routine)
PLAT_FIRST_BASE_PLAY_RUNS = 0.03  # most of a first baseman's are catching throws
PLAT_ERROR_RUNS = 0.75  # an error avoided
PLAT_CS_RUNS = 0.6  # a runner thrown out instead of stealing


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def defensive_runs(c: dict, group: list[dict], pos: str, games: int) -> float:
    """Runs he saved against an average fielder at his position (the Gold
    Glove group), a rough version of SABR's Defensive Index: his rating,
    the extra plays he made, the errors he didn't, and for a catcher the
    runners he threw out. Every part grows with how much he played, so an
    everyday shortstop counts for far more than a starting pitcher."""
    games = max(1, games)

    def share(x):  # his part of the team's season at the position
        if pos == "p":
            return min(1.0, _n(x, "pitch_outs") / (27 * games))
        return min(1.0, _n(x, "pos_starts") / games)

    def rating(x):
        return float((x.get("ratings") or {}).get(pos, 0))

    def chances(x):
        return _n(x, "field_putouts") + _n(x, "field_assists")

    def plays_a_game(x):  # a game: a start, or nine innings for a pitcher
        played = _n(x, "pitch_outs") / 27 if pos == "p" else _n(x, "pos_starts")
        return (chances(x) + _n(x, "field_double_plays")) / max(1, played)

    def error_rate(x):
        e = _n(x, "field_errors")
        return e / (chances(x) + e) if chances(x) + e else 0.0

    pos_runs = PLAT_RATING_RUNS.get(pos, 0.3)
    runs = (rating(c) - _mean([rating(x) for x in group])) * pos_runs * share(c)
    if pos != "c":  # a catcher's chances are mostly strikeouts
        played = _n(c, "pitch_outs") / 27 if pos == "p" else _n(c, "pos_starts")
        per_play = PLAT_FIRST_BASE_PLAY_RUNS if pos == "1b" else PLAT_PLAY_RUNS
        extra = plays_a_game(c) - _mean([plays_a_game(x) for x in group])
        runs += extra * played * per_play
    e = _n(c, "field_errors")
    expected_e = _mean([error_rate(x) for x in group]) * (chances(c) + e)
    runs += (expected_e - e) * PLAT_ERROR_RUNS
    if pos == "c":
        cs, sb = _n(c, "field_catcher_cs"), _n(c, "field_catcher_sb")
        lg_cs = sum(_n(x, "field_catcher_cs") for x in group)
        lg_tries = lg_cs + sum(_n(x, "field_catcher_sb") for x in group)
        if lg_tries:
            runs += (cs - (cs + sb) * lg_cs / lg_tries) * PLAT_CS_RUNS
    return runs


def season_defense(cands: list[dict], games: int) -> dict[str, float]:
    """Defensive runs (defensive_runs()) for every hitter at the position
    he started at most, measured against the league's regulars there (a
    third of the team's starts, as for the Gold Glove; everyone there when
    fewer than two qualify). Pitchers aren't scored."""
    games = max(1, games)
    by_pos: dict[str, list[dict]] = {}
    for c in cands:
        pos = (c.get("position") or "").lower()
        if pos in FIELD_POSITIONS and is_hitter(c) and _n(c, "pos_starts"):
            by_pos.setdefault(pos, []).append(c)
    out = {}
    for pos, players in by_pos.items():
        group = [
            c for c in players if _n(c, "pos_starts") >= GLOVE_STARTS_SHARE * games
        ]
        if len(group) < 2:
            group = players
        for c in players:
            out[c["player_id"]] = defensive_runs(c, group, pos, games)
    return out


def gold_gloves(cands: list[dict], games: int) -> list[dict]:
    """A Gold Glove at each position in each league, and a Platinum Glove
    for the winner who saved the most runs (defensive_runs()). Candidates as for regular_awards(),
    each also with ratings (PlayerEvaluator) and fielding totals."""
    games = max(1, games)
    out = []
    for scope in sorted({c["scope"] for c in cands}):
        winners = []
        for pos in FIELD_POSITIONS + ("p",):
            if pos == "p":
                group = [
                    c for c in cands
                    if c["scope"] == scope and not is_hitter(c)
                    and _n(c, "pitch_outs") >= ERA_TITLE_OUTS * games
                ]  # fmt: skip
            else:
                group = [
                    c for c in cands
                    if c["scope"] == scope and is_hitter(c)
                    and (c.get("position") or "").lower() == pos
                    and _n(c, "pos_starts") >= GLOVE_STARTS_SHARE * games
                ]  # fmt: skip
            if len(group) < 2:
                continue
            scores = dict(
                zip((c["player_id"] for c in group), _glove_scores(group, pos))
            )
            c = _best(group, lambda c: scores[c["player_id"]])
            e = _n(c, "field_errors")
            text = f"{POSITION_NAMES[pos]}, {e} error{'' if e == 1 else 's'}"
            winners.append((defensive_runs(c, group, pos, games), pos, c))
            out.append(_win("gold_glove", scope, c, scores[c["player_id"]], text, pos))
        if winners:
            score, pos, c = max(winners, key=lambda w: (w[0], w[2]["player_id"]))
            out.append(
                _win(
                    "platinum_glove",
                    scope,
                    c,
                    score,
                    f"Gold Glove at {POSITION_NAMES[pos]}, {score:+.0f} defensive runs",
                    pos,
                )
            )
    return out


# ── Silver Sluggers ───────────────────────────────────────────────────────────

SLUGGER_POSITIONS = FIELD_POSITIONS + ("dh",)
SLUGGER_POINTS = (5, 3, 1)
SLUGGER_NOISE = 0.25
SLUGGER_LOYALTY = 0.5  # z-score boost for a GM's own player, at loyalty 100


def slugger_ballot(
    group: list[dict], lg: League, dials: dict | None, team_id: str | None, rng
) -> list[str]:
    """One GM's top three hitters at a position, best first. An analytics
    GM goes by batting runs (wOBA), an old-school one by average (scaled by
    playing time), home runs and RBI; a loyal GM nudges his own players
    up. With rng, a little wobble, so GMs don't all vote alike."""
    d = {"analytics": 50, "loyalty": 50, **(dials or {})}
    modern = d["analytics"] / 100
    full = BATTING_TITLE_PA * lg.games
    bat = _zs([batting_runs(c, lg) for c in group])
    avgs = _zs([avg(c) * min(1.0, pa(c) / full) for c in group])
    hrs = _zs([float(_n(c, "bat_home_runs")) for c in group])
    rbis = _zs([float(_n(c, "bat_rbi")) for c in group])
    ranked = []
    for i, c in enumerate(group):
        s = modern * bat[i] + (1 - modern) * (avgs[i] + hrs[i] + rbis[i]) / 3
        if team_id and c["team_id"] == team_id:
            s += SLUGGER_LOYALTY * d["loyalty"] / 100
        if rng:
            s += rng.gauss(0, SLUGGER_NOISE)
        ranked.append((s, c["player_id"]))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    return [pid for _, pid in ranked[: len(SLUGGER_POINTS)]]


def silver_sluggers(
    cands: list[dict], games: int, voters: list[dict], rng=None
) -> list[dict]:
    """A Silver Slugger at each position and DH in each league, voted by
    the GMs whose teams are in that league. voters: team_id, scope and
    dials (None votes with neutral dials). A player needs a third of his
    team's games started at the position. The line gives the winner's
    season and his first-place votes."""
    lg = League.of(cands, games)
    out = []
    for scope in sorted({c["scope"] for c in cands}):
        mine = [v for v in voters if v["scope"] == scope] or [
            {"team_id": None, "scope": scope, "dials": None}
        ]
        for pos in SLUGGER_POSITIONS:
            group = sorted(
                (
                    c for c in cands
                    if c["scope"] == scope and is_hitter(c)
                    and (c.get("position") or "").lower() == pos
                    and _n(c, "pos_starts") >= GLOVE_STARTS_SHARE * lg.games
                ),
                key=lambda c: c["player_id"],
            )  # fmt: skip
            if not group:
                continue
            points: dict[str, int] = {}
            firsts: dict[str, int] = {}
            for v in mine:
                ballot = slugger_ballot(
                    group, lg, v.get("dials"), v.get("team_id"), rng
                )
                for pts, pid in zip(SLUGGER_POINTS, ballot):
                    points[pid] = points.get(pid, 0) + pts
                firsts[ballot[0]] = firsts.get(ballot[0], 0) + 1
            pid = max(sorted(points), key=lambda p: (points[p], firsts.get(p, 0)))
            c = next(c for c in group if c["player_id"] == pid)
            n = firsts.get(pid, 0)
            text = (
                f"{POSITION_NAMES[pos]}, {hitter_line(c)}"
                f" · {n} of {len(mine)} first-place votes"
            )
            out.append(_win("silver_slugger", scope, c, points[pid], text, pos))
    return out
