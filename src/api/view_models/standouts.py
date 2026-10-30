# src/api/view_models/standouts.py
"""
Standout performances in one game: the batting and pitching lines worth
calling out, from either team, picked from the box score alone.

Each standout names the player's best feat ("Cycle", "3 HR", "12 K") and a
short stat line. They are ranked by how rare the feat is, so the first one
is the game's best individual performance and can feed the headline.
"""

from __future__ import annotations

from src.stats import formulas

MAX_STANDOUTS = 3


def _n(row: dict, key: str) -> int:
    return row.get(key) or 0


def _batting_feats(b: dict) -> list[tuple[int, str]]:
    """(score, label) for each standout feat in one batting line."""
    h, hr, rbi = _n(b, "H"), _n(b, "HR"), _n(b, "RBI")
    doubles, triples = _n(b, "doubles"), _n(b, "triples")
    singles = h - doubles - triples - hr
    feats = []
    if singles >= 1 and doubles >= 1 and triples >= 1 and hr >= 1:
        feats.append((85, "Cycle"))
    if hr >= 3:
        feats.append((75 + hr, f"{hr} HR"))
    elif hr == 2:
        feats.append((50, "2 HR"))
    if rbi >= 5:
        feats.append((45 + rbi, f"{rbi} RBI"))
    if h >= 4:
        feats.append((40 + 5 * (h - 4), f"{h} hits"))
    return feats


def _batting_line(b: dict) -> str:
    parts = [f"{_n(b, 'H')}-for-{_n(b, 'AB')}"]
    for key, label in (("doubles", "2B"), ("triples", "3B"), ("HR", "HR")):
        n = _n(b, key)
        if n:
            parts.append(label if n == 1 else f"{n} {label}")
    if _n(b, "RBI"):
        parts.append(f"{_n(b, 'RBI')} RBI")
    if _n(b, "R"):
        parts.append(f"{_n(b, 'R')} R")
    return ", ".join(parts)


def _ip(outs: int) -> str:
    """Innings pitched, dropping a trailing ".0" (24 outs -> "8")."""
    return formulas.ip_str(outs).removesuffix(".0")


def _pitching_feats(p: dict, team_errors: int) -> list[tuple[int, str]]:
    """(score, label) for each standout feat in one pitching line."""
    outs, k = _n(p, "outs"), _n(p, "K")
    feats = []
    if _n(p, "NH"):
        perfect = not (_n(p, "BB") or _n(p, "HBP") or team_errors)
        feats.append((100, "Perfect game") if perfect else (90, "No-hitter"))
    elif _n(p, "SHO"):
        feats.append((60, "Shutout"))
    elif outs >= 24 and _n(p, "R") == 0:
        feats.append((35, f"{_ip(outs)} scoreless IP"))
    if k >= 10:
        feats.append((35 + k, f"{k} K"))
    return feats


def _pitching_line(p: dict) -> str:
    return (
        f"{formulas.ip_str(_n(p, 'outs'))} IP, {_n(p, 'H')} H, {_n(p, 'R')} R, "
        f"{_n(p, 'BB')} BB, {_n(p, 'K')} K"
    )


def standouts(
    bat_rows: list[dict],
    pit_rows: list[dict],
    errors: dict[str, int] | None = None,
    limit: int = MAX_STANDOUTS,
) -> list[dict]:
    """
    The game's standout performances, best first, at most ``limit``.

    errors is {team_id: errors}, used only to tell a perfect game from a
    no-hitter. Each standout is {"player_id", "team_id", "first_name",
    "last_name", "kind" ("bat" or "pit"), "label", "feats", "line", "score"},
    where feats lists every label the player earned and label is the best.
    """
    errors = errors or {}
    found = []
    for kind, rows in (("bat", bat_rows), ("pit", pit_rows)):
        for r in rows:
            if kind == "bat":
                feats, line = _batting_feats(r), _batting_line(r)
            else:
                feats = _pitching_feats(r, errors.get(r["team_id"], 0))
                line = _pitching_line(r)
            if not feats:
                continue
            feats.sort(reverse=True)
            found.append(
                {
                    "player_id": r.get("player_id"),
                    "team_id": r["team_id"],
                    "first_name": r.get("first_name", ""),
                    "last_name": r["last_name"],
                    "kind": kind,
                    "label": feats[0][1],
                    "feats": [label for _, label in feats],
                    "line": line,
                    # A second feat breaks ties: 2 HR and 6 RBI beats 2 HR.
                    "score": feats[0][0] + sum(s for s, _ in feats[1:]) / 100,
                }
            )
    found.sort(key=lambda s: s["score"], reverse=True)
    return found[:limit]
