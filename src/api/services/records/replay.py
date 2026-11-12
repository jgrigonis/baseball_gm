# src/api/services/records/replay.py
"""
Seeding the single-game and streak records from the backstory.

Backstory seasons have real season lines and real game scores, but no box
scores, so nobody has a best game or a hitting streak. Here each player's
season line is dealt out over his club's games, in memory: his plate
appearances become a shuffled run of outcomes split game by game, his runs,
RBI and steals follow the times he reached and hit, a pitcher's outs and
strikeouts follow his starts, and his wins and losses fall on some of his
games. Totals match his line exactly. From that we keep only what the
record book keeps (defs.py): the best games and the longest streaks, on the
real backstory dates and games. Club streaks come straight from the
backstory's games.

Nothing else is stored, and a league without a backstory gets nothing here
(its records start at the league marks instead).
"""

from __future__ import annotations

import random
from collections import defaultdict

import numpy as np

from src.api.services.records import defs, feats
from src.api.services.records.defs import Run

PITCH_START_WEIGHT = 6.0  # a start gets about six times a relief outing's outs
MAX_PA_PER_GAME = 5


def seed_league(conn, league_id: str, rng: random.Random) -> None:
    np_rng = np.random.default_rng(rng.randrange(2**32))
    seasons = conn.execute(
        """SELECT s.id, s.year FROM seasons s
           JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s AND s.is_backstory
           ORDER BY s.year""",
        (league_id,),
    ).fetchall()
    games: list[dict] = []
    streaks: list[dict] = []
    for s in seasons:
        g, st = replay_season(conn, league_id, s["id"], s["year"], np_rng)
        games += g
        streaks += st
    feats.save(conn, _keep(conn, league_id, "game", games))
    feats.save(conn, _keep(conn, league_id, "streak", streaks))


def _keep(conn, league_id: str, kind: str, cands: list[dict]) -> list[dict]:
    """The candidates that make a top five, league or club, best first so
    the cut-offs come out right."""
    keeper = feats.Keeper(conn, league_id, kind)
    stats = defs.GAME_BY_KEY if kind == "game" else defs.STREAK_BY_KEY
    out = []
    for c in sorted(cands, key=lambda c: (-c["value"], c["on_date"] or "")):
        if keeper.worth(c["stat"], c["team_id"], c["value"], stats[c["stat"]].keep):
            keeper.add(c["stat"], c["team_id"], c["value"])
            out.append(c)
    return out


def replay_season(conn, league_id, season_id, year, rng) -> tuple[list, list]:
    schedule: dict[str, list[dict]] = defaultdict(list)
    for r in conn.execute(
        """SELECT g.id, g.game_date, g.home_team_id, g.away_team_id, g.innings_played,
                  tgs.team_id, tgs.win
           FROM games g JOIN team_game_stats tgs ON tgs.game_id = g.id
           WHERE g.season_id = %s AND g.series_id IS NULL AND g.completed = 1
           ORDER BY g.game_date, g.id""",
        (season_id,),
    ).fetchall():
        opp = (
            r["away_team_id"]
            if r["team_id"] == r["home_team_id"]
            else r["home_team_id"]
        )
        schedule[r["team_id"]].append(
            {"id": r["id"], "date": r["game_date"], "opp": opp,
             "innings": r["innings_played"], "win": r["win"]}
        )  # fmt: skip
    lines = conn.execute(
        """SELECT * FROM player_season_stats
           WHERE season_id = %s AND NOT is_postseason
           ORDER BY player_id, team_id""",
        (season_id,),
    ).fetchall()
    base = {"league_id": league_id, "season_id": season_id, "year": year,
            "source": "backstory", "active": False}  # fmt: skip
    games: list[dict] = []
    streaks: list[dict] = []
    for ln in lines:
        team = ln["team_id"]
        sched = schedule.get(team) or []
        if not sched:
            continue
        if (ln["bat_games_played"] or 0) > 0:
            per_game = _hitter_games(ln, len(sched), rng)
            _collect(per_game, ln, team, sched, base, games, streaks, pitcher=False)
        if (ln["pitch_games_played"] or 0) > 0:
            per_game = _pitcher_games(ln, len(sched), rng)
            _collect(per_game, ln, team, sched, base, games, streaks, pitcher=True)
    for team, sched in schedule.items():
        for stat in defs.TEAM_STREAKS:
            run = Run()
            for g in sched:
                won = defs.EXTEND if g["win"] else defs.BREAK
                outcome = won if stat.key == "twin" else -won
                ended = run.feed(outcome, g["date"], g["id"], team)
                if ended:
                    _streak(streaks, base, stat, team, None, ended)
            if run.length:
                _streak(streaks, base, stat, team, None, run)
    return games, streaks


