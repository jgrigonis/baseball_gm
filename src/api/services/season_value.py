# src/api/services/season_value.py
"""
WAR and defensive runs (Def) for every player in a regular season, for the
Stats and Leaders tabs, the player panel and the career page.

WAR is the awards voters' wins above replacement (src/league/awards.py:
batting runs by wOBA, base stealing, a position adjustment, the Platinum
Glove's defensive runs at the position he started at most and replacement
level for hitters; a FIP/ERA blend against a replacement pitcher for
pitchers). Def leans on his defense rating there, then
the plays he made, the errors he didn't and (catchers) the runners he
threw out, against the league's regulars at the position.

Working it out rates the whole league, so each season's answer is kept
until another game is played in it.
"""

from __future__ import annotations

from src.api.services import awards as awards_service
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.league import awards

_CACHE: dict[str, tuple[int, dict[str, dict]]] = {}
_CACHE_SIZE = 32


def _version(conn, season_id: str) -> int:
    """Changes whenever a game in the season is saved."""
    row = conn.execute(
        """SELECT COALESCE(SUM(bat_ab + bat_walks + pitch_outs), 0) AS v
           FROM player_season_stats
           WHERE season_id = %s AND NOT is_postseason""",
        (season_id,),
    ).fetchone()
    return int(row["v"] or 0)


def season_values(conn, season_id: str) -> dict[str, dict]:
    """{player_id: {"WAR": wins, "Def": runs or None, "hitter": bool}} for
    a season's regular season. A player is valued as a hitter or as a
    pitcher (whichever he played more games as), never both; Def is None
    for pitchers. bat_war() and pit_war() read it for one side."""
    version = _version(conn, season_id)
    hit = _CACHE.get(season_id)
    if hit and hit[0] == version:
        return hit[1]
    values = _compute(conn, season_id) if version else {}
    if len(_CACHE) >= _CACHE_SIZE:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[season_id] = (version, values)
    return values


def _compute(conn, season_id: str) -> dict[str, dict]:
    row = conn.execute(
        "SELECT year FROM seasons WHERE id = %s", (season_id,)
    ).fetchone()
    if not row:
        return {}
    cands = awards_service.candidates(conn, season_id, row["year"], {})
    games = PlayerSeasonStatsRepository(conn).get_max_games_played(season_id)
    lg = awards.League.of(cands, games)
    defense = awards.season_defense(cands, games)
    for c in cands:
        c["def_runs"] = defense.get(c["player_id"], 0.0)
    out = {}
    for c in cands:
        pid = c["player_id"]
        if awards.is_hitter(c):
            d = defense.get(pid)
            out[pid] = {
                "WAR": round(awards.hitter_war(c, lg), 1),
                "Def": round(d, 1) if d is not None else None,
                "hitter": True,
            }
        elif c.get("pitch_outs"):
            out[pid] = {
                "WAR": round(awards.pitcher_war(c, lg), 1),
                "Def": None,
                "hitter": False,
            }
    return out


def bat_war(values: dict[str, dict], player_id: str) -> float | None:
    v = values.get(player_id)
    return v["WAR"] if v and v["hitter"] else None


def pit_war(values: dict[str, dict], player_id: str) -> float | None:
    v = values.get(player_id)
    return v["WAR"] if v and not v["hitter"] else None


def defense(values: dict[str, dict], player_id: str) -> float | None:
    v = values.get(player_id)
    return v["Def"] if v else None
