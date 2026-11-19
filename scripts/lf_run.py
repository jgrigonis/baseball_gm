"""Play an all-AI 30-team Long Form league for N seasons; after each regular
season+postseason, dump league-wide stats for the season just finished.

    DATABASE_URL=... python lf_run.py 25 out.json [league_id]
"""

import contextlib, io, json, statistics, sys, time, uuid
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
MODE = sys.argv[4] if len(sys.argv) > 4 else "longform"
GMRepository.get_human_gm_city_mascot = lambda self, lid: None
conn = get_connection()
init_db(conn)
RESUME = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else None
lid = RESUME or str(uuid.uuid4())
if not RESUME:
    LeagueRepository(conn).create_new_league(
        lid,
        "MLBCheck",
        uuid.uuid4().hex[:6],
        MODE,
        None,
        {
            "num_teams": 30,
            "backstory_years": 0,
            "num_seasons": 25,
            "sim_period_days": 30,
            "injuries_enabled": True,
            "trades_enabled": True,
            "pace_control": "confirmed",
        },
    )
    conn.commit()
    with contextlib.redirect_stdout(io.StringIO()):
        start_league(lid, conn)
        conn.commit()
print("league", lid, flush=True)


def q1(sql, args):
    r = conn.execute(sql, args).fetchone()
    return {k: float(v or 0) for k, v in r.items()}


def extra(sid):
    g = "g.season_id = %s AND g.series_id IS NULL AND g.completed = 1"
    out = {}
    # pitcher usage from per-game lines
    r = q1(
        f"""SELECT COUNT(*) FILTER (WHERE pitch_game_started=1) gs,
                 SUM(pitch_outs) FILTER (WHERE pitch_game_started=1) so_outs,
                 SUM(pitch_count) FILTER (WHERE pitch_game_started=1) sp_pitches,
                 COUNT(*) FILTER (WHERE pitch_game_started=1 AND pitch_outs>=18) six,
                 COUNT(*) FILTER (WHERE pitch_game_started=1 AND pitch_outs>=18 AND pitch_earned_runs<=3) qs,
                 COUNT(*) FILTER (WHERE pitch_game_started=1 AND pitch_outs<15) short,
                 COUNT(*) FILTER (WHERE pitch_game_started=1 AND pitch_count>=100) p100,
                 COUNT(*) FILTER (WHERE pitch_game_played=1 AND pitch_game_started=0) relief_apps,
                 SUM(pitch_outs) FILTER (WHERE pitch_game_played=1 AND pitch_game_started=0) rp_outs,
                 SUM(pitch_outs) tot_outs,
                 COUNT(*) FILTER (WHERE pitch_game_played=0 AND bat_game_played=1 AND bat_game_started=0) sub_apps,
                 COUNT(*) FILTER (WHERE pitch_game_played=0 AND bat_game_played=1 AND bat_game_started=0 AND (bat_ab+bat_walks+bat_hbp+bat_sac_flys+bat_sac_bunts)>0) sub_pa_apps,
                 SUM(catcher_interferences) ci, SUM(field_double_plays) dp, SUM(field_triple_plays) tp,
                 SUM(passed_balls) pb, SUM(pitch_balks) bk, SUM(pitch_pickoffs) pk, SUM(catcher_pickoffs) cpk,
                 SUM(pitch_save) sv, SUM(pitch_hold) hld
               FROM player_game_stats p JOIN games g ON g.id=p.game_id WHERE {g}""",
        (sid,),
    )
    tg = q1(
        f"SELECT COUNT(*) n FROM team_game_stats t JOIN games g ON g.id=t.game_id WHERE {g}",
        (sid,),
    )["n"]
    out["IP/GS"] = r["so_outs"] / 3 / r["gs"]
    out["P/GS"] = r["sp_pitches"] / r["gs"]
    out["6IP%"] = 100 * r["six"] / r["gs"]
    out["QS%"] = 100 * r["qs"] / r["gs"]
    out["<5IP%"] = 100 * r["short"] / r["gs"]
    out["100P%"] = 100 * r["p100"] / r["gs"]
    out["RP app/G"] = r["relief_apps"] / tg
    out["RP IP%"] = 100 * r["rp_outs"] / r["tot_outs"]
    out["SV/G"] = r["sv"] / tg
    out["HLD/G"] = r["hld"] / tg
    out["Sub/G"] = r["sub_apps"] / tg
    out["SubPA/G"] = r["sub_pa_apps"] / tg
    out["DP/G"] = (
        r["dp"] / 2 / tg
    )  # field_double_plays credited to ~2+ fielders; corrected below by events if possible
    out["PB/G"] = r["pb"] / tg
    out["BK/G"] = r["bk"] / tg
    out["PK/G"] = (r["pk"]) / tg
    out["CPK/G"] = r["cpk"] / tg
    # extra innings, one-run games, shutouts
    e = q1(
        f"""SELECT COUNT(*) FILTER (WHERE innings_played>9) xi, COUNT(*) FILTER (WHERE abs(home_score-away_score)=1) one,
                 COUNT(*) FILTER (WHERE home_score=0 OR away_score=0) sho, COUNT(*) n,
                 COUNT(*) FILTER (WHERE home_score>away_score) hw
               FROM games g WHERE {g}""",
        (sid,),
    )
    out["XI%"] = 100 * e["xi"] / e["n"]
    out["1run%"] = 100 * e["one"] / e["n"]
    out["ShO/G"] = e["sho"] / (2 * e["n"])
    out["Home W%"] = 100 * e["hw"] / e["n"]
    # substitution events by reason
    ev = conn.execute(
        f"""SELECT event_type, COALESCE(reason,'') reason, COUNT(*) n FROM game_events ge JOIN games g ON g.id=ge.game_id
                         WHERE {g} AND event_type IN ('substitution','pitching_change','closer_called','injury')
                         GROUP BY 1,2""",
        (sid,),
    ).fetchall()
    out["events"] = {f"{x['event_type']}:{x['reason']}": x["n"] / tg for x in ev}
    # injuries in the season (log), by severity
    inj = conn.execute(
        """SELECT COUNT(*) n, COUNT(*) FILTER (WHERE games_missed>=10) il, SUM(LEAST(games_missed,200)) days,
                            COUNT(*) FILTER (WHERE injury_type ILIKE '%%tommy%%' OR injury_type ILIKE '%%ucl%%') tj
                          FROM player_injury_log WHERE season_id=%s""",
        (sid,),
    ).fetchone()
    out["Inj/team"] = float(inj["n"] or 0) / 30
    out["Inj10+/team"] = float(inj["il"] or 0) / 30
    out["InjGames/team"] = float(inj["days"] or 0) / 30
    out["TJ"] = float(inj["tj"] or 0)
    return out


