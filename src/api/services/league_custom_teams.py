# src/api/services/league_custom_teams.py
"""
Custom teams in a league (services/custom_teams.py builds them).

Custom teams only go in a custom league: the commissioner makes a league
one when creating it (leagues.custom_league, a paid contributor's choice on
the New League form), and it stays one for good, custom teams or not
(Josh, 2026-11-22). Only paid contributors (and admins) can run a team in a
custom league: may_join() guards every way in (join code, the Join tab,
taking over between seasons), and they see warning() first. Anyone can
watch. Someone already in keeps their seat if they stop being paid; they just
can't put custom teams in any more.

In a custom league's lobby, each paid person can put one of their ready
custom teams on the team they run, and the commissioner can also put them
on teams AI GMs hold. The league keeps that team's city, name and uniforms;
only the players change. The players are copied when they're put in, so
later edits to the custom team don't reach the league. A person who picks
another team or leaves the lobby takes theirs off their old team.

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
from src.league.real_seasons import players
from src.team.team_record import TeamRecord

ROSTER = 26
PITCHERS = 13

PAID_ONLY = "has custom teams, so only paid contributors can run a team in it."


class CustomTeamRefused(ValueError):
    """Why a custom team can't go into this league now."""


def assignments(conn, league_id: str) -> dict[tuple[str, str], dict]:
    rows = conn.execute(
        """SELECT city, mascot, custom_team_id, name, players, user_id
           FROM league_custom_teams WHERE league_id = %s""",
        (league_id,),
    ).fetchall()
    return {(r["city"], r["mascot"]): dict(r) for r in rows}


# ── who can join ───────────────────────────────────────────────────────


def may_join(user: dict | None, league: dict) -> bool:
    """Whether this person may run a team in the league: anyone in an
    ordinary league, only paid contributors (or admins) in a custom one."""
    return not league.get("custom_league") or ct.can_build(user)


def paid_only(league: dict) -> str:
    """Why someone who isn't paid can't join a custom league."""
    return f"{league['name']} {PAID_ONLY}"


def _holders(conn, league_id: str) -> dict[tuple[str, str], dict]:
    """Who runs each team, by (city, mascot): the GM dealt it in the lobby,
    or the GM whose team it is once the league has started."""
    rows = conn.execute(
        """SELECT g.id, g.user_id, g.display_name, g.is_ai,
                  COALESCE(t.city, g.lobby_city) AS city,
                  COALESCE(t.mascot, g.lobby_mascot) AS mascot
           FROM gms g LEFT JOIN teams t ON t.id = g.team_id
           WHERE g.league_id = %s AND g.fired_at IS NULL""",
        (league_id,),
    ).fetchall()
    return {(r["city"], r["mascot"]): dict(r) for r in rows if r["city"]}


def warning(conn, league: dict, user_id: str | None = None) -> list[dict]:
    """The custom teams a joiner is told about: each league team that plays
    as a custom team, who runs it, who put it in, and how many of its
    players are made up or have edited ratings. Whether it's the joiner's
    own (mine) is filled in by the caller when it knows."""
    holders = _holders(conn, league["id"])
    by_user = {
        h["user_id"]: h["display_name"] for h in holders.values() if h["user_id"]
    }
    out = []
    for (city, mascot), a in sorted(assignments(conn, league["id"]).items()):
        holder = holders.get((city, mascot))
        entries = a["players"] or []
        out.append(
            {
                "city": city,
                "mascot": mascot,
                "name": a["name"],
                "size": len(entries),
                "made": sum(1 for e in entries if e.get("made")),
                "edited": sum(1 for e in entries if e.get("skills")),
                "run_by": (
                    "AI GM" if not holder or holder["is_ai"] else holder["display_name"]
                ),
                "put_in_by": by_user.get(a.get("user_id")),
                "mine": bool(user_id and holder and holder["user_id"] == user_id),
            }
        )
    return out


# ── putting custom teams in ────────────────────────────────────────────


def refusal(conn, league: dict, user: dict) -> str | None:
    """Why this person can't put custom teams in this league, or None."""
    if not league.get("custom_league"):
        return "Custom teams go in custom leagues, set when the league is created."
    if not ct.can_build(user):
        return "Custom teams are for paid contributors."
    if league["state"] != "lobby":
        return "Custom teams go in before the league starts."
    if league.get("is_practice"):
        return "Tutorial leagues use generated teams."
    return None


def settable(conn, league: dict, user: dict) -> list[tuple[str, str]]:
    """The league teams this person may put a custom team on (or take one
    off): the one they run, and for the commissioner the AI GMs' teams too."""
    gm = conn.execute(
        "SELECT id, lobby_city, lobby_mascot FROM gms WHERE league_id = %s AND user_id = %s",
        (league["id"], user["id"]),
    ).fetchone()
    if not gm:
        return []
    commish = league["commissioner_gm_id"] == str(gm["id"])
    holders = _holders(conn, league["id"])
    out = []
    for key in lobby_teams.league_teams(conn, league["id"]):
        h = holders.get(key)
        if h and h["id"] == gm["id"]:
            out.insert(0, key)  # their own team first
        elif commish and (not h or h["is_ai"]):
            out.append(key)
    return out


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
    if (city, mascot) not in settable(conn, league, user):
        raise CustomTeamRefused(
            "You can set the custom team for your own team"
            + (" and the AI GMs' teams." if _is_commish(conn, league, user) else ".")
        )
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
                   (league_id, city, mascot, custom_team_id, name, players, user_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                league["id"],
                city,
                mascot,
                team["id"],
                team["name"],
                Jsonb(_copies(conn, team["players"])),
                user["id"],
            ),
        )


def _is_commish(conn, league: dict, user: dict) -> bool:
    gm = conn.execute(
        "SELECT id FROM gms WHERE league_id = %s AND user_id = %s",
        (league["id"], user["id"]),
    ).fetchone()
    return bool(gm and league["commissioner_gm_id"] == str(gm["id"]))


def take_off(
    conn, league_id: str, user_id: str, city: str | None, mascot: str | None
) -> None:
    """A person leaving a lobby team (another pick, or leaving the league)
    takes the custom team they put on it with them."""
    if not user_id or not city:
        return
    conn.execute(
        """DELETE FROM league_custom_teams
           WHERE league_id = %s AND city = %s AND mascot = %s AND user_id = %s""",
        (league_id, city, mascot, user_id),
    )


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
