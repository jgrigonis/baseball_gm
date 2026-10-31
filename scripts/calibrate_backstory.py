# scripts/calibrate_backstory.py
"""
Fit the numbers the league backstory (src/league/backstory/) uses to turn
ratings into stat lines, from seasons the real game engine played.

The backstory never runs the engine: it generates past seasons from these
coefficients instead (plans/league-backstory.md). Re-run this whenever the
engine, or what a rating number means, changes, so the made-up seasons keep
looking like real ones:

    # sim 3 fresh 30-team seasons, fit, and rewrite the coefficients file
    DATABASE_URL=postgresql://... uv run python -m scripts.calibrate_backstory --sim 3

    # fit from the regular seasons already in the database
    DATABASE_URL=postgresql://... uv run python -m scripts.calibrate_backstory

Use a scratch database: --sim creates leagues and plays full seasons (about
four minutes each). The fit only reads completed regular seasons (no
playoff games) that are not themselves backstory.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
import pprint
import uuid
from pathlib import Path

import numpy as np

from src.db.connection import get_connection

OUT = Path(__file__).resolve().parent.parent / "src/league/backstory/calibration.py"

BAT_SKILLS = ["contact", "power", "eye", "speed", "base_running", "clutch", "bunting"]
PIT_SKILLS = ["accuracy", "strikes", "ground_balls", "stamina", "recovery", "clutch"]

# Batting events, as rates per plate appearance.
BAT_EVENTS = [
    "singles",
    "doubles",
    "triples",
    "home_runs",
    "walks",
    "hbp",
    "strike_outs",
    "sac_flys",
    "sac_bunts",
    "gdp",
    "stolen_bases",
    "caught_stealing",
]
# Pitching events, as rates per batter faced.
PIT_EVENTS = [
    "singles",
    "doubles",
    "triples",
    "home_runs",
    "walks",
    "hit_batters",
    "strike_outs",
    "wild_pitches",
]

# Standard linear weights (runs per event), scaled by one fitted factor.
LINEAR_WEIGHTS = {
    "singles": 0.47,
    "doubles": 0.77,
    "triples": 1.04,
    "home_runs": 1.40,
    "walks": 0.33,
    "hbp": 0.34,
    "stolen_bases": 0.20,
    "caught_stealing": -0.40,
}

MIN_PA = 30
MIN_BF = 30


# ── Simulating seasons ────────────────────────────────────────────────────────


def sim_season(conn) -> str:
    """Start a fresh 30-team Speed Blitz league and play its regular season.
    Returns the league id."""
    from src.api.services.draft_execute import execute_blitz_draft
    from src.api.services.league_start import start_league
    from src.api.services.sim_next import sim_days
    from src.db.repositories.draft_repo import DraftRepository
    from src.db.repositories.games_repo import GameRepository
    from src.db.repositories.gm_repo import GMRepository
    from src.db.repositories.league_repo import LeagueRepository
    from src.db.repositories.season_repo import SeasonRepository

    league_id = str(uuid.uuid4())
    LeagueRepository(conn).create_new_league(
        league_id,
        "Backstory calibration",
        uuid.uuid4().hex[:6],
        "speed_blitz",
        None,
        {"num_teams": 30, "backstory_years": 0},
    )
    GMRepository(conn).create_gm(league_id, "Calibration")
    conn.commit()
    with contextlib.redirect_stdout(io.StringIO()):
        start_league(league_id, conn)
        conn.commit()
        draft = DraftRepository(conn).get_current_for_league(league_id)
        execute_blitz_draft(draft["id"], conn)
        conn.commit()
        season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
        games = GameRepository(conn)
        for _ in range(50):  # the sim stops at the deadline, the break, ...
            if not games.games_remaining(season_id):
                break
            sim_days(league_id, conn, "season")
            conn.commit()
    return league_id


# ── Reading played seasons ────────────────────────────────────────────────────


def played_seasons(conn) -> list[str]:
    """Regular seasons the engine finished (every scheduled game played)."""
    rows = conn.execute(
        """SELECT s.id FROM seasons s
           WHERE NOT s.is_backstory
             AND EXISTS (SELECT 1 FROM games g
                         WHERE g.season_id = s.id AND g.series_id IS NULL)
             AND NOT EXISTS (SELECT 1 FROM games g
                             WHERE g.season_id = s.id AND g.series_id IS NULL
                               AND g.completed = 0)"""
    ).fetchall()
    return [r["id"] for r in rows]


def season_lines(conn, season_id: str) -> list[dict]:
    """Every regular-season stat line with the player's skills that season
    (the history row when he has aged since, else his current skills)."""
    return conn.execute(
        """SELECT pss.*, p.position,
                  COALESCE(h.contact, sk.contact) AS contact,
                  COALESCE(h.power, sk.power) AS power,
                  COALESCE(h.eye, sk.eye) AS eye,
                  COALESCE(h.speed, sk.speed) AS speed,
                  COALESCE(h.base_running, sk.base_running) AS base_running,
                  COALESCE(h.clutch, sk.clutch) AS clutch,
                  COALESCE(h.bunting, sk.bunting) AS bunting,
                  COALESCE(h.accuracy, sk.accuracy) AS accuracy,
                  COALESCE(h.strikes, sk.strikes) AS strikes,
                  COALESCE(h.ground_balls, sk.ground_balls) AS ground_balls,
                  COALESCE(h.stamina, sk.stamina) AS stamina,
                  COALESCE(h.recovery, sk.recovery) AS recovery
           FROM player_season_stats pss
           JOIN players p ON p.id = pss.player_id
           JOIN player_skills sk ON sk.player_id = pss.player_id
           LEFT JOIN player_skills_history h
             ON h.player_id = pss.player_id AND h.season_id = pss.season_id
           WHERE pss.season_id = %s AND NOT pss.is_postseason""",
        (season_id,),
    ).fetchall()


def team_games(conn, season_id: str) -> list[dict]:
    """One row per team per regular-season game: runs, hits, errors, and the
    opponent's runs."""
    return conn.execute(
        """SELECT t.team_id, t.runs, t.hits, t.errors, o.runs AS opp_runs,
                  g.innings_played
           FROM team_game_stats t
           JOIN team_game_stats o ON o.game_id = t.game_id AND o.team_id <> t.team_id
           JOIN games g ON g.id = t.game_id
           WHERE g.season_id = %s AND g.series_id IS NULL AND g.completed = 1""",
        (season_id,),
    ).fetchall()


