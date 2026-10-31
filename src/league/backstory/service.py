# src/league/backstory/service.py
"""
Generate a league's past seasons and save them (see __init__.py).

create_backstory() runs at league start, after the teams are filled and
before the draft order is written. Past seasons are ordinary season rows
marked is_backstory, linked to the league and its teams, with completed
games (scores, line scores, hits and errors, no box scores), playoff series,
player_season_stats lines, skill snapshots and All-Stars. Veterans made up
to fill past rosters are saved as retired players.
"""

from __future__ import annotations

import datetime
import random
import uuid
from dataclasses import dataclass

import numpy as np
from psycopg.types.json import Jsonb

from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.retirement_repo import RetirementRepository
from src.db.repositories.standings_repo import StandingsRepository
from src.league import all_star
from src.league.backstory import careers as careers_mod
from src.league.backstory import season as season_mod
from src.league.backstory.careers import Career
from src.league.backstory.season import Game, Member
from src.league.league_constants import (
    ALL_STAR_BREAK_AFTER_GAMES,
    ALL_STAR_BREAK_DAYS,
    SEASON_LENGTH,
)
from src.league.schedule import ScheduleGenerator
from src.player.player_skills import PlayerSkills

PLAYOFF_TEAMS = 8
# Days between the last regular-season game and the first playoff game, as
# the real sim leaves (src/api/services/sim_next.py).
PLAYOFF_GAP_DAYS = 5
SEASON_NAME = "Past season"

SKILL_COLUMNS = (
    "durability",
    "clutch",
    "speed",
    "power",
    "eye",
    "contact",
    "base_running",
    "bunting",
    "catching",
    "infield",
    "outfield",
    "arm",
    "accuracy",
    "stamina",
    "recovery",
    "ground_balls",
    "strikes",
)


@dataclass
class Backstory:
    season_ids: list[str]  # oldest first
    last_season_id: str | None
    retirees: int


def create_backstory(
    conn, league_id: str, season_id: str, years: int, rng: random.Random
) -> Backstory:
    """Generate `years` seasons before the league's first season
    (season_id) and save them. Doesn't commit."""
    if years <= 0:
        return Backstory([], None, 0)
    base_year = conn.execute(
        "SELECT year FROM seasons WHERE id = %s", (season_id,)
    ).fetchone()["year"]
    team_ids = LeagueRepository(conn).get_league_teams(league_id, season_id)
    players = _current_players(conn, team_ids)
    np_rng = np.random.default_rng(rng.getrandbits(64))

    team_ids = sorted(team_ids)
    careers = careers_mod.current_careers(players, base_year, years, team_ids, rng)
    retirees = careers_mod.add_retirees(careers, base_year, years, team_ids, rng)
    _save_retirees(conn, league_id, retirees)

    season_ids = []
    for year in range(base_year - years, base_year):
        sid = _play_year(
            conn, league_id, year, team_ids, careers, base_year, rng, np_rng
        )
        season_ids.append(sid)

    year_to_season = dict(zip(range(base_year - years, base_year), season_ids))
    retire_repo = RetirementRepository(conn)
    for r in retirees:
        retire_repo.retire_player(
            r.player_id, league_id, year_to_season[r.retired_after], r.final_team_id
        )
    return Backstory(season_ids, season_ids[-1], len(retirees))


# ── Loading today's players ───────────────────────────────────────────────────


def _current_players(conn, team_ids: list[str]) -> list[dict]:
    rows = conn.execute(
        f"""SELECT tp.team_id, p.id, p.first_name, p.last_name, p.bats,
                   p.throws, p.position, sk.age,
                   {", ".join("sk." + c for c in SKILL_COLUMNS)},
                   to_jsonb(tc) AS caps
            FROM team_players tp
            JOIN players p ON p.id = tp.player_id
            JOIN player_skills sk ON sk.player_id = p.id
            LEFT JOIN player_talent_caps tc ON tc.player_id = p.id
            WHERE tp.team_id = ANY(%s)""",
        (team_ids,),
    ).fetchall()
    out = []
    for r in rows:
        caps = r["caps"]
        if caps:
            caps = {k: v for k, v in caps.items() if k in SKILL_COLUMNS}
        out.append(
            {
                "id": r["id"],
                "team_id": r["team_id"],
                "first_name": r["first_name"],
                "last_name": r["last_name"],
                "bats": r["bats"],
                "throws": r["throws"],
                "position": r["position"],
                "age": r["age"],
                "skills": {c: float(r[c]) for c in SKILL_COLUMNS},
                "caps": caps or None,
            }
        )
    return out


# ── One season ────────────────────────────────────────────────────────────────


