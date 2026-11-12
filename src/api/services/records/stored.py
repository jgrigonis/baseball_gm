# src/api/services/records/stored.py
"""
Cards for the stored records (record_feats): single games and streaks.
Without a backstory, the league's book opens at the league marks
(defs.py floors); a club's own book never does.
"""

from __future__ import annotations

from datetime import date

from src.api.services.records import defs, feats
from src.api.services.records.core import Card, card
from src.api.services.records.news import has_backstory


def _name(f: dict) -> str:
    if f.get("first_name"):
        return f"{f['first_name']} {f['last_name']}"
    return f"{f['city']} {f['mascot']}" if f.get("city") else "?"


def _md(iso: str | None) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}"


def game_cards(conn, league_id: str, my_team_id, team_id=None) -> dict[str, list[Card]]:
    rows = feats.load(conn, league_id, "game", team_id)
    floors = not team_id and not has_backstory(conn, league_id)
    by: dict[str, list[dict]] = {}
    for f in rows:
        extra = f", {f['innings']} inn" if (f["innings"] or 9) > 9 else ""
        by.setdefault(f["stat"], []).append({
            "value": f["value"],
            "shown": str(f["value"]),
            "order": f["on_date"] or f"{f['year']:05d}",
            "player_id": f["player_id"],
            "game_id": f["game_id"] if f["source"] == "played" else None,
            "name": _name(f),
            "team": "" if team_id else f"{f['city']} {f['mascot']}",
            "detail": f"{_md(f['on_date'])}, {f['year']} vs {f['opp_city']}{extra}"
            if f.get("opp_city") else str(f["year"]),
            "is_mine": not team_id and f["team_id"] == my_team_id,
        })  # fmt: skip
    out: dict[str, list[Card]] = {"batting": [], "pitching": []}
    for s in defs.GAME_STATS:
        c = card(f"game-{s.key}", s.label, by.get(s.key, []),
                 floor=s.floor if floors else None)  # fmt: skip
        out["pitching" if s.pitching else "batting"].append(c)
    return out


def streak_cards(
    conn, league_id: str, my_team_id, team_id=None
) -> dict[str, list[Card]]:
    rows = feats.load(conn, league_id, "streak", team_id)
    floors = not team_id and not has_backstory(conn, league_id)
    by: dict[str, list[dict]] = {}
    for f in rows:
        stat = defs.STREAK_BY_KEY[f["stat"]]
        span = f"{_md(f['start_date'])}–{_md(f['on_date'])}, {f['year']}"
        by.setdefault(f["stat"], []).append({
            "value": f["value"],
            "shown": str(f["value"]),
            "order": f["on_date"] or "",
            "player_id": f["player_id"],
            "team_id": f["team_id"],
            "name": _name(f),
            "team": "" if (team_id or stat.team) else f"{f['city']} {f['mascot']}",
            "detail": span,
            "active": f["active"],
            "is_mine": not team_id and f["team_id"] == my_team_id,
        })  # fmt: skip
    out: dict[str, list[Card]] = {"players": [], "teams": []}
    for s in defs.STREAKS:
        c = card(f"streak-{s.key}", s.label, by.get(s.key, []),
                 floor=s.floor if floors else None, note=_STREAK_NOTES[s.key])  # fmt: skip
        out["teams" if s.team else "players"].append(c)
    return out


_STREAK_NOTES = {
    "hit": "Games with a hit; walks-only games don't end it",
    "hr": "Games with a home run",
    "onbase": "Games reaching on a hit, walk or hit by pitch",
    "pwin": "Wins in a row; no-decisions don't end it",
    "twin": "Regular season",
    "tloss": "Regular season",
}
