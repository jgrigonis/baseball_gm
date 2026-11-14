# src/team/roster_limits.py
#
# The size of a team's playing roster. In Blitz-style leagues that's the
# 40-man (26man and 40man players), which must hold 25 to 40. A trade can
# leave a roster short, since traded players arrive in the organization
# (minors); before the team's next game the game promotes the best healthy
# players from the organization, or sends the lowest-rated down if it's over.
# Each move goes in the GM's news.
#
# Long Form plays off the 26-man (Josh, 2026-11-14): the active roster holds
# 25 to 26 players with at most 13 pitchers, and from September 1 to the end
# of the regular season a full 28 with at most 14 (the playoffs go back to 26),
# and the 40-man (active plus reserve) holds at most 40. Before a team plays,
# the game fixes whatever is over or under, lowest-rated first, and tells the
# GM. AI teams also take players hurt for more than a few days off the active
# roster, call up a healthy replacement, fill open spots (September), and put
# players back once they've healed. There are no option years or move limits.

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.notification_repo import NotificationRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.league.league_modes import is_blitz_style
from src.player.player_value import role_rating
from src.player.positions import is_pitcher
from src.team.injured_list import InjuredList, ai_kind

log = logging.getLogger(__name__)

MIN_PLAYING_ROSTER = 25
MAX_PLAYING_ROSTER = 40
PLAYING_STATUSES = ("26man", "40man")


# Long Form (league_modes.LONGFORM)
ACTIVE_MIN = 25
ACTIVE_MAX = 26
ACTIVE_MAX_EXPANDED = 28
PITCHER_MAX = 13
PITCHER_MAX_EXPANDED = 14
FORTY_MAX = 40
# Expanded rosters start on this month and day.
EXPANSION_DAY = (9, 1)
# An AI team takes a player off its active roster when he's hurt for more
# than this many days, and puts a reserve back on once he's been healthy for
# up to RETURN_WINDOW_DAYS.
AI_BENCH_AFTER_DAYS = 3
RETURN_WINDOW_DAYS = 14


@dataclass(frozen=True)
class ActiveLimits:
    max_active: int
    max_pitchers: int
    min_active: int = ACTIVE_MIN

    @property
    def expanded(self) -> bool:
        return self.max_active > ACTIVE_MAX


def active_limits(game_date: str | None, playoffs: bool = False) -> ActiveLimits:
    """Long Form's active roster limits on a date: 25 to 26 with 13
    pitchers, a full 28 with 14 from September 1 through the regular
    season."""
    if game_date and not playoffs:
        d = date.fromisoformat(str(game_date)[:10])
        if (d.month, d.day) >= EXPANSION_DAY:
            # A full 28: every team carries all of them (Josh, 2026-11-14).
            return ActiveLimits(
                ACTIVE_MAX_EXPANDED, PITCHER_MAX_EXPANDED, ACTIVE_MAX_EXPANDED
            )
    return ActiveLimits(ACTIVE_MAX, PITCHER_MAX)


def league_active_limits(conn, league: dict) -> ActiveLimits:
    """The limits on the league's next game day."""
    from src.db.repositories.season_repo import SeasonRepository
    from src.web.utils import _current_league_date

    state = league.get("state") or ""
    season_id = SeasonRepository(conn).get_most_recent_season_from_league(league["id"])
    on = _current_league_date(conn, season_id, state, all_star_game=False)
    return active_limits(on, playoffs=state == "playoffs")


def playing_count(conn, team_id: str) -> int:
    return conn.execute(
        """SELECT COUNT(*) AS n FROM team_players tp
           JOIN player_status ps ON ps.player_id = tp.player_id
           WHERE tp.team_id = %s AND ps.status IN ('26man', '40man')""",
        (team_id,),
    ).fetchone()["n"]


