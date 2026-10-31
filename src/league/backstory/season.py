# src/league/backstory/season.py
"""
One made-up past season: who played how much, their stat lines, every
game's score, and the playoffs.

Nothing here touches the database. The numbers come from calibration.py,
fitted to seasons the real engine played, so a made-up season has the
engine's league averages and spreads:

1. Playing time from each team's depth chart (the k-th best hitter gets the
   plate appearances the engine's k-th busiest hitter gets, and so on).
2. Stat lines from ratings: each event's rate per plate appearance (or per
   batter faced) is a linear fit on the skills, drawn with binomial luck.
3. Team strength: the runs a team's hitters should create and its pitchers
   should allow, plus a dose of form (things the ratings don't capture).
4. Games: every scheduled game played half-inning by half-inning from the
   two teams' strengths, so standings, line scores and walk-offs look real.
5. Lines are then scaled so each team's runs, RBI, runs allowed and hits
   match its games, and wins, losses and saves go to its pitchers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from src.league.backstory.calibration import PARAMS
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_skills import PlayerSkills
from src.player.positions import is_pitcher

P = PARAMS

# Team form: a per-season multiplier on runs scored and allowed for what the
# ratings don't see (lineup choices, defense, chemistry). Its size is set so
# the spread of wins matches the engine's (tests/league/test_backstory.py).
TEAM_FORM_SD = 0.06

# Spread of the luck in how a pitcher's base runners turn into runs.
SEQUENCING_SD = 0.18
# How strongly a pitcher's run prevention, against his team's, steers his
# share of the team's wins and losses.
DECISION_POWER = 1.0
# Stolen bases rise faster than linearly with speed: a rate r from the fit
# becomes SB_REF * (r / SB_REF) ** SB_POWER, which keeps the league total
# about the same and gives the fastest runners the engine's totals.
SB_REF = 0.012
SB_POWER = 1.6

# A game still tied after this many innings goes to the home team.
MAX_INNINGS = 20

FIELD_ORDER = ("c", "ss", "cf", "2b", "3b", "rf", "lf", "1b")
ROTATION_SIZE = 5

HIT_EVENTS = ("singles", "doubles", "triples", "home_runs")


@dataclass
class Member:
    """A player on a team in one past season, with his ratings that year."""

    player_id: str
    position: str
    throws: str
    age: int
    skills: dict[str, float]
    ratings: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.ratings:
            sk = PlayerSkills(self.skills, age=self.age, validate=False)
            self.ratings = PlayerEvaluator.rate_player(sk, self.throws)

    @property
    def pitcher(self) -> bool:
        return is_pitcher(self.position)


@dataclass
class Line:
    """A player's season, as player_season_stats columns (without the
    prefix-free keys the table doesn't have)."""

    player_id: str
    team_id: str
    slot: str  # where he played: a field position, dh, sp or rp
    stats: dict[str, int] = field(default_factory=dict)
    exp_runs: float = 0.0  # runs his events are worth (batting) or allowed


@dataclass
class Game:
    id: str
    game_date: str
    home_team_id: str
    away_team_id: str
    away_innings: list[int]
    home_innings: list[int]
    home_hits: int = 0
    away_hits: int = 0
    home_errors: int = 0
    away_errors: int = 0
    series_id: str | None = None

    @property
    def home_score(self) -> int:
        return sum(self.home_innings)

    @property
    def away_score(self) -> int:
        return sum(self.away_innings)

    @property
    def winner_id(self) -> str:
        return (
            self.home_team_id
            if self.home_score > self.away_score
            else self.away_team_id
        )

    @property
    def innings_played(self) -> int:
        return max(len(self.away_innings), len(self.home_innings))


# ── Rates from ratings ────────────────────────────────────────────────────────


def _rate(model: dict, skills: dict[str, float]) -> float:
    r = model["intercept"] + sum(
        c * skills.get(s, 50) for s, c in model.items() if s != "intercept"
    )
    return max(0.0, r)


def batting_rates(skills: dict[str, float]) -> dict[str, float]:
    rates = {ev: _rate(m, skills) for ev, m in P["bat_rates"].items()}
    for ev in ("stolen_bases", "caught_stealing"):
        rates[ev] = SB_REF * (rates[ev] / SB_REF) ** SB_POWER
    return rates


def pitching_rates(skills: dict[str, float]) -> dict[str, float]:
    return {ev: _rate(m, skills) for ev, m in P["pit_rates"].items()}


