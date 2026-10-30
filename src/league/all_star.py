# src/league/all_star.py
"""
All-Star voting (plans/all-star-game.md). The pure part: when the ballot is
open, how a GM scores the candidates, what a ballot looks like and how the
votes become the 64-player pool. src/api/services/all_star.py runs it
against the database.

The ballot. Every GM, person or AI, picks a 1st and a 2nd choice at each
fielding position, one DH and nine pitchers: 26 votes. A 1st choice is worth
2 points, everything else 1. Each player is on the ballot at one position
only, the one he has started at most this season, so the pool can't fill up
with center fielders.

The pool. A 32-man All-Star team is 9 starters (with a DH), 9 pitchers, 8
backups and 6 extras, so the pool is two of those:

    the top 4 at each of the 8 fielding positions     32
    the top 2 DHs                                       2
    the top 18 pitchers                                18
    wildcards: the most points left, any position      12

Ties at a position's cut line all get in, and each extra one takes a
wildcard spot. Players nobody voted for are ordered by the stat score, so a
league whose GMs all vote alike still fills the pool.

The voting window. The All-Star break is the one gap in the regular season
calendar (src/league/schedule.py). The ballot opens VOTING_DAYS days before
it and closes after the last games before it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, pstdev

FIELD_SLOTS = ("c", "1b", "2b", "3b", "ss", "lf", "cf", "rf")
SLOTS = FIELD_SLOTS + ("dh", "p")
SLOT_LABELS = {
    "c": "Catcher",
    "1b": "First base",
    "2b": "Second base",
    "3b": "Third base",
    "ss": "Shortstop",
    "lf": "Left field",
    "cf": "Center field",
    "rf": "Right field",
    "dh": "Designated hitter",
    "p": "Pitchers",
}

# Votes per slot on a ballot, and players per slot in the pool.
BALLOT = {**dict.fromkeys(FIELD_SLOTS, 2), "dh": 1, "p": 9}
QUOTA = {**dict.fromkeys(FIELD_SLOTS, 4), "dh": 2, "p": 18}
POOL_SIZE = 64

# The ballot is open for this many days of the calendar before the break.
VOTING_DAYS = 14
# A gap between game days at least this long is the break.
MIN_BREAK_GAP = 3

# Enough playing time to be on the ballot, per game the league has played:
# a hitter's starts and a pitcher's outs.
MIN_STARTS_PER_GAME = 0.25
MIN_OUTS_PER_GAME = 1.0

# How much an AI GM favors his own players at loyalty 100, in standard
# deviations of score, and how much his ballot wobbles.
LOYALTY_BOOST = 1.5
NOISE = 0.3


def points(slot: str, pick: int) -> int:
    """A 1st choice at a fielding position is worth 2, every other vote 1."""
    return 2 if slot in FIELD_SLOTS and pick == 1 else 1


# ── The calendar ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Window:
    opens: str  # first game day the ballot is open
    closes: str  # last game day before the break; voting ends after its games
    resumes: str  # first game day after the break


def window(game_dates: list[str]) -> Window | None:
    """The voting window from a season's regular season game dates (ISO,
    any order), or None if the season has no break."""
    days = sorted({date.fromisoformat(d) for d in game_dates})
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    if not gaps or max(gaps) < MIN_BREAK_GAP:
        return None
    i = gaps.index(max(gaps))
    closes, resumes = days[i], days[i + 1]
    opens = closes - timedelta(days=VOTING_DAYS - 1)
    return Window(opens.isoformat(), closes.isoformat(), resumes.isoformat())


# ── Who's on the ballot ──────────────────────────────────────────────────────


def on_ballot(players: list[dict], games: int) -> list[dict]:
    """The players on the ballot, each with his slot and glove (his defense
    rating there, 0 at DH), from AllStarRepository.candidates(). games is
    how many games a team has played. A player who has started more games
    in the lineup than he has pitched in is a hitter at the position he has
    started at most; anyone else who has pitched is a pitcher. Either way he
    needs enough playing time: MIN_STARTS_PER_GAME starts or
    MIN_OUTS_PER_GAME outs per game."""
    out = []
    for c in players:
        pos = c["start_position"]
        if pos in FIELD_SLOTS + ("dh",) and c["starts"] > c["pitch_games_played"]:
            if c["starts"] < MIN_STARTS_PER_GAME * games:
                continue
            slot, glove = pos, c["ratings"].get(pos, 0) if pos != "dh" else 0
        elif c["pitch_outs"] > 0:
            if c["pitch_outs"] < MIN_OUTS_PER_GAME * games:
                continue
            slot, glove = "p", 0
        else:
            continue
        out.append({**c, "slot": slot, "glove": glove})
    return out


# ── Scoring ──────────────────────────────────────────────────────────────────


def _z(values: list[float]) -> list[float]:
    if not values:
        return []
    sd = pstdev(values)
    if sd == 0:
        return [0.0] * len(values)
    m = mean(values)
    return [(v - m) / sd for v in values]


def _set_z(cands: list[dict], key: str, values: list[float]) -> None:
    for c, z in zip(cands, _z(values)):
        c["z"][key] = z


def _woba(c: dict) -> tuple[float, int]:
    pa = c["bat_ab"] + c["bat_walks"] + c["bat_hbp"] + c["bat_sac_flys"]
    if not pa:
        return 0.0, 0
    singles = c["bat_hits"] - c["bat_doubles"] - c["bat_triples"] - c["bat_home_runs"]
    num = (
        0.69 * c["bat_walks"]
        + 0.72 * c["bat_hbp"]
        + 0.89 * singles
        + 1.27 * c["bat_doubles"]
        + 1.62 * c["bat_triples"]
        + 2.10 * c["bat_home_runs"]
    )
    return num / pa, pa


def _fip(c: dict) -> float:
    outs = c["pitch_outs"]
    if not outs:
        return 0.0
    raw = (
        13 * c["pitch_home_runs"]
        + 3 * (c["pitch_walks"] + c["pitch_hit_batters"])
        - 2 * c["pitch_strike_outs"]
    )
    return raw / (outs / 3)


def add_features(cands: list[dict]) -> list[dict]:
    """Give each candidate c["z"]: the things a GM weighs, each as a z-score
    among the hitters or among the pitchers.

      bat     batting runs above average from wOBA (modern), pitchers: runs
              saved by FIP
      trad    AVG, HR and RBI (old school), pitchers: W, SV, K and ERA
      talent  the scouts' rating: offense, or the better of SP and RP
      glove   the defense rating at his ballot position, among that position
      speed   stolen bases and the speed skill
      youth   younger is higher
    """
    for c in cands:
        c["z"] = {}
    hitters = [c for c in cands if c["slot"] != "p"]
    pitchers = [c for c in cands if c["slot"] == "p"]

    if hitters:
        wobas = [_woba(c) for c in hitters]
        lg = sum(w * pa for w, pa in wobas) / max(1, sum(pa for _, pa in wobas))
        _set_z(hitters, "bat", [(w - lg) / 1.2 * pa for w, pa in wobas])
        avg = _z([c["bat_hits"] / c["bat_ab"] if c["bat_ab"] else 0 for c in hitters])
        hr = _z([c["bat_home_runs"] for c in hitters])
        rbi = _z([c["bat_rbi"] for c in hitters])
        for c, a, h, r in zip(hitters, avg, hr, rbi):
            c["z"]["trad"] = (a + h + r) / 3
        _set_z(hitters, "talent", [c["offense"] for c in hitters])
        sb = _z([c["bat_stolen_bases"] for c in hitters])
        spd = _z([c["speed"] for c in hitters])
        for c, s, p in zip(hitters, sb, spd):
            c["z"]["speed"] = (s + p) / 2
        _set_z(hitters, "youth", [-c["age"] for c in hitters])
        for slot in FIELD_SLOTS + ("dh",):
            at = [c for c in hitters if c["slot"] == slot]
            _set_z(at, "glove", [c["glove"] for c in at])

    if pitchers:
        fips = [_fip(c) for c in pitchers]
        outs = [c["pitch_outs"] for c in pitchers]
        lg = sum(f * o for f, o in zip(fips, outs)) / max(1, sum(outs))
        _set_z(pitchers, "bat", [(lg - f) * o / 27 for f, o in zip(fips, outs)])
        w = _z([c["pitch_wins"] for c in pitchers])
        sv = _z([c["pitch_saves"] for c in pitchers])
        k = _z([c["pitch_strike_outs"] for c in pitchers])
        era = _z(
            [
                -27 * c["pitch_earned_runs"] / c["pitch_outs"] if c["pitch_outs"] else 0
                for c in pitchers
            ]
        )
        for c, a, b, d, e in zip(pitchers, w, sv, k, era):
            c["z"]["trad"] = (a + b + d + e) / 4
        _set_z(pitchers, "talent", [c["talent"] for c in pitchers])
        _set_z(pitchers, "youth", [-c["age"] for c in pitchers])
    return cands


def score(c: dict, dials: dict | None = None) -> float:
    """How good a GM with these persona dials (src/league/personas.py)
    thinks a candidate is. No dials: neutral, the stat-based score every
    ballot starts from.

    Stats always count for at least half: it's an All-Star vote. The rest
    is the scouts' rating, more of it for a GM who trusts the scouts.
    Analytics picks modern stats over old school ones. A glove-first GM
    gives defense more weight, a small-ball GM speed, and a GM who plays
    the kids youth.
    """
    d = {**NEUTRAL_DIALS, **(dials or {})}
    z = c["z"]
    stats_w = 0.5 + 0.5 * d["stats_vs_scouting"] / 100
    modern = d["analytics"] / 100
    s = stats_w * (modern * z.get("bat", 0) + (1 - modern) * z.get("trad", 0))
    s += (1 - stats_w) * z.get("talent", 0)
    if c["slot"] != "p":
        s += (0.1 + 0.4 * (100 - d["offense_defense"]) / 100) * z.get("glove", 0)
        s += (d["small_ball"] - 50) / 100 * z.get("speed", 0)
    s += (d["youth"] - 50) / 100 * z.get("youth", 0)
    return s


NEUTRAL_DIALS = {
    "stats_vs_scouting": 50,
    "analytics": 50,
    "offense_defense": 50,
    "small_ball": 50,
    "youth": 50,
    "loyalty": 50,
}


# ── Ballots ──────────────────────────────────────────────────────────────────


def ballot(
    cands: list[dict],
    dials: dict | None = None,
    team_id: str | None = None,
    rng: random.Random | None = None,
) -> dict[str, list[str]]:
    """A ballot, {slot: [player id in pick order]}: the best at each slot by
    score(). With team_id, a loyal GM boosts his own players; with rng, the
    scores wobble a little, so AI GMs don't all vote alike."""
    loyalty = (dials or {}).get("loyalty", 50)
    ranked = []
    for c in cands:
        s = score(c, dials)
        if team_id and c["team_id"] == team_id:
            s += LOYALTY_BOOST * loyalty / 100
        if rng:
            s += rng.gauss(0, NOISE)
        ranked.append((s, c))
    ranked.sort(key=lambda sc: -sc[0])
    out = {}
    for slot in SLOTS:
        at = [c["player_id"] for _, c in ranked if c["slot"] == slot]
        out[slot] = at[: BALLOT[slot]]
    return out