def games_by_season(conn, season_ids):
    return {sid: team_games(conn, sid) for sid in season_ids}


def team_wins_by(by_season: dict) -> list[int]:
    """Each team's regular-season wins, one per team per season."""
    out = []
    for rows in by_season.values():
        wins: dict[str, int] = {}
        for g in rows:
            wins[g["team_id"]] = wins.get(g["team_id"], 0) + (g["runs"] > g["opp_runs"])
        out += list(wins.values())
    return out


# ── Fitting ───────────────────────────────────────────────────────────────────


def bat_counts(r: dict) -> dict:
    hits = r["bat_hits"]
    xbh = r["bat_doubles"] + r["bat_triples"] + r["bat_home_runs"]
    return {
        "singles": hits - xbh,
        "doubles": r["bat_doubles"],
        "triples": r["bat_triples"],
        "home_runs": r["bat_home_runs"],
        "walks": r["bat_walks"],
        "hbp": r["bat_hbp"],
        "strike_outs": r["bat_strike_outs"],
        "sac_flys": r["bat_sac_flys"],
        "sac_bunts": r["bat_sac_bunts"],
        "gdp": r["bat_gdp"],
        "stolen_bases": r["bat_stolen_bases"],
        "caught_stealing": r["bat_caught_stealing"],
    }


def plate_appearances(r: dict) -> int:
    return (
        r["bat_ab"]
        + r["bat_walks"]
        + r["bat_hbp"]
        + r["bat_sac_flys"]
        + r["bat_sac_bunts"]
    )


def pit_counts(r: dict) -> dict:
    hits = r["pitch_hits"]
    xbh = r["pitch_doubles"] + r["pitch_triples"] + r["pitch_home_runs"]
    return {
        "singles": hits - xbh,
        "doubles": r["pitch_doubles"],
        "triples": r["pitch_triples"],
        "home_runs": r["pitch_home_runs"],
        "walks": r["pitch_walks"],
        "hit_batters": r["pitch_hit_batters"],
        "strike_outs": r["pitch_strike_outs"],
        "wild_pitches": r["pitch_wild_pitches"],
    }


def batters_faced(r: dict) -> int:
    return r["pitch_outs"] + r["pitch_hits"] + r["pitch_walks"] + r["pitch_hit_batters"]