def _play_year(conn, league_id, year, team_ids, careers, base_year, rng, np_rng) -> str:
    lr = LeagueRepository(conn)
    sid = _create_season(conn, year)
    lr.assign_season_to_league(league_id, sid)
    for tid in team_ids:
        lr.assign_team_to_league(league_id, sid, tid)

    by_team: dict[str, list[Career]] = {t: [] for t in team_ids}
    for c in careers:
        tid = c.team_by_year.get(year)
        if tid in by_team:
            by_team[tid].append(c)
    members = {
        tid: [
            Member(
                player_id=c.player_id,
                position=c.position,
                throws=c.throws,
                age=c.age_in(year, base_year),
                skills=c.skills_by_year[year],
            )
            for c in cs
        ]
        for tid, cs in by_team.items()
    }

    teams = [season_mod.team_season(np_rng, tid, members[tid]) for tid in team_ids]
    strength = season_mod.strengths(np_rng, teams)

    schedule = ScheduleGenerator(rng=rng).create_schedule(
        season_id=sid,
        team_ids=team_ids,
        start_date=datetime.date(year, 4, 1),
        target_games=SEASON_LENGTH,
        all_star_break_after=ALL_STAR_BREAK_AFTER_GAMES,
        all_star_break_days=ALL_STAR_BREAK_DAYS,
    )
    games = season_mod.play_schedule(np_rng, schedule, strength)
    team_hits = {
        t.team_id: sum(ln.stats["bat_hits"] for ln in t.batting) for t in teams
    }
    season_mod.add_hits_and_errors(np_rng, games, team_hits)
    records = season_mod.team_records(games)
    for t in teams:
        season_mod.finish_lines(np_rng, t, records[t.team_id])
    _save_games(conn, sid, games)

    if len(team_ids) >= PLAYOFF_TEAMS:
        seeds = [
            r["team_id"]
            for r in StandingsRepository(conn).get_top_n(sid, PLAYOFF_TEAMS)
        ]
        last_day = max(datetime.date.fromisoformat(g.game_date) for g in games)
        start = last_day + datetime.timedelta(days=PLAYOFF_GAP_DAYS)
        series, playoff_games = season_mod.play_playoffs(
            np_rng, strength, sid, seeds, start
        )
        season_mod.add_hits_and_errors(np_rng, playoff_games, {})
        for series_id, name in series:
            conn.execute(
                "INSERT INTO series (id, season_id, name) VALUES (%s, %s, %s)",
                (series_id, sid, name),
            )
        _save_games(conn, sid, playoff_games)

    lines = [ln for t in teams for ln in t.batting + t.pitching]
    _save_lines(conn, sid, lines)
    member_by_id = {m.player_id: m for ms in members.values() for m in ms}
    played = {ln.player_id for ln in lines}
    _save_skill_history(conn, sid, [member_by_id[p] for p in played])
    _save_all_stars(conn, sid, lines, member_by_id)
    return sid


def _create_season(conn, year: int) -> str:
    sid = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO seasons (id, year, name, is_backstory) VALUES (%s, %s, %s, TRUE)",
        (sid, year, SEASON_NAME),
    )
    return sid


# ── Saving ────────────────────────────────────────────────────────────────────


def _save_games(conn, season_id: str, games: list[Game]) -> None:
    with conn.cursor() as cur:
        with cur.copy(
            """COPY games (id, game_date, season_id, series_id, home_team_id,
                           away_team_id, home_score, away_score, completed,
                           innings_played, line_score, winner_id)
               FROM STDIN"""
        ) as copy:
            for g in games:
                copy.write_row(
                    (
                        g.id,
                        g.game_date,
                        season_id,
                        g.series_id,
                        g.home_team_id,
                        g.away_team_id,
                        g.home_score,
                        g.away_score,
                        1,
                        g.innings_played,
                        Jsonb({"away": g.away_innings, "home": g.home_innings}),
                        g.winner_id,
                    )
                )
        with cur.copy(
            """COPY team_game_stats (game_id, team_id, runs, hits, errors, win, loss)
               FROM STDIN"""
        ) as copy:
            for g in games:
                for side in ("home", "away"):
                    tid = getattr(g, f"{side}_team_id")
                    won = int(g.winner_id == tid)
                    copy.write_row(
                        (
                            g.id,
                            tid,
                            getattr(g, f"{side}_score"),
                            getattr(g, f"{side}_hits"),
                            getattr(g, f"{side}_errors"),
                            won,
                            1 - won,
                        )
                    )


