# src/api/services/records/held.py
"""
The league records a player holds, for the badge on his player panel and
career page ("📖 League record: Home runs in a season, 52"). Working out
the whole book takes a moment, so the answer is kept per league until
another game is played.
"""

from __future__ import annotations

import logging

from src.api.services.records import current_season, seasons, stored

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[tuple, dict[str, list[str]]]] = {}
_CACHE_SIZE = 16


def _version(conn, league_id: str) -> tuple:
    row = conn.execute(
        """SELECT COUNT(*) AS n, MAX(g.game_date) AS d FROM games g
           JOIN league_seasons ls ON ls.season_id = g.season_id
           WHERE ls.league_id = %s AND g.completed = 1""",
        (league_id,),
    ).fetchone()
    feats = conn.execute(
        "SELECT COUNT(*) AS n FROM record_feats WHERE league_id = %s", (league_id,)
    ).fetchone()
    return (row["n"], row["d"], feats["n"])


def holders(conn, league_id: str) -> dict[str, list[str]]:
    """{player_id: ["Home runs in a season (52)", ...]} for every player
    holding (or sharing) a league record."""
    version = _version(conn, league_id)
    hit = _CACHE.get(league_id)
    if hit and hit[0] == version:
        return hit[1]
    out: dict[str, list[str]] = {}

    def note(cards, scope: str):
        for c in cards:
            if c.mark or c.listing:
                continue
            for h in c.holders:
                if h.get("player_id"):
                    out.setdefault(h["player_id"], []).append(
                        f"{c.label} {scope} ({h['shown']})"
                    )

    rows = seasons.load(conn, league_id)
    s = seasons.season_cards(rows, seasons.season_info(conn, league_id), None)
    note(s["batting"] + s["pitching"], "in a season")
    c = seasons.career_cards(rows, current_season(conn, league_id), None)
    note(c["batting"] + c["pitching"], "in a career")
    g = stored.game_cards(conn, league_id, None)
    note(g["batting"] + g["pitching"], "in a game")
    st = stored.streak_cards(conn, league_id, None)
    note(st["players"], "")
    if len(_CACHE) >= _CACHE_SIZE:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[league_id] = (version, out)
    return out


def held(conn, league_id: str | None, player_id: str) -> list[str]:
    if not league_id:
        return []
    try:
        with conn.transaction():
            found = holders(conn, league_id).get(player_id, [])
    except Exception:  # a badge is never worth breaking the panel over
        log.exception("Couldn't work out records held in league %s", league_id)
        return []
    return [" ".join(label.split()) for label in found]