# ── Dealing a season line into games ──────────────────────────────────────────


def _n(ln, col) -> int:
    return int(ln[col] or 0)


def _games_for(count: int, n: int, rng) -> np.ndarray:
    """Which of the club's n games he played (indices, in order)."""
    count = max(1, min(count, n))
    return np.sort(rng.choice(n, size=count, replace=False))


def _deal(rng, total: int, weights: np.ndarray) -> np.ndarray:
    """``total`` events spread over games in proportion to ``weights``."""
    if total <= 0 or len(weights) == 0:
        return np.zeros(len(weights), dtype=int)
    w = weights.astype(float)
    if w.sum() <= 0:
        w = np.ones(len(weights))
    return rng.multinomial(total, w / w.sum())


def _hitter_games(ln, n_games: int, rng) -> dict:
    """{"idx": game indices, stat: per-game counts...} for a hitter."""
    pa_total = sum(
        _n(ln, c) for c in ("bat_ab", "bat_walks", "bat_hbp", "bat_sac_flys")
    )
    # At most about five trips to the plate a game.
    played = max(_n(ln, "bat_games_played"), -(-pa_total // MAX_PA_PER_GAME))
    idx = _games_for(played, n_games, rng)
    g = len(idx)
    h, d, t, hr = (_n(ln, c) for c in ("bat_hits", "bat_doubles", "bat_triples",
                                        "bat_home_runs"))  # fmt: skip
    bb, hbp, sf, k = (_n(ln, c) for c in ("bat_walks", "bat_hbp", "bat_sac_flys",
                                           "bat_strike_outs"))  # fmt: skip
    ab = _n(ln, "bat_ab")
    singles = max(0, h - d - t - hr)
    outs = max(0, ab - h - k)
    # A plate appearance code per outcome, shuffled, then cut into games.
    codes = np.repeat(
        np.arange(8), [singles, d, t, hr, bb, hbp, sf, k + outs]
    )  # 0=1B 1=2B 2=3B 3=HR 4=BB 5=HBP 6=SF 7=out
    rng.shuffle(codes)
    pa_per = _even(rng, len(codes), g)
    cuts = np.cumsum(pa_per)[:-1]
    per = np.split(codes, cuts)
    cnt = (
        np.array([np.bincount(p, minlength=8) for p in per]) if g else np.zeros((0, 8))
    )
    out = {
        "idx": idx,
        "1B": cnt[:, 0], "2B": cnt[:, 1], "3B": cnt[:, 2], "HR": cnt[:, 3],
        "BB": cnt[:, 4], "HBP": cnt[:, 5], "SF": cnt[:, 6],
    }  # fmt: skip
    out["H"] = out["1B"] + out["2B"] + out["3B"] + out["HR"]
    # Strikeouts among the outs: each out a strikeout with his rate.
    outs_per = cnt[:, 7]
    out["K"] = _deal_capped(rng, k, outs_per)
    out["AB"] = out["H"] + outs_per
    on_base = out["1B"] + out["2B"] + out["3B"] + out["BB"] + out["HBP"]
    # A run needs a time on base; a hit drives in at most three others, a
    # sacrifice fly one; a steal needs a runner (two at most from one trip).
    out["R"] = out["HR"] + _deal_capped(rng, max(0, _n(ln, "bat_runs") - hr), on_base)
    out["RBI"] = out["HR"] + _deal_capped(
        rng, max(0, _n(ln, "bat_rbi") - hr), 3 * out["H"] + out["SF"]
    )
    out["SB"] = _deal_capped(
        rng, _n(ln, "bat_stolen_bases"), 2 * (out["1B"] + out["BB"] + out["HBP"])
    )
    return out


def _deal_capped(rng, total: int, caps: np.ndarray, weights=None) -> np.ndarray:
    """``total`` events over games, no game past its cap (each of a game's
    slots equally likely, or by the game's weight)."""
    out = np.zeros(len(caps), dtype=int)
    caps = np.asarray(caps, dtype=int)
    if total <= 0:
        return out
    slots = np.repeat(np.arange(len(caps)), caps)
    if len(slots) == 0:
        return out
    p = None
    if weights is not None:
        p = np.asarray(weights, dtype=float)[slots]
        p = p / p.sum()
    pick = rng.choice(len(slots), size=min(total, len(slots)), replace=False, p=p)
    np.add.at(out, slots[pick], 1)
    return out


def _even(rng, total: int, g: int) -> np.ndarray:
    """``total`` plate appearances over g games as evenly as they go."""
    base, extra = divmod(total, g)
    out = np.full(g, base, dtype=int)
    if extra:
        out[rng.choice(g, size=extra, replace=False)] += 1
    return out


def _pitcher_games(ln, n_games: int, rng) -> dict:
    idx = _games_for(_n(ln, "pitch_games_played"), n_games, rng)
    g = len(idx)
    starts = np.zeros(g, dtype=bool)
    gs = min(_n(ln, "pitch_games_started"), g)
    if gs:
        starts[rng.choice(g, size=gs, replace=False)] = True
    weight = np.where(starts, PITCH_START_WEIGHT, 1.0)
    # A start goes nine innings at most, a relief outing three, spread
    # by weight.
    caps = np.where(starts, 27, 9)
    total = _n(ln, "pitch_outs")
    while caps.sum() < total:
        caps = caps + 3
    outs = _deal_capped(rng, total, caps, weight)
    ks = _deal_capped(rng, _n(ln, "pitch_strike_outs"), outs)
    w, lo = _n(ln, "pitch_wins"), _n(ln, "pitch_losses")
    dec = np.zeros(g, dtype=int)  # 1 win, -1 loss
    if w + lo:
        p = weight * (outs > 0) + 0.01
        chosen = rng.choice(g, size=min(w + lo, g), replace=False, p=p / p.sum())
        labels = np.array([1] * w + [-1] * lo)[: len(chosen)]
        rng.shuffle(labels)
        dec[chosen] = labels
    return {"idx": idx, "PK": ks, "dec": dec}


# ── Keeping what counts ───────────────────────────────────────────────────────


def _collect(per, ln, team, sched, base, games, streaks, pitcher: bool) -> None:
    pid = ln["player_id"]
    idx = per["idx"]
    stats = [s for s in defs.GAME_STATS if s.pitching == pitcher]
    for s in stats:
        vals = per[s.key]
        for j in np.nonzero(vals >= s.keep)[0]:
            g = sched[int(idx[j])]
            games.append({
                **base, "kind": "game", "stat": s.key,
                "key": f"g:{s.key}:{pid}:{g['id']}", "value": int(vals[j]),
                "subject": pid, "player_id": pid, "team_id": team, "game_id": g["id"],
                "on_date": g["date"], "opp_team_id": g["opp"], "innings": g["innings"],
            })  # fmt: skip
    by = defs.STREAK_BY_KEY
    if pitcher:
        run = Run()
        for j, dec in enumerate(per["dec"]):
            outcome = defs.pitcher_outcome(dec == 1, dec == -1)
            if outcome == defs.SKIP:
                continue
            g = sched[int(idx[j])]
            ended = run.feed(outcome, g["date"], g["id"], team)
            if ended:
                _streak(streaks, base, by["pwin"], pid, pid, ended)
        if run.length:
            _streak(streaks, base, by["pwin"], pid, pid, run)
        return
    runs = {s.key: Run() for s in defs.PLAYER_STREAKS if s.key != "pwin"}
    for j in range(len(idx)):
        g = sched[int(idx[j])]
        game = {"ab": int(per["AB"][j]), "h": int(per["H"][j]), "hr": int(per["HR"][j]),
                "bb": int(per["BB"][j]), "hbp": int(per["HBP"][j]), "sf": int(per["SF"][j])}  # fmt: skip
        for key, outcome in defs.hitter_outcomes(game).items():
            ended = runs[key].feed(outcome, g["date"], g["id"], team)
            if ended:
                _streak(streaks, base, by[key], pid, pid, ended)
    for key, run in runs.items():
        if run.length:
            _streak(streaks, base, by[key], pid, pid, run)


def _streak(out, base, stat, subject, player_id, run: Run) -> None:
    if run.length < stat.keep:
        return
    out.append({
        **base, "kind": "streak", "stat": stat.key,
        "key": f"s:{stat.key}:{subject}:{base['season_id']}:{run.start}",
        "value": run.length, "subject": subject, "player_id": player_id,
        "team_id": run.team_id, "game_id": run.last_game, "on_date": run.last,
        "start_date": run.start,
    })  # fmt: skip
