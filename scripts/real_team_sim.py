"""
Drop real team-seasons into a fresh 30-team league and play a season.

Spike for docs/brainstorming/skill_mapping_from_stats.md. Takes the JSON that
scripts/real_rosters.py writes, starts a Speed Blitz league the way
scripts/calibrate_backstory.py does, and after the draft turns three AI
teams' major league rosters into the real clubs: each 26-man hitter becomes
one of the real club's top hitters by playing time, each pitcher one of its
top pitchers (names, handedness, age, affinity position and skills). Then it
re-seeds those teams' rotations and bullpens and plays the regular season.

    DATABASE_URL=postgresql://... uv run python -m scripts.real_team_sim \\
        --rosters rosters.json [--out result.json]

Use a scratch database.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import uuid
from pathlib import Path

from src.db.connection import get_connection

SKILLS = (
    "durability clutch speed power eye contact base_running bunting catching "
    "infield outfield arm accuracy stamina recovery ground_balls strikes"
).split()


def start(conn) -> tuple[str, str, str]:
    from src.api.services.draft_execute import execute_blitz_draft
    from src.api.services.league_start import start_league
    from src.db.repositories.draft_repo import DraftRepository
    from src.db.repositories.gm_repo import GMRepository
    from src.db.repositories.league_repo import LeagueRepository
    from src.db.repositories.season_repo import SeasonRepository

    league_id = str(uuid.uuid4())
    LeagueRepository(conn).create_new_league(
        league_id,
        "Real teams test",
        uuid.uuid4().hex[:6],
        "speed_blitz",
        None,
        {"num_teams": 30, "backstory_years": 0},
    )
    GMRepository(conn).create_gm(league_id, "Watcher")
    conn.commit()
    with contextlib.redirect_stdout(io.StringIO()):
        start_league(league_id, conn)
        conn.commit()
        draft = DraftRepository(conn).get_current_for_league(league_id)
        execute_blitz_draft(draft["id"], conn)
        conn.commit()
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    year = conn.execute(
        "SELECT game_date FROM games WHERE season_id = %s ORDER BY game_date LIMIT 1",
        (season_id,),
    ).fetchone()["game_date"][:4]
    return league_id, season_id, year


def active(conn, team_id: str) -> list[dict]:
    return conn.execute(
        """SELECT p.id, p.position FROM team_players tp
           JOIN players p ON p.id = tp.player_id
           JOIN player_status s ON s.player_id = p.id
           WHERE tp.team_id = %s AND s.status = '26man'""",
        (team_id,),
    ).fetchall()


def become(conn, player_id: str, real: dict) -> None:
    first, _, last = real["name"].partition(" ")
    conn.execute(
        """UPDATE players SET first_name=%s, last_name=%s, bats=%s, throws=%s,
           position=%s WHERE id=%s""",
        (first, last or first, real["bats"], real["throws"], real["pos"], player_id),
    )
    sets = ", ".join(f"{s}=%s" for s in SKILLS)
    conn.execute(
        f"UPDATE player_skills SET age=%s, {sets} WHERE player_id=%s",
        (real["age"], *[real["skills"][s] for s in SKILLS], player_id),
    )
    conn.execute(
        f"UPDATE player_skill_fractions SET {', '.join(f'{s}=0' for s in SKILLS)} "
        "WHERE player_id=%s",
        (player_id,),
    )


def swap_in(conn, league_id, season_id, year, rosters: dict) -> dict:
    from src.db.repositories.gm_repo import GMRepository
    from src.league.rotation_seeder import seed_ai_rotations

    human = GMRepository(conn).get_human_team_ids(league_id)
    teams = conn.execute(
        """SELECT t.id, t.city, t.mascot FROM league_season_teams lst
           JOIN teams t ON t.id = lst.team_id WHERE lst.season_id = %s
           ORDER BY t.city""",
        (season_id,),
    ).fetchall()
    targets = [t for t in teams if t["id"] not in human][: len(rosters)]
    mapping = {}
    starters: dict[str, list[str]] = {}
    for team, (title, data) in zip(targets, rosters.items()):
        players = data["players"] if "players" in data else data
        hit = [p for p in players if p["pos"] not in ("sp", "rp")]
        pit = [p for p in players if p["pos"] in ("sp", "rp")]
        mine = active(conn, team["id"])
        my_hit = [p["id"] for p in mine if p["position"] not in ("sp", "rp")]
        my_pit = [p["id"] for p in mine if p["position"] in ("sp", "rp")]
        # Use the real club's split; move extras to the other side if the
        # drafted roster was lopsided.
        need_h, need_p = min(len(hit), 13), min(len(pit), 13)
        slots = my_hit + my_pit
        reals = hit[:need_h] + pit[:need_p]
        for pid, real in zip(slots, reals):
            become(conn, pid, real)
        # Only the nickname changes: the city drives region and climate.
        y, _, nick = title.partition(" ")
        conn.execute(
            "UPDATE teams SET mascot=%s WHERE id=%s",
            (f"{y} {nick.rsplit(' ', 1)[-1]}", team["id"]),
        )
        mapping[team["id"]] = title
        # Real starters start, in order of innings (the roster's order).
        starters[team["id"]] = [
            pid for pid, real in zip(slots, reals) if real["pos"] == "sp"
        ][:5]
    conn.commit()
    seed_ai_rotations(
        conn,
        season_id,
        set(mapping),
        statuses=["26man"],
        effective_date=f"{year}-04-01",
        league_id=league_id,
    )
    set_real_rotations(conn, league_id, season_id, year, starters)
    conn.commit()
    return mapping


def set_real_rotations(conn, league_id, season_id, year, starters) -> None:
    """The seeder ranks every pitcher by SP rating, which can put a real
    reliever in the rotation. Use the club's real starters instead."""
    from src.db.repositories.bullpen_roles_repo import BullpenRepository
    from src.db.repositories.player_repo import PlayerRepository
    from src.db.repositories.team_repo import TeamRepository
    from src.db.repositories.team_rotations_repo import TeamRotationsRepository

    players = PlayerRepository(conn)
    teams = {t.id: t for t in TeamRepository(conn).get_teams_by_season(season_id)}
    for team_id, rotation in starters.items():
        TeamRotationsRepository(conn, league_id).replace_rotation(
            team_id=team_id,
            season_id=season_id,
            player_ids=rotation,
            effective_date=f"{year}-04-01",
            next_order=1,
        )
        staff = [p for p in active(conn, team_id) if p["position"] in ("sp", "rp")]
        relievers = [
            r
            for p in staff
            if p["id"] not in rotation and (r := players.look_up(p["id"]))
        ]
        roles = teams[team_id].set_bullpen_roles(rotation, relievers=relievers)
        if roles:
            BullpenRepository(conn).set_roles(
                team_id, season_id, roles, f"{year}-04-01"
            )


