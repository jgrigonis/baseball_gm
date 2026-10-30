# src/api/view_models/box_score.py
"""
Box score row order for the game panel.

Batters are listed in batting order, with each substitute right under the
player he replaced. Pitchers are listed in the order they entered the game.
Both orders come from the game's event log (lineup_set, substitution,
pitcher_start, pitching_change, closer_called). A row the log doesn't
mention, such as a game played before the log existed, keeps its place
after the ordered rows.
"""

from __future__ import annotations

_PITCHER_ENTRIES = ("pitcher_start", "pitching_change", "closer_called")


def batting_order(events: list[dict], team_id: str) -> list[str]:
    """Player ids for a team in batting order, subs under the man they replaced."""
    slots: list[list[str]] = []
    slot_of: dict[str, int] = {}
    for e in events:
        if e.get("team_id") != team_id:
            continue
        if e["event_type"] == "lineup_set" and not slots:
            lineup = sorted(
                e.get("detail_parsed") or [], key=lambda s: s["batting_order"]
            )
            for s in lineup:
                slot_of[s["player_id"]] = len(slots)
                slots.append([s["player_id"]])
        elif e["event_type"] == "substitution":
            i = slot_of.get(e.get("player_id_2"))
            if i is not None and e.get("player_id") not in slot_of:
                slot_of[e["player_id"]] = i
                slots[i].append(e["player_id"])
    return [pid for slot in slots for pid in slot]


def pitching_order(events: list[dict], team_id: str) -> list[str]:
    """Player ids for a team's pitchers in the order they entered the game."""
    order: list[str] = []
    for e in events:
        if e.get("team_id") != team_id or e["event_type"] not in _PITCHER_ENTRIES:
            continue
        pid = e.get("player_id")
        if pid and pid not in order:
            order.append(pid)
    return order


def in_order(rows: list[dict], order: list[str]) -> list[dict]:
    """Rows sorted by their player's place in order; unknown players go last."""
    rank = {pid: i for i, pid in enumerate(order)}
    return sorted(rows, key=lambda r: rank.get(r["player_id"], len(rank)))