def clean_ballot(raw: dict[str, list], cands: list[dict]) -> dict[str, list[str]]:
    """A ballot as a GM sent it, keeping only candidates at the slot they're
    on the ballot at, no one twice and no more picks than the slot has. A
    blank pick stays blank (None)."""
    slot_of = {c["player_id"]: c["slot"] for c in cands}
    out = {}
    for slot in SLOTS:
        picks, seen = [], set()
        for pid in list(raw.get(slot) or [])[: BALLOT[slot]]:
            ok = pid and slot_of.get(pid) == slot and pid not in seen
            picks.append(pid if ok else None)
            if ok:
                seen.add(pid)
        out[slot] = picks
    return out


def tally(ballots) -> dict[str, int]:
    """{player id: points} over these ballots."""
    total: dict[str, int] = {}
    for b in ballots:
        for slot, picks in b.items():
            for pick, pid in enumerate(picks, 1):
                if pid:
                    total[pid] = total.get(pid, 0) + points(slot, pick)
    return total


# ── The pool ─────────────────────────────────────────────────────────────────


def _take(ranked: list[dict], pts: dict[str, int], n: int) -> list[dict]:
    """The first n of ranked (best first), plus anyone with as many points
    as the n-th. Only a tie on points counts: players nobody voted for are
    taken in order."""
    if len(ranked) <= n:
        return list(ranked)
    cut = pts.get(ranked[n - 1]["player_id"], 0)
    taken = ranked[:n]
    if cut > 0:
        taken += [c for c in ranked[n:] if pts.get(c["player_id"], 0) == cut]
    return taken