def lw_runs(events: dict[str, float]) -> float:
    lw = P["linear_weights"]
    return sum(w * events.get(k, 0) for k, w in lw.items())


# ── Depth chart and playing time ──────────────────────────────────────────────


def _jitter(rng: np.random.Generator, value: float, sd: float = 0.08) -> float:
    return value * math.exp(rng.normal(0, sd))


def hitter_roles(hitters: list[Member]) -> list[tuple[Member, str]]:
    """Hitters best first, each with where he played: the best nine take the
    field (each position goes to the best glove there among them, scarcest
    position first) and the one left over is the DH; the rest are bench."""
    ranked = sorted(hitters, key=lambda m: -m.ratings["overall_player"])
    starters, bench = ranked[:9], ranked[9:]
    slots: dict[str, str] = {}
    free = list(starters)
    for pos in FIELD_ORDER:
        if not free:
            break
        best = max(free, key=lambda m: m.ratings.get(pos, 0))
        slots[best.player_id] = pos
        free.remove(best)
    for m in free:
        slots[m.player_id] = "dh"
    out = [(m, slots[m.player_id]) for m in starters]
    for m in bench:
        out.append((m, m.position if m.position in FIELD_ORDER else "dh"))
    return out


def pitcher_roles(pitchers: list[Member]) -> tuple[list[Member], list[Member]]:
    """(rotation, bullpen): the five best starters by SP rating, filled from
    the bullpen when a team is short, then the bullpen best first."""
    sps = sorted(
        [m for m in pitchers if m.position == "sp"], key=lambda m: -m.ratings["sp"]
    )
    rotation = sps[:ROTATION_SIZE]
    rest = sps[ROTATION_SIZE:] + [m for m in pitchers if m.position != "sp"]
    while len(rotation) < ROTATION_SIZE and rest:
        best = max(rest, key=lambda m: m.ratings["sp"])
        rotation.append(best)
        rest.remove(best)
    bullpen = sorted(rest, key=lambda m: -m.ratings["rp"])
    return rotation, bullpen


def _split(total: int, weights: list[float]) -> list[int]:
    """Whole numbers in proportion to weights that add up to total (largest
    remainders)."""
    if not weights or total <= 0:
        return [0] * len(weights)
    s = sum(weights)
    if s <= 0:
        weights = [1.0] * len(weights)
        s = float(len(weights))
    raw = [total * w / s for w in weights]
    out = [int(math.floor(r)) for r in raw]
    left = total - sum(out)
    order = sorted(range(len(raw)), key=lambda i: -(raw[i] - out[i]))
    for i in order[:left]:
        out[i] += 1
    return out


# ── Stat lines ────────────────────────────────────────────────────────────────

BAT_PA_EVENTS = (
    "singles",
    "doubles",
    "triples",
    "home_runs",
    "walks",
    "hbp",
    "strike_outs",
    "sac_flys",
    "sac_bunts",
)
PIT_BF_EVENTS = (
    "singles",
    "doubles",
    "triples",
    "home_runs",
    "walks",
    "hit_batters",
    "strike_outs",
)


def _multinomial(rng, n: int, probs: list[float]) -> list[int]:
    p = np.array(probs, dtype=float)
    total = p.sum()
    if total > 0.98:
        p *= 0.98 / total
    p = np.append(p, 1.0 - p.sum())
    return [int(x) for x in rng.multinomial(max(0, n), p)]


