# scripts/league_stat_check.py
"""
Compare the engine's league-wide stats with recent MLB averages.

Plays fresh 30-team Speed Blitz seasons (the same setup as
scripts/calibrate_backstory.py) and prints league totals per game and per
plate appearance next to MLB's 2022-2024 averages. Re-run it after changing
anything in src/game/probabilities.py or the pitch / in-play modifiers.

    # play 2 fresh seasons, then report on them
    DATABASE_URL=postgresql://... uv run python -m scripts.league_stat_check --sim 2

    # report on regular seasons already in the database
    DATABASE_URL=postgresql://... uv run python -m scripts.league_stat_check

Use a scratch database: --sim creates leagues and plays full seasons.
"""

from __future__ import annotations

import argparse

from src.db.connection import get_connection

# MLB 2023-2025 regular-season averages, rounded (per team per game unless
# noted). The pitch-clock era: more steals, slightly more offense than 2022.
MLB = {
    "R/G": 4.49,
    "H/G": 8.25,
    "2B/G": 1.65,
    "3B/G": 0.14,
    "HR/G": 1.16,
    "BB/G": 3.20,
    "SO/G": 8.55,
    "SB/G": 0.72,
    "CS/G": 0.18,
    "E/G": 0.52,
    "GIDP/G": 0.72,
    "SF/G": 0.24,
    "SH/G": 0.07,
    "HBP/G": 0.44,
    "WP/G": 0.31,
    "PA/G": 38.1,
    "P/PA": 3.89,
    "AVG": 0.245,
    "OBP": 0.316,
    "SLG": 0.406,
    "OPS": 0.722,
    "BABIP": 0.292,
    "K%": 22.5,
    "BB%": 8.4,
    "HR%": 3.05,
    "ERA": 4.19,
    "SB%": 80.0,
    "CG%": 0.6,
}


def played_seasons(conn) -> list[str]:
    rows = conn.execute(
        """SELECT s.id FROM seasons s
           WHERE NOT s.is_backstory AND EXISTS (SELECT 1 FROM games g WHERE g.season_id = s.id
                         AND g.series_id IS NULL)
             AND NOT EXISTS (SELECT 1 FROM games g WHERE g.season_id = s.id
                             AND g.series_id IS NULL AND g.completed = 0)"""
    ).fetchall()
    return [r["id"] for r in rows]


def league_stats(conn, season_ids: list[str]) -> dict:
    t = conn.execute(
        """SELECT SUM(bat_ab) ab, SUM(bat_hits) h, SUM(bat_doubles) d,
                  SUM(bat_triples) tr, SUM(bat_home_runs) hr, SUM(bat_walks) bb,
                  SUM(bat_strike_outs) so, SUM(bat_hbp) hbp, SUM(bat_sac_flys) sf,
                  SUM(bat_sac_bunts) sh, SUM(bat_gdp) gdp,
                  SUM(bat_stolen_bases) sb, SUM(bat_caught_stealing) cs,
                  SUM(bat_runs) r, SUM(pitch_outs) outs,
                  SUM(pitch_earned_runs) er, SUM(pitch_count) pitches,
                  SUM(pitch_wild_pitches) wp, SUM(pitch_complete_games) cg,
                  SUM(pitch_games_started) gs, SUM(field_errors) e
           FROM player_season_stats
           WHERE season_id = ANY(%s) AND NOT is_postseason""",
        (season_ids,),
    ).fetchone()
    g = conn.execute(
        """SELECT COUNT(*) n FROM team_game_stats t JOIN games g ON g.id = t.game_id
           WHERE g.season_id = ANY(%s) AND g.series_id IS NULL AND g.completed = 1""",
        (season_ids,),
    ).fetchone()["n"]
    t = {k: float(v or 0) for k, v in t.items()}
    pa = t["ab"] + t["bb"] + t["hbp"] + t["sf"] + t["sh"]
    singles = t["h"] - t["d"] - t["tr"] - t["hr"]
    tb = singles + 2 * t["d"] + 3 * t["tr"] + 4 * t["hr"]
    avg = t["h"] / t["ab"]
    obp = (t["h"] + t["bb"] + t["hbp"]) / (t["ab"] + t["bb"] + t["hbp"] + t["sf"])
    slg = tb / t["ab"]
    return {
        "R/G": t["r"] / g,
        "H/G": t["h"] / g,
        "2B/G": t["d"] / g,
        "3B/G": t["tr"] / g,
        "HR/G": t["hr"] / g,
        "BB/G": t["bb"] / g,
        "SO/G": t["so"] / g,
        "SB/G": t["sb"] / g,
        "CS/G": t["cs"] / g,
        "E/G": t["e"] / g,
        "GIDP/G": t["gdp"] / g,
        "SF/G": t["sf"] / g,
        "SH/G": t["sh"] / g,
        "HBP/G": t["hbp"] / g,
        "WP/G": t["wp"] / g,
        "PA/G": pa / g,
        "P/PA": t["pitches"] / pa,
        "AVG": avg,
        "OBP": obp,
        "SLG": slg,
        "OPS": obp + slg,
        "BABIP": (t["h"] - t["hr"]) / (t["ab"] - t["so"] - t["hr"] + t["sf"]),
        "K%": 100 * t["so"] / pa,
        "BB%": 100 * t["bb"] / pa,
        "HR%": 100 * t["hr"] / pa,
        "ERA": 27 * t["er"] / t["outs"],
        "SB%": 100 * t["sb"] / max(1, t["sb"] + t["cs"]),
        "CG%": 100 * t["cg"] / max(1, t["gs"]),
        "_team_games": g,
    }


def report(stats: dict) -> str:
    lines = [f"{'stat':<8}{'sim':>9}{'MLB':>9}{'diff':>9}"]
    for k, mlb in MLB.items():
        v = stats[k]
        fmt = ".3f" if k in ("AVG", "OBP", "SLG", "OPS", "BABIP") else ".2f"
        pct = 100 * (v - mlb) / mlb
        lines.append(f"{k:<8}{v:>9{fmt}}{mlb:>9{fmt}}{pct:>+8.0f}%")
    lines.append(f"({stats['_team_games']:.0f} team games)")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--sim", type=int, default=0, help="Seasons to play first.")
    args = p.parse_args()

    conn = get_connection()
    from src.db.init import init_db
    from scripts.calibrate_backstory import sim_season
    from src.db.repositories.season_repo import SeasonRepository

    init_db(conn)
    new = []
    for i in range(args.sim):
        print(f"Playing season {i + 1} of {args.sim}...", flush=True)
        league_id = sim_season(conn)
        new.append(SeasonRepository(conn).get_current_id_for_league(league_id))
    seasons = new or played_seasons(conn)
    if not seasons:
        raise SystemExit("No completed regular seasons. Try --sim 1.")
    print(report(league_stats(conn, seasons)))


if __name__ == "__main__":
    main()