def select_pool(cands: list[dict], pts: dict[str, int]) -> list[dict]:
    """The All-Stars: [{player_id, team_id, slot, points, wildcard}], by
    slot quota then wildcards, POOL_SIZE in all when there are enough
    candidates. Order within points is the neutral stat score, which also
    settles a tie for the last wildcard spot. Ties at the cut lines that
    would overflow the pool lose their lowest-scoring extras."""
    neutral = {c["player_id"]: score(c) for c in cands}

    def rank(group):
        return sorted(
            group,
            key=lambda c: (-pts.get(c["player_id"], 0), -neutral[c["player_id"]]),
        )

    chosen: list[dict] = []
    extras: list[dict] = []
    for slot in SLOTS:
        ranked = rank([c for c in cands if c["slot"] == slot])
        taken = _take(ranked, pts, QUOTA[slot])
        chosen += taken[: QUOTA[slot]]
        extras += taken[QUOTA[slot] :]
    room = POOL_SIZE - len(chosen)
    extras = rank(extras)
    wild = extras[:room]
    room -= len(wild)
    picked = {c["player_id"] for c in chosen + wild}
    rest = rank([c for c in cands if c["player_id"] not in picked])
    wild += rest[: max(0, room)]

    def row(c, wildcard):
        return {
            "player_id": c["player_id"],
            "team_id": c["team_id"],
            "slot": c["slot"],
            "points": pts.get(c["player_id"], 0),
            "wildcard": wildcard,
        }

    return [row(c, False) for c in chosen] + [row(c, True) for c in wild]