def batting_line(
    rng, m: Member, team_id: str, slot: str, pa: int, starter: bool = True
) -> Line:
    rates = batting_rates(m.skills)
    drawn = dict(
        zip(BAT_PA_EVENTS, _multinomial(rng, pa, [rates[e] for e in BAT_PA_EVENTS]))
    )
    on_first = drawn["singles"] + drawn["walks"] + drawn["hbp"]
    gdp = int(rng.binomial(pa, rates["gdp"]))
    sb = int(
        rng.binomial(
            max(on_first, 0), min(1.0, rates["stolen_bases"] * pa / max(1, on_first))
        )
    )
    cs = int(
        rng.binomial(
            max(on_first, 0), min(1.0, rates["caught_stealing"] * pa / max(1, on_first))
        )
    )
    hits = sum(drawn[e] for e in HIT_EVENTS)
    ab = pa - drawn["walks"] - drawn["hbp"] - drawn["sac_flys"] - drawn["sac_bunts"]
    k = drawn["strike_outs"]
    g_a, g_b = P["games_from_pa"]
    games = int(min(162, max(1, round(g_a * pa + g_b))))
    if pa < 30:
        games = max(1, min(games, pa))
    events = {**drawn, "stolen_bases": sb, "caught_stealing": cs}
    stats = {
        "bat_games_played": games,
        "bat_games_started": games if starter else games // 3,
        "bat_ab": ab,
        "bat_hits": hits,
        "bat_doubles": drawn["doubles"],
        "bat_triples": drawn["triples"],
        "bat_home_runs": drawn["home_runs"],
        "bat_walks": drawn["walks"],
        "bat_strike_outs": k,
        "bat_strike_outs_looking": int(rng.binomial(k, P["strike_outs_looking_share"])),
        "bat_hbp": drawn["hbp"],
        "bat_sac_flys": drawn["sac_flys"],
        "bat_sac_bunts": drawn["sac_bunts"],
        "bat_gdp": gdp,
        "bat_stolen_bases": sb,
        "bat_caught_stealing": cs,
    }
    line = Line(m.player_id, team_id, slot, stats)
    line.exp_runs = P["bat_run_scale"] * lw_runs(events)
    # Runs and RBI from his own events; scaled to the team's runs later
    rfe, bfe = P["runs_from_events"], P["rbi_from_events"]
    line.stats["_runs"] = max(0.0, sum(c * events.get(k, 0) for k, c in rfe.items()))
    line.stats["_rbi"] = max(0.0, sum(c * events.get(k, 0) for k, c in bfe.items()))
    return line


def expected_batting_runs(m: Member, pa: int) -> float:
    r = batting_rates(m.skills)
    return P["bat_run_scale"] * lw_runs({k: v * pa for k, v in r.items()})


def _out_rate(rates: dict) -> float:
    on = sum(rates[e] for e in PIT_BF_EVENTS if e != "strike_outs")
    return max(0.4, 1.0 - on)


def pitching_line(
    rng, m: Member, team_id: str, slot: str, outs: int, games: int, starts: int
) -> Line:
    rates = pitching_rates(m.skills)
    bf = int(round(outs / _out_rate(rates)))
    drawn = dict(
        zip(PIT_BF_EVENTS, _multinomial(rng, bf, [rates[e] for e in PIT_BF_EVENTS]))
    )
    on = sum(drawn[e] for e in PIT_BF_EVENTS if e != "strike_outs")
    real_outs = bf - on
    k = min(drawn["strike_outs"], real_outs)
    hits = sum(drawn[e] for e in HIT_EVENTS)
    stats = {
        "pitch_games_played": games,
        "pitch_games_started": starts,
        "pitch_outs": real_outs,
        "pitch_hits": hits,
        "pitch_doubles": drawn["doubles"],
        "pitch_triples": drawn["triples"],
        "pitch_home_runs": drawn["home_runs"],
        "pitch_walks": drawn["walks"],
        "pitch_hit_batters": drawn["hit_batters"],
        "pitch_strike_outs": k,
        "pitch_strike_outs_looking": int(
            rng.binomial(k, P["strike_outs_looking_share"])
        ),
        "pitch_wild_pitches": int(rng.binomial(bf, rates["wild_pitches"])),
        "pitch_count": int(round(bf * P["pitches_per_batter"])),
    }
    line = Line(m.player_id, team_id, slot, stats)
    events = {**drawn, "hbp": drawn["hit_batters"]}
    line.exp_runs = P["pit_run_scale"] * lw_runs(events)
    return line


def expected_pitching_runs(m: Member, outs: int) -> float:
    r = pitching_rates(m.skills)
    bf = outs / _out_rate(r)
    events = {k: v * bf for k, v in r.items()}
    events["hbp"] = events.get("hit_batters", 0)
    return P["pit_run_scale"] * lw_runs(events)


@dataclass
class TeamSeason:
    team_id: str
    batting: list[Line]
    pitching: list[Line]
    rotation: list[str]
    bullpen: list[str]
    exp_rs: float  # runs the team should score in a season
    exp_ra: float  # and allow


