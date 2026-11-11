"""
Play an all-AI 30-team Speed Blitz league for N seasons and log, at the
start of each season, the 26-man rosters' average role rating, age and key
skills, plus the league stats of the season before. For checking whether
talent drifts over a long league (compare a run on main with a run on a
branch that changes player generation or development).

    DATABASE_URL=postgresql://... uv run python -m scripts.league_drift_check 20 out.json
    # resume a league that was interrupted:
    DATABASE_URL=... uv run python -m scripts.league_drift_check 20 out.json <league id>

Use a scratch database. About 6-11 minutes a season.
"""

import contextlib, io, json, statistics, sys, uuid
from src.db.connection import get_connection
from src.db.init import init_db
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.player_repo import PlayerRepository
from src.api.services.league_start import start_league
from src.api.services import ready_check
from src.league.offseason.draft_strategy import ratings
from scripts.league_stat_check import league_stats

N = int(sys.argv[1])
OUT = sys.argv[2]
GMRepository.get_human_gm_city_mascot = lambda self, lid: None
conn = get_connection()
init_db(conn)
RESUME = sys.argv[3] if len(sys.argv) > 3 else None
lid = RESUME or str(uuid.uuid4())
if not RESUME:
    LeagueRepository(conn).create_new_league(
        lid,
        "Drift",
        uuid.uuid4().hex[:6],
        "speed_blitz",
        None,
        {"num_teams": 30, "backstory_years": 0, "num_seasons": 25},
    )
    conn.commit()
    with contextlib.redirect_stdout(io.StringIO()):
        start_league(lid, conn)
        conn.commit()


def snapshot():
    rows = conn.execute(
        """SELECT ps.player_id, ps.status FROM player_status ps JOIN players p ON p.id = ps.player_id
                           WHERE p.league_id = %s AND ps.status IN ('26man','40man')""",
        (lid,),
    ).fetchall()
    st = {r["player_id"]: r["status"] for r in rows}
    players = [
        p for p in PlayerRepository(conn).get_players_by_league(lid) if p.id in st
    ]
    out = {}
    for tier in ("26man", "40man"):
        ps = [p for p in players if st[p.id] == tier or tier == "40man"]
        hit = [p for p in ps if not p.is_pitcher()]
        pit = [p for p in ps if p.is_pitcher()]
        if not hit:
            continue
        out[tier] = {
            "n": len(ps),
            "hit": statistics.mean(ratings(p)["overall_player"] for p in hit),
            "pit": statistics.mean(
                max(ratings(p)["sp"], ratings(p)["rp"]) for p in pit
            ),
            "age": statistics.mean(p.age for p in ps),
            "hit_skills": {
                k: statistics.mean(p.skills.as_dict()[k] for p in hit)
                for k in ("contact", "power", "eye", "speed")
            },
            "pit_skills": {
                k: statistics.mean(p.skills.as_dict()[k] for p in pit)
                for k in ("strikes", "accuracy", "ground_balls", "stamina")
            },
        }
    return out


log = []
seen = None
seasons = 0
prev = None
if RESUME:
    log = json.load(open(OUT))
    seen = prev = SeasonRepository(conn).get_current_id_for_league(lid)
    seasons = len(log)
for step in range(100000):
    sid = SeasonRepository(conn).get_current_id_for_league(lid)
    if sid != seen:
        rec = {"season": seasons, "talent": snapshot()}
        if prev:
            try:
                rec["prev_stats"] = {
                    k: v
                    for k, v in league_stats(conn, [prev]).items()
                    if k in ("R/G", "HR/G", "AVG", "OBP", "SLG", "ERA", "K%", "BB%")
                }
            except Exception as e:
                rec["prev_stats"] = str(e)
        log.append(rec)
        json.dump(log, open(OUT, "w"), indent=1, default=str)
        print(json.dumps(rec, default=str)[:400], flush=True)
        if seasons == N:
            break
        prev, seen = sid, sid
        seasons += 1
    state = LeagueRepository(conn).get_state(lid)
    with contextlib.redirect_stdout(io.StringIO()):
        ready_check._run_period(conn, lid, state, 30)
    conn.commit()