STAT_KEYS = (
    "bat_games_played",
    "bat_games_started",
    "bat_ab",
    "bat_hits",
    "bat_doubles",
    "bat_triples",
    "bat_home_runs",
    "bat_rbi",
    "bat_runs",
    "bat_walks",
    "bat_strike_outs",
    "bat_strike_outs_looking",
    "bat_hbp",
    "bat_sac_flys",
    "bat_sac_bunts",
    "bat_gdp",
    "bat_stolen_bases",
    "bat_caught_stealing",
    "pitch_games_played",
    "pitch_games_started",
    "pitch_wins",
    "pitch_losses",
    "pitch_saves",
    "pitch_outs",
    "pitch_hits",
    "pitch_runs",
    "pitch_earned_runs",
    "pitch_home_runs",
    "pitch_walks",
    "pitch_strike_outs",
    "pitch_strike_outs_looking",
    "pitch_hit_batters",
    "pitch_doubles",
    "pitch_triples",
    "pitch_wild_pitches",
    "pitch_count",
)


def _merged(lines) -> dict[tuple[str, str], dict]:
    """One row per player and team (a two-way line would be two Lines)."""
    out: dict[tuple[str, str], dict] = {}
    for ln in lines:
        row = out.setdefault((ln.player_id, ln.team_id), {})
        for k, v in ln.stats.items():
            if not k.startswith("_"):
                row[k] = row.get(k, 0) + v
    return out


def _save_lines(conn, season_id: str, lines) -> None:
    cols = ", ".join(STAT_KEYS)
    with conn.cursor() as cur:
        with cur.copy(
            f"""COPY player_season_stats
                    (player_id, season_id, team_id, is_postseason, {cols})
                FROM STDIN"""
        ) as copy:
            for (pid, tid), row in _merged(lines).items():
                copy.write_row(
                    (
                        pid,
                        season_id,
                        tid,
                        False,
                        *(int(row.get(k, 0)) for k in STAT_KEYS),
                    )
                )


def _save_skill_history(conn, season_id: str, members: list[Member]) -> None:
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with conn.cursor() as cur:
        with cur.copy(
            f"""COPY player_skills_history
                    (player_id, season_id, age, {", ".join(SKILL_COLUMNS)}, recorded_at)
                FROM STDIN"""
        ) as copy:
            for m in members:
                copy.write_row(
                    (
                        m.player_id,
                        season_id,
                        m.age,
                        *(int(round(m.skills[c])) for c in SKILL_COLUMNS),
                        now,
                    )
                )


def _save_retirees(conn, league_id: str, retirees: list[Career]) -> None:
    players = PlayerRepository(conn)
    status = PlayerStatusRepository(conn)
    for r in retirees:
        players.insert(
            id=r.player_id,
            first_name=r.first_name,
            last_name=r.last_name,
            bats=r.bats,
            throws=r.throws,
            position=r.position,
            skills=PlayerSkills(r.final_skills, age=r.age_now),
            league_id=league_id,
        )
        status.set_status(r.player_id, "retired", datetime.date(r.retired_after, 11, 1))


def _save_all_stars(conn, season_id: str, lines, member_by_id: dict) -> None:
    """The season's All-Stars, picked the way the real vote's stat ballot
    picks them (src/league/all_star.py), from full-season lines."""
    cands = []
    for (pid, tid), row in _merged(lines).items():
        m = member_by_id[pid]
        slot_line = next(
            ln for ln in lines if ln.player_id == pid and ln.team_id == tid
        )
        pos = slot_line.slot
        c = {k: int(row.get(k, 0)) for k in all_star_columns()}
        c.update(
            player_id=pid,
            team_id=tid,
            age=m.age,
            speed=m.skills["speed"],
            power=m.skills["power"],
            contact=m.skills["contact"],
            start_position=pos if pos in all_star.FIELD_SLOTS + ("dh",) else None,
            starts=int(row.get("bat_games_started", 0)),
            offense=m.ratings["overall_offense"],
            talent=max(m.ratings["sp"], m.ratings["rp"]),
            ratings=m.ratings,
        )
        cands.append(c)
    ballot = all_star.add_features(all_star.on_ballot(cands, SEASON_LENGTH))
    pool = all_star.select_pool(ballot, {})
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO all_stars (season_id, player_id, team_id, slot,
                                      points, wildcard, score)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            [
                (
                    season_id,
                    r["player_id"],
                    r["team_id"],
                    r["slot"],
                    r["points"],
                    r["wildcard"],
                    r["score"],
                )
                for r in pool
            ],
        )


def all_star_columns() -> tuple[str, ...]:
    from src.db.repositories.all_star_repo import _STAT_COLUMNS

    return _STAT_COLUMNS
