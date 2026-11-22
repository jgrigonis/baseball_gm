# src/api/services/league_custom_teams.py
"""
Custom teams in a league (services/custom_teams.py builds them).

In a lobby with only its commissioner as a person, a commissioner who can
build custom teams puts one of their ready teams on any of the league's
teams. The league keeps that team's city, name and uniforms; only the
players change. The players are copied when they're put in, so later edits
to the custom team don't reach the league.

A league with a custom team is single player (leagues.single_player): it's
private, takes no late joiners, hides its join code and refuses joins.
Taking every custom team out again in the lobby lifts that.

At the start (league_start.py), apply() swaps each custom team's players in.
A team short of 26 is filled to 26 with the generated team's own players:
pitchers if it has fewer than 13, hitters otherwise.

Made-up players (services/custom_players.py) are copied in whole when the
team goes in ({"key": "made:<id>", "made": id, "player": {...}}). apply()
also says what the game would otherwise draw from a new player's id (face,
personality, morale ruiner, home region, jersey wishes) and his ceilings;
save_made() writes those once the players are saved.
"""

from __future__ import annotations

import random

from psycopg.types.json import Jsonb

from src.api.services import custom_players as cp
from src.api.services import custom_teams as ct
from src.api.services import lobby_teams
from src.db.repositories.custom_player_repo import CustomPlayerRepository
from src.db.repositories.custom_team_repo import CustomTeamRepository
from src.db.repositories.talent_cap_repo import TalentCapRepository
from src.db.repositories.ready_check_repo import ReadyCheckRepository
from src.league.real_seasons import players
from src.team.team_record import TeamRecord

ROSTER = 26
PITCHERS = 13


class CustomTeamRefused(ValueError):
    """Why a custom team can't go into this league now."""


def assignments(conn, league_id: str) -> dict[tuple[str, str], dict]:
    rows = conn.execute(
        """SELECT city, mascot, custom_team_id, name, players
           FROM league_custom_teams WHERE league_id = %s""",
        (league_id,),
    ).fetchall()
    return {(r["city"], r["mascot"]): dict(r) for r in rows}


def refusal(conn, league: dict, user: dict) -> str | None:
    """Why this person can't put custom teams in this league, or None."""
    if not ct.can_build(user):
        return "Custom teams are for paid contributors."
    if league["state"] != "lobby":
        return "Custom teams go in before the league starts."
    if league.get("is_practice"):
        return "Tutorial leagues use generated teams."
    if ReadyCheckRepository(conn).human_gm_count(league["id"]) > 1:
        return "Custom teams are for single-player leagues, and others have joined."
    return None


def _sync_single_player(conn, league_id: str) -> None:
    has = conn.execute(
        "SELECT 1 FROM league_custom_teams WHERE league_id = %s LIMIT 1",
        (league_id,),
    ).fetchone()
    if has:
        conn.execute(
            """UPDATE leagues SET single_player = TRUE, is_public = FALSE,
                      late_joins = FALSE WHERE id = %s""",
            (league_id,),
        )
    else:
        conn.execute(
            "UPDATE leagues SET single_player = FALSE WHERE id = %s", (league_id,)
        )