def team_season(rng, team_id: str, members: list[Member]) -> TeamSeason:
    """Playing time and stat lines for one team's season."""
    hitters = [m for m in members if not m.pitcher]
    pitchers = [m for m in members if m.pitcher]
    batting = []
    exp_rs = 0.0
    pa_table = P["hitter_pa_by_rank"]
    for k, (m, slot) in enumerate(hitter_roles(hitters)):
        if k >= len(pa_table):
            break
        pa = int(round(_jitter(rng, pa_table[k])))
        if pa < 1:
            continue
        batting.append(batting_line(rng, m, team_id, slot, pa, starter=k < 9))
        exp_rs += expected_batting_runs(m, pa)

    rotation, bullpen = pitcher_roles(pitchers)
    gs_table = P["starter_gs_by_rank"][: len(rotation)]
    starts = _split(162, [_jitter(rng, g, 0.05) for g in gs_table])
    pitching = []
    exp_ra = 0.0
    for m, gs in zip(rotation, starts):
        outs = int(round(gs * _jitter(rng, P["starter_outs_per_start"], 0.06)))
        pitching.append(pitching_line(rng, m, team_id, "sp", outs, gs, gs))
        exp_ra += expected_pitching_runs(m, outs)
    g_table, o_table = P["reliever_games_by_rank"], P["reliever_outs_by_rank"]
    for k, m in enumerate(bullpen[: len(o_table)]):
        outs = int(round(_jitter(rng, o_table[k], 0.12)))
        games = int(round(_jitter(rng, g_table[k], 0.1)))
        if outs < 1 or games < 1:
            continue
        pitching.append(pitching_line(rng, m, team_id, "rp", outs, games, 0))
        exp_ra += expected_pitching_runs(m, outs)
    return TeamSeason(
        team_id,
        batting,
        pitching,
        [m.player_id for m in rotation],
        [m.player_id for m in bullpen],
        exp_rs,
        exp_ra,
    )


# ── Games ─────────────────────────────────────────────────────────────────────


def strengths(rng, teams: list[TeamSeason]) -> dict[str, tuple[float, float]]:
    """{team_id: (offense, defense)}: runs-per-game multipliers around 1.0.
    A team's runs in a game are league runs per game x its offense x the
    other team's defense (higher defense = more runs allowed)."""
    rs = np.array([t.exp_rs for t in teams])
    ra = np.array([t.exp_ra for t in teams])
    off = rs / rs.mean() * np.exp(rng.normal(0, TEAM_FORM_SD, len(teams)))
    dfn = ra / ra.mean() * np.exp(rng.normal(0, TEAM_FORM_SD, len(teams)))
    return {t.team_id: (float(o), float(d)) for t, o, d in zip(teams, off, dfn)}


def _half_innings(rng, mean_runs: float, n: int) -> np.ndarray:
    """Runs in n half-innings for a team expected to score mean_runs in nine:
    gamma-Poisson, so the game totals have the engine's spread."""
    m = max(0.05, mean_runs / 9)
    var = P["runs_per_game_var"]
    rpg = P["runs_per_game"]
    r_game = rpg * rpg / max(0.1, var - rpg)  # dispersion of a game's total
    shape = r_game / 9
    lam = rng.gamma(shape, m / shape, n)
    return rng.poisson(lam)


def play_game(rng, home_mean: float, away_mean: float) -> tuple[list[int], list[int]]:
    """(away innings, home innings). The home team skips the bottom of the
    last inning when it's already ahead (stored as 0; the scoreboard shows
    an X), and extra innings go on until someone leads after one."""
    away = [int(x) for x in _half_innings(rng, away_mean, 9)]
    home = [int(x) for x in _half_innings(rng, home_mean, 9)]
    if sum(home[:8]) > sum(away):
        home[8] = 0
    inning = 9
    while sum(home) == sum(away):
        inning += 1
        if inning > MAX_INNINGS:
            home[-1] += 1
            break
        away.append(int(_half_innings(rng, away_mean, 1)[0]))
        home.append(int(_half_innings(rng, home_mean, 1)[0]))
        if sum(home[:-1]) > sum(away):
            home[-1] = 0
    return away, home


def game_means(s: dict, home: str, away: str) -> tuple[float, float]:
    rpg = P["runs_per_game"]
    (ho, hd), (ao, ad) = s[home], s[away]
    return rpg * ho * ad, rpg * ao * hd