def enforce_roster_limits(
    conn,
    league_id: str,
    team_id: str,
    mode: str | None,
    game_date: str | None = None,
    playoffs: bool = False,
) -> list[dict]:
    """Bring the team's playing roster back to 25-40 players (Long Form:
    its 26-man and 40-man inside their limits). Returns the moves made, each
    {"player_id", "name", "to"}."""
    if not is_blitz_style(mode):
        return enforce_active_roster(
            conn, league_id, team_id, game_date, playoffs=playoffs
        )
    count = playing_count(conn, team_id)
    if MIN_PLAYING_ROSTER <= count <= MAX_PLAYING_ROSTER:
        return []

    status_repo = PlayerStatusRepository(conn)
    players = PlayerRepository(conn).get_players_by_team(team_id)
    statuses = {p.id: status_repo.get_status(p.id) for p in players}
    rated = {p.id: role_rating(p) for p in players}
    moves = []

    if count < MIN_PLAYING_ROSTER:
        injured = set(InjuryRepository(conn, league_id).get_team_injuries(team_id))
        pool = [p for p in players if statuses[p.id] == "minors"]
        # Healthy players first, best first.
        pool.sort(key=lambda p: (p.id in injured, -rated[p.id]))
        for p in pool[: MIN_PLAYING_ROSTER - count]:
            status_repo.set_status(p.id, "40man")
            moves.append({"player_id": p.id, "name": p.name, "to": "40man"})
    else:
        on = [p for p in players if statuses[p.id] in PLAYING_STATUSES]
        on.sort(key=lambda p: rated[p.id])
        for p in on[: count - MAX_PLAYING_ROSTER]:
            status_repo.set_status(p.id, "minors")
            moves.append({"player_id": p.id, "name": p.name, "to": "minors"})

    _tell_gm(conn, league_id, team_id, moves)
    log.info("Team %s roster had %s players: moved %s", team_id, count, len(moves))
    return moves


def _tell_gm(conn, league_id: str, team_id: str, moves: list[dict]) -> None:
    gm = GMRepository(conn).get_human_gm_for_team(league_id, team_id)
    if not gm:
        return
    notes = NotificationRepository(conn)
    for m in moves:
        note = {"name": m["name"], "to": m["to"]}
        if m.get("why"):
            note["why"] = m["why"]
        notes.add(gm, "roster", note)


# ── Long Form ────────────────────────────────────────────────────────────────


