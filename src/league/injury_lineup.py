# src/league/injury_lineup.py
#
# The Strategy tab's Injury Lineup setting: what the coach does to a person's
# saved batting orders when one of his hitters is hurt.
#   - Always auto-fill (the default): the saved lineup plays, and the missing
#     man's slot is filled for the day (TeamInGame._set_lineup_from_saved).
#     He goes straight back into it when he's available again.
#   - Auto-fill up to N days (10, 7, 5, 3, 2 or 1): an out that short is
#     filled the same way;
#     a longer one gets both batting orders rebuilt.
#   - Always rebuild: every out gets them rebuilt.
# A rebuild is the Lineup tab's Rebuild for both hands (vs RHP and vs LHP),
# saved as the person's lineups. It happens when a long out starts, again
# when the player is back in the lineup, and again when his rust wears off.
# How long an out is counts the injury's days, plus the days he sits rusty
# when Rest rusty players is on (rust fades twice as fast on days he doesn't
# play). AI teams have no saved lineup and are built fresh every game.
#
# The Strategy tab's Lineup Updates setting can instead rebuild both batting
# orders before every game (Rebuild daily, Josh 2026-11-13); then the Injury
# Lineup setting has nothing left to do. Every rebuild here starts from the
# lineup being played, so a player only moves or loses his spot when the
# change is clearly better (LineupOptimizer KEEP_BONUS).

from __future__ import annotations

import math

from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.lineup_preference_repo import (
    HANDS,
    LineupPreferenceRepository,
)
from src.team.lineup_optimizer import LineupOptimizer


def days_out(length: int, rust_days: float, rest_rusty: bool) -> int:
    """How many days an injury keeps a hitter out of the lineup: its own
    length, plus the rust he sits out when Rest rusty players is on."""
    return length + (math.ceil(rust_days / 2) if rest_rusty else 0)


def absence_key(team, eligible, hurt: set, out: set, rust: dict, lengths: dict) -> str:
    """Who on this team is out long enough to rebuild for, and how: "id:out"
    while he can't play, "id:rusty" while he plays with rust on. It changes
    when a long out starts, when he's back, and when his rust is gone."""
    profile = team.profile
    after = profile.rebuild_after_days
    entries = []
    for p in team.players:
        if p.pitcher_fatigue or (eligible and p.id not in eligible):
            continue
        length = lengths.get(p.id)
        if not length:
            continue
        if days_out(length["length"], length["rust_days"], profile.rest_rusty) <= after:
            continue
        if p.id in hurt or p.id in out:
            entries.append(f"{p.id}:out")
        elif p.id in rust:
            entries.append(f"{p.id}:rusty")
    return ",".join(sorted(entries))


def update_lineups(
    conn, league_id: str, team, eligible, hurt: set, out: set, rust: dict
) -> bool:
    """Before a game: this person's batting orders rebuilt and saved if
    their Lineup Updates or Injury Lineup setting calls for it. True if
    either changed."""
    if team.profile.lineup_updates == "daily":
        gm_id = _person(conn, league_id, team)
        return bool(gm_id) and _rebuild(conn, gm_id, team, eligible, out)
    return rebuild_if_needed(conn, league_id, team, eligible, hurt, out, rust)


def _person(conn, league_id: str, team) -> str | None:
    """The id of the person running this team, or None for an AI team."""
    row = conn.execute(
        """SELECT id FROM gms
           WHERE team_id = %s AND league_id = %s AND NOT is_ai
             AND fired_at IS NULL
           LIMIT 1""",
        (team.record.id, league_id),
    ).fetchone()
    return row["id"] if row else None


def rebuild_if_needed(
    conn, league_id: str, team, eligible, hurt: set, out: set, rust: dict
) -> bool:
    """Rebuild and save this person's batting orders if their Injury Lineup
    setting calls for it today. hurt is who's injured today, out is hurt plus
    anyone resting his rust, rust is who still has some. True if the rebuild
    changed either batting order.
    The first look after the setting changes only notes who's out."""
    if team.profile.rebuild_after_days is None:
        return False
    gm = conn.execute(
        """SELECT g.id, gp.injury_lineup_key FROM gms g
           JOIN gm_profiles gp ON gp.gm_id = g.id
           WHERE g.team_id = %s AND g.league_id = %s AND NOT g.is_ai
             AND g.fired_at IS NULL
           LIMIT 1""",
        (team.record.id, league_id),
    ).fetchone()
    if not gm:
        return False
    ids = [p.id for p in team.players if p.id in hurt or p.id in out or p.id in rust]
    lengths = InjuryRepository(conn, league_id).get_lengths(ids)
    key = absence_key(team, eligible, hurt, out, rust, lengths)
    stored = gm["injury_lineup_key"]
    if stored == key:
        return False
    conn.execute(
        "UPDATE gm_profiles SET injury_lineup_key = %s WHERE gm_id = %s",
        (key, gm["id"]),
    )
    if stored is None:
        return False
    return _rebuild(conn, gm["id"], team, eligible, out)


def _rebuild(conn, gm_id: str, team, eligible, out: set) -> bool:
    """The Lineup tab's Rebuild for both hands, starting from the saved
    batting orders so only clearly better changes are made, and saved. True
    if either hand changed."""
    team._ensure_players_rated()
    hitters = [
        p
        for p in team.players
        if not p.pitcher_fatigue
        and p.id not in out
        and (not eligible or p.id in eligible)
    ]
    profile = team.profile
    repo = LineupPreferenceRepository(conn)
    saved = repo.get_by_gm_id(gm_id)
    playing = {p.id for p in hitters}
    lineups = {}
    try:
        for hand in HANDS:
            # A hand never saved plays the other one (get_preferences).
            now = saved[hand] or saved["L" if hand == "R" else "R"]
            keep = {
                s["player_id"]: (s["batting_order"] - 1, s.get("position") or "")
                for s in now
                if s["player_id"] in playing and 1 <= s["batting_order"] <= 9
            }
            slots = LineupOptimizer.fill(
                [None] * 9,
                hitters,
                style=profile.lineup_style,
                dh=True,
                vs_hand=hand,
                platoon=profile.platoon_usage,
                form=getattr(team, "form", None) or None,
                defense=getattr(team, "defense_weight", 1.0),
                keep=keep,
            )
            lineups[hand] = [
                {
                    "player_id": s.player.id,
                    "batting_order": i + 1,
                    "position": s.position,
                }
                for i, s in enumerate(slots)
            ]
    except ValueError:
        return False  # too few hitters: today's fill will cope
    changed = False
    for hand, lineup in lineups.items():
        if _key(lineup) != _key(saved[hand]):
            repo.save_preferences(gm_id, lineup, hand)
            changed = True
    return changed


def _key(lineup: list[dict]) -> list[tuple]:
    """A batting order to compare: (slot, player, position) for each spot."""
    return sorted(
        (s["batting_order"], s["player_id"], s.get("position") or "") for s in lineup
    )