def play_schedule(rng, schedule, s: dict) -> list[Game]:
    """Every scheduled game, played. schedule: ScheduledGame-like objects."""
    games = []
    for g in schedule:
        hm, am = game_means(s, g.home_team_id, g.away_team_id)
        away, home = play_game(rng, hm, am)
        games.append(
            Game(
                id=g.id,
                game_date=str(g.game_date),
                home_team_id=g.home_team_id,
                away_team_id=g.away_team_id,
                away_innings=away,
                home_innings=home,
                series_id=getattr(g, "series_id", None),
            )
        )
    return games


def add_hits_and_errors(rng, games: list[Game], team_hits: dict[str, int]) -> None:
    """Hits and errors for each team in each game: hits follow runs, then
    each team's are scaled to the hits its players' lines add up to."""
    a, b = P["hits_from_runs"]
    sd = P["hits_noise_sd"]
    raw: dict[str, list[tuple[Game, str, float]]] = {}
    for g in games:
        for side in ("home", "away"):
            tid = getattr(g, f"{side}_team_id")
            runs = getattr(g, f"{side}_score")
            h = max(float(runs) * 0.6, a * runs + b + rng.normal(0, sd), 0.0)
            raw.setdefault(tid, []).append((g, side, h))
            setattr(g, f"{side}_errors", int(rng.poisson(P["errors_per_game"])))
    for tid, rows in raw.items():
        target = team_hits.get(tid)
        if target is None:
            target = int(round(sum(h for _, _, h in rows)))
        split = _split(target, [h for _, _, h in rows])
        for (g, side, _), h in zip(rows, split):
            setattr(g, f"{side}_hits", h)


# ── Finishing the lines ───────────────────────────────────────────────────────


def team_records(games: list[Game]) -> dict[str, dict]:
    rec: dict[str, dict] = {}
    for g in games:
        for side, other in (("home", "away"), ("away", "home")):
            tid = getattr(g, f"{side}_team_id")
            r = rec.setdefault(tid, {"w": 0, "l": 0, "rs": 0, "ra": 0})
            r["rs"] += getattr(g, f"{side}_score")
            r["ra"] += getattr(g, f"{other}_score")
            if g.winner_id == tid:
                r["w"] += 1
            else:
                r["l"] += 1
    return rec


def finish_lines(rng, ts: TeamSeason, record: dict) -> None:
    """Scale runs, RBI and runs allowed to the team's games, and hand out
    wins, losses and saves."""
    bats = ts.batting
    runs = _split(record["rs"], [ln.stats.pop("_runs") for ln in bats])
    rbi_total = int(round(record["rs"] * P.get("rbi_per_run", 0.95)))
    rbis = _split(rbi_total, [ln.stats.pop("_rbi") for ln in bats])
    for ln, r, b in zip(bats, runs, rbis):
        ln.stats["bat_runs"] = r
        ln.stats["bat_rbi"] = b

    pits = ts.pitching
    # Runs allowed follow the events allowed, plus sequencing luck (who was
    # on base when the hits came), which gives ERAs the engine's spread.
    allowed = _split(
        record["ra"],
        [max(0.01, ln.exp_runs) * _jitter(rng, 1.0, SEQUENCING_SD) for ln in pits],
    )
    for ln, r in zip(pits, allowed):
        ln.stats["pitch_runs"] = r
        ln.stats["pitch_earned_runs"] = int(rng.binomial(r, P["earned_run_share"]))

    starters = [ln for ln in pits if ln.slot == "sp"]
    relievers = [ln for ln in pits if ln.slot == "rp"]

    team_rpo = record["ra"] / max(1, sum(ln.stats["pitch_outs"] for ln in pits))

    def quality(ln):  # fewer runs per out than his team pitches into more wins
        rpo = ln.stats["pitch_runs"] / max(1, ln.stats["pitch_outs"])
        return min(4.0, max(0.25, (team_rpo / max(rpo, 0.02)) ** DECISION_POWER))

    sp_w = int(round(record["w"] * P["starter_win_share"])) if starters else 0
    sp_l = int(round(record["l"] * P["starter_loss_share"])) if starters else 0
    if not relievers:
        sp_w, sp_l = record["w"], record["l"]
    w_sp = _split(
        sp_w, [ln.stats["pitch_games_started"] * quality(ln) for ln in starters]
    )
    l_sp = _split(
        sp_l, [ln.stats["pitch_games_started"] / quality(ln) for ln in starters]
    )
    w_rp = _split(
        record["w"] - sp_w, [ln.stats["pitch_outs"] * quality(ln) for ln in relievers]
    )
    l_rp = _split(
        record["l"] - sp_l, [ln.stats["pitch_outs"] / quality(ln) for ln in relievers]
    )
    for ln, w, l in zip(starters, w_sp, l_sp):
        ln.stats["pitch_wins"], ln.stats["pitch_losses"] = w, l
        ln.stats["pitch_saves"] = 0
    for ln, w, l in zip(relievers, w_rp, l_rp):
        ln.stats["pitch_wins"], ln.stats["pitch_losses"] = w, l
    # Saves: the closer (best reliever) gets most, in proportion to wins
    sv_table = P["saves_by_rank"]
    for k, ln in enumerate(relievers):
        sv = sv_table[k] * record["w"] / 81 if k < len(sv_table) else 0
        ln.stats["pitch_saves"] = (
            int(max(0, round(_jitter(rng, sv, 0.15)))) if sv else 0
        )