def play(conn, league_id: str, season_id: str) -> None:
    from src.api.services.sim_next import sim_days
    from src.db.repositories.games_repo import GameRepository

    games = GameRepository(conn)
    with contextlib.redirect_stdout(io.StringIO()):
        for _ in range(60):
            if not games.games_remaining(season_id):
                break
            sim_days(league_id, conn, "season")
            conn.commit()


def standings(conn, season_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT t.id, t.city, t.mascot,
             SUM(CASE WHEN g.winner_id = t.id THEN 1 ELSE 0 END) w,
             SUM(CASE WHEN g.winner_id <> t.id THEN 1 ELSE 0 END) l,
             SUM(CASE WHEN g.home_team_id = t.id THEN g.home_score ELSE g.away_score END) rs,
             SUM(CASE WHEN g.home_team_id = t.id THEN g.away_score ELSE g.home_score END) ra
           FROM teams t JOIN games g ON (g.home_team_id = t.id OR g.away_team_id = t.id)
           WHERE g.season_id = %s AND g.series_id IS NULL AND g.completed = 1
           GROUP BY t.id, t.city, t.mascot ORDER BY w DESC""",
        (season_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def player_lines(conn, season_id: str, team_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT p.first_name || ' ' || p.last_name AS name, p.position,
             SUM(bat_ab) ab, SUM(bat_hits) h, SUM(bat_doubles) d, SUM(bat_triples) t,
             SUM(bat_home_runs) hr, SUM(bat_walks) bb, SUM(bat_hbp) hbp,
             SUM(bat_sac_flys) sf, SUM(bat_strike_outs) so, SUM(bat_stolen_bases) sb,
             SUM(pitch_game_started) gs, SUM(pitch_outs) outs, SUM(pitch_earned_runs) er,
             SUM(pitch_strike_outs) k, SUM(pitch_walks) pbb, SUM(pitch_win) w,
             SUM(pitch_loss) l, SUM(pitch_save) sv
           FROM player_game_stats s JOIN games g ON g.id = s.game_id
           JOIN players p ON p.id = s.player_id
           WHERE g.season_id = %s AND g.series_id IS NULL AND s.team_id = %s
           GROUP BY p.id, p.first_name, p.last_name, p.position""",
        (season_id, team_id),
    ).fetchall()
    out = []
    for r in rows:
        r = {
            k: (v or 0) if k not in ("name", "position") else v
            for k, v in dict(r).items()
        }
        pa = r["ab"] + r["bb"] + r["hbp"] + r["sf"]
        if pa:
            r["avg"] = r["h"] / r["ab"] if r["ab"] else 0
            r["obp"] = (r["h"] + r["bb"] + r["hbp"]) / pa
            tb = r["h"] + r["d"] + 2 * r["t"] + 3 * r["hr"]
            r["slg"] = tb / r["ab"] if r["ab"] else 0
        r["pa"] = pa
        if r["outs"]:
            r["ip"] = r["outs"] / 3
            r["era"] = 27 * r["er"] / r["outs"]
        out.append(r)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rosters", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    rosters = json.loads(args.rosters.read_text())
    conn = get_connection()
    from src.db.init import init_db

    init_db(conn)
    league_id, season_id, year = start(conn)
    mapping = swap_in(conn, league_id, season_id, year, rosters)
    play(conn, league_id, season_id)
    table = standings(conn, season_id)
    result = {"standings": table, "teams": {}}
    for i, row in enumerate(table, 1):
        mark = " <==" if row["id"] in mapping else ""
        print(
            f"{i:2} {row['city']} {row['mascot']:12} {row['w']}-{row['l']} "
            f"RS {row['rs']} RA {row['ra']}{mark}"
        )
    for team_id, title in mapping.items():
        result["teams"][title] = {
            "id": team_id,
            "players": player_lines(conn, season_id, team_id),
        }
    if args.out:
        args.out.write_text(json.dumps(result, indent=1, default=float))


if __name__ == "__main__":
    main()