def assign(
    conn, league: dict, user: dict, city: str, mascot: str, custom_team_id: str
) -> None:
    """Put the user's custom team on (city, mascot); an empty id takes the
    custom team off it."""
    reason = refusal(conn, league, user)
    if reason:
        raise CustomTeamRefused(reason)
    if (city, mascot) not in lobby_teams.league_teams(conn, league["id"]):
        raise CustomTeamRefused("That team isn't in this league.")
    conn.execute(
        "DELETE FROM league_custom_teams WHERE league_id = %s AND city = %s AND mascot = %s",
        (league["id"], city, mascot),
    )
    if custom_team_id:
        team = ct.owned(CustomTeamRepository(conn), user, custom_team_id)
        if not team:
            raise CustomTeamRefused("That isn't one of your custom teams.")
        rows = ct.roster(team, conn)
        summary = ct.summary(rows)
        if not summary["ready"]:
            raise CustomTeamRefused(
                f"{team['name']} needs {', '.join(summary['needs'])} first."
            )
        conn.execute(
            """INSERT INTO league_custom_teams
                   (league_id, city, mascot, custom_team_id, name, players)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                league["id"],
                city,
                mascot,
                team["id"],
                team["name"],
                Jsonb(_copies(conn, team["players"])),
            ),
        )
    _sync_single_player(conn, league["id"])


def _copies(conn, entries: list[dict]) -> list[dict]:
    """The team's players as the league keeps them: made-up players copied
    whole (a deleted one is left out)."""
    made = CustomPlayerRepository(conn).get_many(
        e["made"] for e in entries if e.get("made")
    )
    out = []
    for e in entries:
        if not e.get("made"):
            out.append(dict(e))
        elif e["made"] in made:
            out.append({**e, "player": cp.snapshot(made[e["made"]])})
    return out


def _record(entry: dict, rng: random.Random):
    if entry.get("player"):
        return cp.record(entry["player"], rng)
    if entry.get("made"):
        return None  # a made-up player without his copy
    season = players.get(entry["key"])
    return season.record(rng, entry.get("skills")) if season else None


def _is_pitcher(p) -> bool:
    return p.position in ct.PITCHER_POS


def apply(
    conn, league_id: str, teams: list[TeamRecord], rng: random.Random
) -> tuple[list[TeamRecord], dict[str, dict]]:
    """The league's starting teams with each custom team's players in, and
    each made-up player's copy by his new player id (for save_made)."""
    chosen = assignments(conn, league_id)
    made: dict[str, dict] = {}
    if not chosen:
        return teams, made
    out = []
    for team in teams:
        entry = chosen.get((team.city, team.mascot))
        if not entry:
            out.append(team)
            continue
        mine = []
        for e in entry["players"]:
            rec = _record(e, rng)
            if rec is None:
                continue
            mine.append(rec)
            if e.get("player"):
                made[rec.id] = e["player"]
        pitchers = sum(_is_pitcher(p) for p in mine)
        want_p = max(PITCHERS - pitchers, 0)
        spare_p = [p for p in team.players if _is_pitcher(p)]
        spare_h = [p for p in team.players if not _is_pitcher(p)]
        room = max(ROSTER - len(mine), 0)
        fill = spare_p[: min(want_p, room)]
        fill += spare_h[: room - len(fill)]
        fill += spare_p[min(want_p, room) : min(want_p, room) + room - len(fill)]
        out.append(
            TeamRecord(
                id=team.id,
                city=team.city,
                mascot=team.mascot,
                players=tuple(mine + fill),
            )
        )
    return out, made


def save_made(conn, made: dict[str, dict]) -> None:
    """Give each saved made-up player what was picked for him, in place of
    what the game drew from his id: face, home region, jersey wishes,
    personality and morale ruiner, and his talent ceilings."""
    for pid, snap in made.items():
        pers = snap["personality"]
        conn.execute(
            """UPDATE players SET face = %s, home_region = %s, jersey_prefs = %s
               WHERE id = %s""",
            (
                Jsonb(snap["face"]),
                snap["home_region"],
                snap["jersey_prefs"] or None,
                pid,
            ),
        )
        conn.execute(
            """INSERT INTO player_personality
                   (player_id, type, drives, traits, climate, ruiner)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (player_id) DO UPDATE SET
                   type = EXCLUDED.type, drives = EXCLUDED.drives,
                   traits = EXCLUDED.traits, climate = EXCLUDED.climate,
                   ruiner = EXCLUDED.ruiner""",
            (
                pid,
                pers["type"],
                Jsonb(pers["drives"]),
                Jsonb(pers["traits"]),
                pers.get("climate"),
                bool(pers.get("ruiner")),
            ),
        )
        TalentCapRepository(conn).update_talent_caps(
            pid, {s: int(v) for s, v in snap["caps"].items()}
        )