# ── Playoffs ──────────────────────────────────────────────────────────────────

HOME_MAP_BO5 = [True, True, False, False, True]
HOME_MAP_BO7 = [True, True, False, False, False, True, True]
ROUND_ONE = [
    ("3v6", 3, 6, [0, 2, 4, 6, 8]),
    ("4v5", 4, 5, [0, 2, 4, 6, 8]),
    ("1v8", 1, 8, [1, 3, 5, 7, 9]),
    ("2v7", 2, 7, [1, 3, 5, 7, 9]),
]
SEMI_OFFSETS = {
    "[2,7]v[3,6]": [10, 12, 14, 16, 18, 20, 22],
    "[1,8]v[4,5]": [11, 13, 15, 17, 19, 21, 23],
}
FINAL_OFFSETS = [25, 26, 28, 29, 30, 32, 33]


def play_series(
    rng, s, series_id, high, low, home_map, start, offsets
) -> tuple[str, list[Game]]:
    """Games until someone wins the series. Returns (winner, games)."""
    import datetime as _dt

    need = len(home_map) // 2 + 1
    wins = {high: 0, low: 0}
    games = []
    for i, (high_home, off) in enumerate(zip(home_map, offsets), start=1):
        home, away = (high, low) if high_home else (low, high)
        hm, am = game_means(s, home, away)
        a_inn, h_inn = play_game(rng, hm, am)
        g = Game(
            id=f"{series_id}_g{i}",
            game_date=(start + _dt.timedelta(days=off)).isoformat(),
            home_team_id=home,
            away_team_id=away,
            away_innings=a_inn,
            home_innings=h_inn,
            series_id=series_id,
        )
        games.append(g)
        wins[g.winner_id] += 1
        if wins[g.winner_id] == need:
            return g.winner_id, games
    raise AssertionError("series ended without a winner")


def play_playoffs(
    rng, s: dict, season_id: str, seeds: list[str], start
) -> tuple[list[tuple[str, str]], list[Game]]:
    """The bracket, as the real playoffs build it (setup_playoffs.py and
    sim_playoff.py): seeds is the top eight, best first. Returns
    ([(series_id, name)], games)."""
    series, games = [], []
    seed_of = {tid: i for i, tid in enumerate(seeds, start=1)}
    winners = {}
    for name, hi, lo, offsets in ROUND_ONE:
        sid = f"{season_id}_{name}"
        w, gs = play_series(
            rng, s, sid, seeds[hi - 1], seeds[lo - 1], HOME_MAP_BO5, start, offsets
        )
        winners[name] = w
        series.append((sid, name))
        games += gs
    semis = {}
    for name, a, b in (("[1,8]v[4,5]", "1v8", "4v5"), ("[2,7]v[3,6]", "2v7", "3v6")):
        ta, tb = winners[a], winners[b]
        high, low = (ta, tb) if seed_of[ta] < seed_of[tb] else (tb, ta)
        sid = f"{season_id}_{name}"
        w, gs = play_series(
            rng, s, sid, high, low, HOME_MAP_BO7, start, SEMI_OFFSETS[name]
        )
        semis[name] = w
        series.append((sid, name))
        games += gs
    ta, tb = semis["[1,8]v[4,5]"], semis["[2,7]v[3,6]"]
    high, low = (ta, tb) if seed_of[ta] < seed_of[tb] else (tb, ta)
    sid = f"{season_id}_Finals"
    _, gs = play_series(rng, s, sid, high, low, HOME_MAP_BO7, start, FINAL_OFFSETS)
    series.append((sid, "Finals"))
    games += gs
    return series, games