def snapshot():
    rows = conn.execute(
        """SELECT ps.player_id, ps.status FROM player_status ps JOIN players p ON p.id = ps.player_id
                           WHERE p.league_id = %s AND ps.status IN ('26man')""",
        (lid,),
    ).fetchall()
    st = {r["player_id"] for r in rows}
    ps = [p for p in PlayerRepository(conn).get_players_by_league(lid) if p.id in st]
    hit = [p for p in ps if not p.is_pitcher()]
    pit = [p for p in ps if p.is_pitcher()]
    if not hit:
        return {}
    return {
        "n": len(ps),
        "hit": statistics.mean(ratings(p)["overall_player"] for p in hit),
        "pit": statistics.mean(max(ratings(p)["sp"], ratings(p)["rp"]) for p in pit),
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


def safe(f, *a):
    try:
        return f(*a)
    except Exception as e:
        conn.rollback()
        return {"error": repr(e)}


log = json.load(open(OUT)) if RESUME else []
seen = prev = SeasonRepository(conn).get_current_id_for_league(lid) if RESUME else None
seasons = len(log)
t0 = time.time()
for step in range(1000000):
    sid = SeasonRepository(conn).get_current_id_for_league(lid)
    if sid != seen:
        rec = {
            "season": seasons,
            "t": round(time.time() - t0),
            "talent": safe(snapshot),
        }
        if prev:
            rec["stats"] = safe(league_stats, conn, [prev])
            rec["extra"] = safe(extra, prev)
        log.append(rec)
        json.dump(log, open(OUT, "w"), indent=1, default=str)
        print(
            json.dumps(
                {
                    k: rec.get("stats", {}).get(k)
                    for k in ("R/G", "AVG", "OBP", "SLG", "K%", "BB%", "ERA")
                },
                default=str,
            ),
            rec["season"],
            rec["t"],
            flush=True,
        )
        if seasons == N:
            break
        prev, seen = sid, sid
        seasons += 1
    state = LeagueRepository(conn).get_state(lid)
    with contextlib.redirect_stdout(io.StringIO()):
        ready_check._run_period(conn, lid, state, 30)
    conn.commit()
    if state == "draft":
        from src.api.services import live_draft
        from src.db.repositories.draft_repo import DraftRepository

        d = DraftRepository(conn).get_current_for_league(lid)
        if (
            live_draft.is_live(d)
            and d["state"] == "open"
            and live_draft.LiveDraft(conn, d["id"]).done
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                live_draft.finish(conn, d["id"])
            conn.execute("DELETE FROM sim_jobs WHERE league_id = %s", (lid,))
            conn.commit()
    if step % 20 == 0:
        print("step", step, state, round(time.time() - t0), flush=True)