def wls(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted least squares with an intercept: [intercept, *slopes]."""
    X = np.column_stack([np.ones(len(x)), x])
    sw = np.sqrt(w)
    coef, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    return coef


def fit_rates(lines, skills, events, counts, volume, min_volume) -> dict:
    """Per-event rate models: rate = intercept + sum(slope * skill)."""
    rows = [r for r in lines if volume(r) >= min_volume]
    x = np.array([[r[s] for s in skills] for r in rows], dtype=float)
    vol = np.array([volume(r) for r in rows], dtype=float)
    out = {}
    for ev in events:
        y = np.array([counts(r)[ev] for r in rows], dtype=float) / vol
        coef = wls(x, y, vol)
        out[ev] = {"intercept": round(float(coef[0]), 6)} | {
            s: round(float(c), 6) for s, c in zip(skills, coef[1:])
        }
    return out


def lw_runs(counts: dict) -> float:
    return sum(LINEAR_WEIGHTS[k] * counts.get(k, 0) for k in LINEAR_WEIGHTS)


def rank_table(groups: list[list[float]], n: int) -> list[float]:
    """The average k-th largest value across teams, for k = 1..n."""
    table = []
    for k in range(n):
        vals = [sorted(g, reverse=True)[k] for g in groups if len(g) > k]
        table.append(round(float(np.mean(vals)), 1) if vals else 0.0)
    return table


def fit(conn, season_ids: list[str]) -> dict:
    lines = []
    games_by = games_by_season(conn, season_ids)
    games = [g for rows in games_by.values() for g in rows]
    by_team_season: dict[tuple, list[dict]] = {}
    for sid in season_ids:
        ls = season_lines(conn, sid)
        lines += ls
        for r in ls:
            by_team_season.setdefault((sid, r["team_id"]), []).append(r)

    bat = fit_rates(
        lines, BAT_SKILLS, BAT_EVENTS, bat_counts, plate_appearances, MIN_PA
    )
    pit = fit_rates(lines, PIT_SKILLS, PIT_EVENTS, pit_counts, batters_faced, MIN_BF)

    # Team runs against linear weights of the team's batting (and pitching)
    team_rs, team_ra, lw_bat, lw_pit = [], [], [], []
    rs_by = {}
    ra_by = {}
    for sid, rows in games_by.items():
        for g in rows:
            rs_by[(sid, g["team_id"])] = rs_by.get((sid, g["team_id"]), 0) + g["runs"]
            ra_by[(sid, g["team_id"])] = (
                ra_by.get((sid, g["team_id"]), 0) + g["opp_runs"]
            )
    for key, rows in by_team_season.items():
        if key not in rs_by:
            continue
        b, p = {}, {}
        for r in rows:
            for k, v in bat_counts(r).items():
                b[k] = b.get(k, 0) + v
            for k, v in pit_counts(r).items():
                p[k] = p.get(k, 0) + v
        p["hbp"] = p.get("hit_batters", 0)
        team_rs.append(rs_by[key])
        team_ra.append(ra_by[key])
        lw_bat.append(lw_runs(b))
        lw_pit.append(lw_runs(p))
    team_rs, team_ra = np.array(team_rs, float), np.array(team_ra, float)
    lw_bat, lw_pit = np.array(lw_bat), np.array(lw_pit)
    bat_scale = float(team_rs @ lw_bat / (lw_bat @ lw_bat))
    pit_scale = float(team_ra @ lw_pit / (lw_pit @ lw_pit))

    # Each hitter's share of runs and RBI from his own events
    hit_rows = [r for r in lines if plate_appearances(r) >= MIN_PA]
    ev = ["singles", "doubles", "triples", "home_runs", "walks", "stolen_bases"]
    X = np.array([[bat_counts(r)[k] for k in ev] for r in hit_rows], float)
    runs_coef, *_ = np.linalg.lstsq(
        X, np.array([r["bat_runs"] for r in hit_rows], float), rcond=None
    )
    rbi_coef, *_ = np.linalg.lstsq(
        X, np.array([r["bat_rbi"] for r in hit_rows], float), rcond=None
    )

    # Playing time: the k-th busiest hitter / starter / reliever on a team
    pa_groups, gs_groups, rp_g, rp_outs, sv_groups, hd_groups = [], [], [], [], [], []
    sp_outs, g_per_pa = [], []
    for rows in by_team_season.values():
        pa_groups.append([plate_appearances(r) for r in rows if plate_appearances(r)])
        starters = [r for r in rows if r["pitch_games_started"] >= 3]
        relievers = [
            r for r in rows if r["pitch_games_played"] and r["pitch_games_started"] < 3
        ]
        gs_groups.append([r["pitch_games_started"] for r in starters])
        sp_outs += [r["pitch_outs"] / r["pitch_games_started"] for r in starters]
        rp_g.append([r["pitch_games_played"] for r in relievers])
        rp_outs.append([r["pitch_outs"] for r in relievers])
        sv_groups.append([r["pitch_saves"] for r in rows if r["pitch_saves"]])
        hd_groups.append([r["pitch_holds"] for r in rows if r["pitch_holds"]])
        for r in rows:
            pa = plate_appearances(r)
            if pa >= MIN_PA:
                g_per_pa.append((pa, r["bat_games_played"], r["bat_games_started"]))
    pa_arr = np.array([p for p, _, _ in g_per_pa], float)
    g_coef = np.polyfit(pa_arr, [g for _, g, _ in g_per_pa], 1)
    gs_coef = np.polyfit(pa_arr, [gs for _, _, gs in g_per_pa], 1)

    # Decisions: share of team wins and losses that go to starters
    sp_w = sum(r["pitch_wins"] for r in lines if r["pitch_games_started"] >= 3)
    sp_l = sum(r["pitch_losses"] for r in lines if r["pitch_games_started"] >= 3)
    all_w = sum(r["pitch_wins"] for r in lines) or 1
    all_l = sum(r["pitch_losses"] for r in lines) or 1
    starts = sum(r["pitch_games_started"] for r in lines) or 1

    # Per game: runs spread, hits and errors around runs, extra innings
    runs = np.array([g["runs"] for g in games], float)
    hits = np.array([g["hits"] for g in games], float)
    errs = np.array([g["errors"] or 0 for g in games], float)
    h_coef = np.polyfit(runs, hits, 1)
    h_resid = hits - np.polyval(h_coef, runs)

    k_look_bat = sum(r["bat_strike_outs_looking"] for r in lines) / max(
        1, sum(r["bat_strike_outs"] for r in lines)
    )
    er_share = sum(r["pitch_earned_runs"] for r in lines) / max(
        1, sum(r["pitch_runs"] for r in lines)
    )
    rbi_per_run = sum(r["bat_rbi"] for r in lines) / max(
        1, sum(r["bat_runs"] for r in lines)
    )
    team_wins = team_wins_by(games_by)
    pitches_per_bf = sum(r["pitch_count"] for r in lines) / max(
        1, sum(batters_faced(r) for r in lines)
    )

    return {
        "seasons_fitted": len(season_ids),
        "bat_skills": BAT_SKILLS,
        "pit_skills": PIT_SKILLS,
        "bat_rates": bat,
        "pit_rates": pit,
        "linear_weights": LINEAR_WEIGHTS,
        "bat_run_scale": round(bat_scale, 4),
        "pit_run_scale": round(pit_scale, 4),
        "runs_from_events": dict(zip(ev, (round(float(c), 4) for c in runs_coef))),
        "rbi_from_events": dict(zip(ev, (round(float(c), 4) for c in rbi_coef))),
        "hitter_pa_by_rank": rank_table(pa_groups, 16),
        "starter_gs_by_rank": rank_table(gs_groups, 8),
        "starter_outs_per_start": round(float(np.mean(sp_outs)), 2),
        "reliever_games_by_rank": rank_table(rp_g, 10),
        "reliever_outs_by_rank": rank_table(rp_outs, 10),
        "saves_by_rank": rank_table(sv_groups, 4),
        "holds_by_rank": rank_table(hd_groups, 6),
        "games_from_pa": [round(float(c), 4) for c in g_coef],
        "starts_from_pa": [round(float(c), 4) for c in gs_coef],
        "starter_win_share": round(sp_w / all_w, 3),
        "starter_loss_share": round(sp_l / all_l, 3),
        "starts_per_team_game": round(starts / max(1, len(games)), 3),
        "runs_per_game": round(float(runs.mean()), 3),
        "runs_per_game_var": round(float(runs.var()), 3),
        "hits_from_runs": [round(float(c), 4) for c in h_coef],
        "hits_noise_sd": round(float(h_resid.std()), 3),
        "errors_per_game": round(float(errs.mean()), 3),
        "strike_outs_looking_share": round(k_look_bat, 3),
        "earned_run_share": round(er_share, 3),
        "rbi_per_run": round(rbi_per_run, 3),
        "team_wins_sd": round(float(np.std(team_wins)), 2),
        "pitches_per_batter": round(pitches_per_bf, 3),
    }


HEADER = '''# src/league/backstory/calibration.py
"""
Coefficients for the league backstory, fitted from seasons the game engine
played. Generated by scripts/calibrate_backstory.py; don't edit by hand,
re-run the script instead (it says when).
"""

'''


def write(params: dict) -> None:
    body = pprint.pformat(params, width=88, sort_dicts=False)
    OUT.write_text(HEADER + f"PARAMS = {body}\n")
    print(f"Wrote {OUT}")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--sim", type=int, default=0, help="Seasons to play first.")
    p.add_argument("--dry-run", action="store_true", help="Print, don't write.")
    args = p.parse_args()

    logging.disable(logging.CRITICAL)
    conn = get_connection()
    from src.db.init import init_db

    init_db(conn)
    for i in range(args.sim):
        print(f"Playing season {i + 1} of {args.sim}...")
        sim_season(conn)

    seasons = played_seasons(conn)
    if not seasons:
        raise SystemExit("No completed regular seasons to fit. Try --sim 3.")
    print(f"Fitting from {len(seasons)} seasons...")
    params = fit(conn, seasons)
    if args.dry_run:
        pprint.pprint(params, sort_dicts=False)
    else:
        write(params)


if __name__ == "__main__":
    main()