def _org(conn, team_id: str) -> list[dict]:
    """Every player in the organization: id, name, position and status."""
    rows = conn.execute(
        """SELECT p.id, p.first_name, p.last_name, p.position, ps.status
           FROM team_players tp
           JOIN players p ON p.id = tp.player_id
           JOIN player_status ps ON ps.player_id = tp.player_id
           WHERE tp.team_id = %s AND ps.status IN ('26man', '40man', 'minors')""",
        (team_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _recently_back(conn, league_id: str, ids: list[str], on: str) -> set[str]:
    """Of these players, those whose injury ended in the last
    RETURN_WINDOW_DAYS days."""
    if not ids:
        return set()
    since = (date.fromisoformat(on) - timedelta(days=RETURN_WINDOW_DAYS)).isoformat()
    rows = conn.execute(
        """SELECT DISTINCT player_id FROM player_injuries
           WHERE league_id = %s AND player_id = ANY(%s)
             AND return_date::date > %s::date AND return_date::date <= %s::date""",
        (league_id, ids, since, on),
    ).fetchall()
    return {r["player_id"] for r in rows}


def enforce_active_roster(
    conn,
    league_id: str,
    team_id: str,
    game_date: str | None,
    playoffs: bool = False,
) -> list[dict]:
    """A Long Form team's rosters inside the limits before it plays: the
    40-man at most 40, the active roster 25 to 26 (28 from September 1) with
    at most 13 pitchers (14). Players on the injured list stay on the 40-man
    but can't be called up; the 60-day list doesn't count toward the 40.
    AI teams also put players hurt for more than a few days on the injured
    list, take healed ones off it, and fill every open spot. Returns the
    moves made."""
    on = str(game_date or date.today().isoformat())[:10]
    limits = active_limits(on, playoffs)
    org = _org(conn, team_id)
    if not org:
        return []
    ai = not GMRepository(conn).get_human_gm_for_team(league_id, team_id)
    injuries = InjuryRepository(conn, league_id)
    days_out = injuries.get_team_injuries(team_id, as_of=on)
    il = InjuredList(conn, league_id)
    stints = il.for_team(team_id)
    on_il = set(stints)
    sixty = {pid for pid, st in stints.items() if st.sixty}

    status = {p["id"]: p["status"] for p in org}
    pitcher = {p["id"]: is_pitcher((p["position"] or "").lower()) for p in org}
    name = {p["id"]: f"{p['first_name']} {p['last_name']}" for p in org}
    position = {p["id"]: p["position"] for p in org}

    def ids(*tiers: str) -> list[str]:
        return [pid for pid, s in status.items() if s in tiers]

    def pitchers_active() -> int:
        return sum(1 for pid in ids("26man") if pitcher[pid])

    def hurt(pid: str) -> bool:
        return pid in days_out

    def long_hurt(pid: str) -> bool:
        return days_out.get(pid, 0) > AI_BENCH_AFTER_DAYS

    def forty_count() -> int:
        """The 40-man as it counts: everyone on it but the 60-day IL."""
        return len([p for p in ids("26man", "40man") if p not in sixty])

    def reserve() -> list[str]:
        """The 40-man players who can be called up or sent down: not on the
        injured list."""
        return [p for p in ids("40man") if p not in on_il]

    # Quick exit: nothing to do for a legal roster, unless an AI team has a
    # long-hurt player off the injured list, an open spot, a healed reserve
    # or a player ready to come off the list.
    active = ids("26man")
    legal = (
        forty_count() <= FORTY_MAX
        and limits.min_active <= len(active) <= limits.max_active
        and pitchers_active() <= limits.max_pitchers
    )
    if legal and not ai:
        return []
    back = _recently_back(conn, league_id, reserve(), on) if ai else set()
    ready = il.ready(team_id, on) if ai else {}
    if (
        legal
        and len(active) == limits.max_active
        and not any(long_hurt(p) for p in ids("26man", "40man") if p not in on_il)
        and not back
        and not ready
    ):
        return []

    players = {p.id: p for p in PlayerRepository(conn).get_players_by_team(team_id)}
    rated = {pid: role_rating(p) for pid, p in players.items()}
    moves: list[dict] = []

    def rating(pid: str) -> float:
        return rated.get(pid, 0)

    def move(pid: str, to: str, why: str) -> None:
        status[pid] = to
        moves.append({"player_id": pid, "name": name[pid], "to": to, "why": why})

    # 1. Active over the pitcher limit: the lowest-rated pitchers sit.
    while pitchers_active() > limits.max_pitchers:
        worst = min((p for p in ids("26man") if pitcher[p]), key=rating)
        move(worst, "40man", "pitchers")
    # 2. Active over the limit: the lowest-rated sit.
    while len(ids("26man")) > limits.max_active:
        worst = min(ids("26man"), key=lambda p: (not hurt(p), rating(p)))
        move(worst, "40man", "active_full")

    # 3. AI teams: players ready to come off the injured list do (the
    #    60-day list only with 40-man room), and players hurt for more than a
    #    few days go on it, the active ones coming off the active roster.
    to_place: list[tuple[str, int]] = []
    if ai:
        for pid in sorted(ready, key=rating, reverse=True):
            if ready[pid].sixty and forty_count() >= FORTY_MAX:
                continue
            il.activate(pid, on)
            on_il.discard(pid)
            sixty.discard(pid)
            back.add(pid)
        types = injuries.get_team_injury_types(team_id)
        for pid in sorted(ids("26man", "40man"), key=rating):
            if pid in on_il or not long_hurt(pid):
                continue
            kind = ai_kind(position[pid], types.get(pid), days_out[pid])
            to_place.append((pid, kind))
            on_il.add(pid)
            if kind == 60:
                sixty.add(pid)
            if status[pid] == "26man":
                move(pid, "40man", "hurt")

    def room_for(pid: str) -> bool:
        return not pitcher[pid] or pitchers_active() < limits.max_pitchers

    def best(pool: list[str], want_pitcher: bool | None = None) -> str | None:
        pool = [
            p
            for p in pool
            if not hurt(p)
            and room_for(p)
            and (want_pitcher is None or pitcher[p] == want_pitcher)
        ]
        return max(pool, key=rating) if pool else None

    def call_up(want_pitcher: bool | None, why: str) -> bool:
        """The best healthy reserve onto the active roster, or a minor
        leaguer if the reserve has nobody (making 40-man room if needed)."""
        pid = best(reserve(), want_pitcher)
        if pid:
            move(pid, "26man", why)
            return True
        pid = best(ids("minors"), want_pitcher)
        if not pid:
            return False
        if forty_count() >= FORTY_MAX:
            spare = reserve()
            if not spare:
                return False
            move(
                min(spare, key=lambda p: (not hurt(p), rating(p))),
                "minors",
                "forty_full",
            )
        move(pid, "26man", why)
        return True

    # 4. AI teams: healed reserves back in for the worst active of their kind.
    if ai:
        for pid in sorted(back, key=rating, reverse=True):
            if status.get(pid) != "40man" or hurt(pid) or pid in on_il:
                continue
            same = [p for p in ids("26man") if pitcher[p] == pitcher[pid]]
            if len(ids("26man")) < limits.max_active and room_for(pid):
                move(pid, "26man", "back")
            elif same and rating(pid) > rating(min(same, key=rating)):
                worst = min(same, key=rating)
                move(worst, "40man", "replaced")
                move(pid, "26man", "back")

    # 5. Short: call up. People's teams go back to the minimum; AI teams fill
    #    every spot, a like-for-like replacement first for each player benched.
    target = limits.max_active if ai else limits.min_active
    if ai:
        for m in [m for m in moves if m["why"] == "hurt"]:
            if len(ids("26man")) >= target:
                break
            call_up(pitcher[m["player_id"]], "replacement")
    while len(ids("26man")) < target:
        need_pitcher = None
        if ai and pitchers_active() < limits.max_pitchers - 1:
            need_pitcher = True
        if not call_up(need_pitcher, "short") and not (
            need_pitcher and call_up(None, "short")
        ):
            break

    # 6. 40-man over the limit: the lowest-rated reserves go to the minors.
    while forty_count() > FORTY_MAX and reserve():
        worst = min(reserve(), key=lambda p: (not hurt(p), rating(p)))
        move(worst, "minors", "forty_full")

    # Net moves only: a player moved twice keeps just where he ended up.
    final: dict[str, dict] = {}
    for m in moves:
        final[m["player_id"]] = m
    original = {p["id"]: p["status"] for p in org}
    moves = [m for pid, m in final.items() if original[pid] != m["to"]]
    repo = PlayerStatusRepository(conn)
    for m in moves:
        repo.set_status(m["player_id"], m["to"])
        m["from"] = original[m["player_id"]]
    for pid, kind in to_place:
        il.place(team_id, pid, kind, on)
    if not moves:
        return []
    if ai:
        _reseed(conn, league_id, team_id, on, moves, pitcher)
    else:
        _tell_gm(conn, league_id, team_id, moves)
    log.info("Team %s active roster: moved %s", team_id, len(moves))
    return moves


def _reseed(conn, league_id, team_id, on, moves, pitcher) -> None:
    """An AI team whose active pitchers changed resets its rotation and
    bullpen from the new staff."""
    if not any(pitcher[m["player_id"]] for m in moves):
        return
    from src.db.repositories.season_repo import SeasonRepository
    from src.league.rotation_seeder import seed_ai_rotations

    season_id = SeasonRepository(conn).get_most_recent_season_from_league(league_id)
    if season_id:
        seed_ai_rotations(
            conn,
            season_id,
            {team_id},
            statuses=["26man"],
            effective_date=on,
            league_id=league_id,
        )
