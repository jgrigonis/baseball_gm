# src/api/view_models/play_by_play.py
"""
Words the game panel's play-by-play: the plays src/game/play_log.py kept
for a game, grouped by half-inning, with the game log's substitutions and
pitching changes put between the plays they came between.
"""

from __future__ import annotations

import re

# Engine notes left on game log lines for debugging, like the
# "— fatigue=tired" on a pitching change. Only admins see them.
_DEBUG_NOTE = re.compile(r"\s*[—(,;]?\s*\b[a-z_]+=[\w.\-]+\)?")


def strip_debug(text: str | None) -> str | None:
    """A game log line without its key=value debug notes."""
    if not text:
        return text
    cleaned = _DEBUG_NOTE.sub("", text).strip()
    return cleaned.rstrip(" —,;") or text


# Where a ball went: "flies out to center"
_TO = {
    "p": "pitcher",
    "c": "catcher",
    "1b": "first",
    "2b": "second",
    "3b": "third",
    "ss": "short",
    "lf": "left",
    "cf": "center",
    "rf": "right",
}
# Who made an error: "an error by the shortstop"
_WHO = {
    "p": "pitcher",
    "c": "catcher",
    "1b": "first baseman",
    "2b": "second baseman",
    "3b": "third baseman",
    "ss": "shortstop",
    "lf": "left fielder",
    "cf": "center fielder",
    "rf": "right fielder",
}
_BASE = {1: "first", 2: "second", 3: "third", 4: "home"}
_HITS = {"single", "double", "triple", "home_run"}
_HOMER = {1: "homers", 2: "hits a two-run homer", 3: "hits a three-run homer"}


def _to(pos) -> str:
    return _TO.get((pos or "").lower(), (pos or "").upper())


def _who(pos) -> str:
    return _WHO.get((pos or "").lower(), (pos or "").upper())


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _names(names: list[str]) -> str:
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _result(play: dict) -> str:
    """What the batter did: "flies out to center"."""
    r = play.get("r") or ""
    f = play.get("f") or [None, None]
    err = play.get("e")
    if r == "home_run":
        return _HOMER.get(len(play.get("s") or []), "hits a grand slam")
    if r in ("single", "double", "triple"):
        return r + "s"
    if r == "strikeout":
        return "strikes out"
    if r == "walk":
        return "walks"
    if r == "intentional_walk":
        return "is walked intentionally"
    if r in ("hit_by_pitch", "intentional_hit_by_pitch"):
        return "is hit by a pitch"
    if r == "catcher_interference":
        return "reaches on catcher's interference"
    if r == "fly_out":
        return f"flies out to {_to(f[0])}" if f[0] else "flies out"
    if r == "out":
        return f"fouls out to {_to(f[0])}" if f[0] else "fouls out"
    if r == "ground_out":
        if f[1]:
            return f"grounds out, {_to(f[1])} to {_to(f[0])}"
        return f"grounds out to {_to(f[0])}" if f[0] else "grounds out"
    if r == "double_play":
        return "grounds into a double play"
    if r == "triple_play":
        return "hits into a triple play"
    if r == "fielders_choice":
        return "reaches on a fielder's choice"
    if r == "sac_fly":
        return (
            f"hits a sacrifice fly to {_to(f[0])}" if f[0] else "hits a sacrifice fly"
        )
    if r == "sac_bunt":
        return "lays down a sacrifice bunt"
    if r == "throwing_error":
        return f"reaches on a throwing error by the {_who(err)}"
    if "error" in r:
        return (
            f"reaches on an error by the {_who(err)}" if err else "reaches on an error"
        )
    return r.replace("_", " ")


def _note(kind: str, name: str | None, where) -> str:
    if kind == "sb":
        return f"{name} steals {_BASE.get(where, 'a base')}."
    if kind == "cs":
        return f"{name} is caught stealing {_BASE.get(where, '')}."
    if kind == "po":
        return f"{name} is picked off {_BASE.get(where, '')}."
    if kind == "poe":
        return "The pickoff throw gets away."
    if kind == "wp":
        return "Wild pitch."
    if kind == "pb":
        return "Passed ball."
    if kind == "bk":
        return "Balk."
    if kind == "xe":
        return f"{name} takes an extra base on an error by the {_who(where)}."
    return ""


def _score(names: list[str]) -> str:
    return f"{_names(names)} {'scores' if len(names) == 1 else 'score'}"


def describe(play: dict) -> str:
    """One play in words."""
    parts = [_note(*n) for n in play.get("n") or []]
    if play.get("b"):
        line = f"{play['b']} {_result(play)}"
        scored = list(play.get("s") or [])
        if play.get("r") == "home_run" and play["b"] in scored:
            scored.remove(play["b"])
            if scored:
                line += f", {_score(scored)}"
        elif scored:
            line += f"; {_score(scored)}"
        parts.append(line + ".")
    elif play.get("s"):
        parts.append(_score(play["s"]) + ".")
    return " ".join(p for p in parts if p)


def build(plays: list[dict], events: list[dict], game: dict) -> list[dict]:
    """Half-innings in order, each {label, team_id, team, items, runs,
    hits}. An item is a play {kind: "play", text, outs, score, scored} or
    a game log line {kind: "event", event_type, team_id, text}."""
    # The pregame lineups and starters are shown above the plays.
    logged = [
        (k, e)
        for k, e in enumerate(events)
        if e["event_type"] not in ("lineup_set", "pitcher_start")
    ]
    halves: list[dict] = []
    current = None
    prev_score = [0, 0]
    li = 0
    for play in plays:
        top = bool(play["t"])
        key = (play["i"], top)
        if current is None or current["key"] != key:
            batting = "away" if top else "home"
            current = {
                "key": key,
                "label": f"{'Top' if top else 'Bottom'} {ordinal(play['i'])}",
                "team_id": game[f"{batting}_team_id"],
                "team": game[f"{batting}_mascot"],
                "items": [],
                "runs": 0,
                "hits": 0,
            }
            halves.append(current)
        while li < len(logged) and logged[li][0] < play.get("g", 0):
            e = logged[li][1]
            current["items"].append(
                {
                    "kind": "event",
                    "event_type": e["event_type"],
                    "team_id": e["team_id"],
                    "text": e["reason"],
                }
            )
            li += 1
        score = play.get("sc") or prev_score
        runs = (score[0] - prev_score[0]) + (score[1] - prev_score[1])
        prev_score = score
        current["runs"] += runs
        if play.get("r") in _HITS:
            current["hits"] += 1
        current["items"].append(
            {
                "kind": "play",
                "text": describe(play),
                "outs": play.get("o", 0),
                "score": f"{score[0]}–{score[1]}" if runs else None,
                "scored": runs > 0,
            }
        )
    for _, e in logged[li:]:
        if halves:
            halves[-1]["items"].append(
                {
                    "kind": "event",
                    "event_type": e["event_type"],
                    "team_id": e["team_id"],
                    "text": e["reason"],
                }
            )
    return halves
