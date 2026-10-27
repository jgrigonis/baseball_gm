# src/api/view_models/leaders.py
#
# Context for the leaders tab: top-10 cards for batting, pitching and
# defense in one season.

from __future__ import annotations

from src.db.repositories.player_games import PlayerGameRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.season_repo import SeasonRepository
from src.stats import formulas


def leaders_context(
    db, league_id: str, season: str | None, my_team_id: str | None
) -> dict:
    """`season` is the season id the user picked, if any."""
    sr = SeasonRepository(db)
    all_seasons = sr.get_seasons_for_league(league_id)  # newest first

    # Determine which season to display: explicit param > last with completed games
    last_completed = sr.get_last_with_completed_games(league_id)
    if season and any(s["id"] == season for s in all_seasons):
        display_season = next(s for s in all_seasons if s["id"] == season)
    elif last_completed:
        display_season = last_completed
    else:
        display_season = all_seasons[0] if all_seasons else None

    season_id = display_season["id"] if display_season else None

    bat_cats = []
    pit_cats = []
    def_cats = []

    if season_id:
        pss_repo = PlayerSeasonStatsRepository(db)

        team_games = pss_repo.get_max_games_played(season_id)
        min_ab = int(3.1 * team_games)  # qualify for rate stats
        min_outs = int(3 * team_games)  # 1 IP per team game

        bat_cats = batting_leaders(
            pss_repo.get_batting_for_league(league_id, season_id), my_team_id, min_ab
        )
        pit_cats = pitching_leaders(
            pss_repo.get_pitching_for_league(league_id, season_id),
            my_team_id,
            min_outs,
        )
        def_cats = defense_leaders(
            PlayerGameRepository(db).get_league_fielding_by_position(season_id),
            my_team_id,
            team_games,
        )

    return {
        "leaders_season_id": season_id,
        "leaders_season_name": display_season["name"] if display_season else "",
        "leaders_seasons": all_seasons,
        "bat_cats": bat_cats,
        "pit_cats": pit_cats,
        "def_cats": def_cats,
    }


def batting_leaders(bat_rows: list, my_team_id: str | None, min_ab: int) -> list:
    batters = []
    for r in bat_rows:
        ab = r["bat_ab"] or 0
        h = r["bat_hits"] or 0
        d = r["bat_doubles"] or 0
        tr = r["bat_triples"] or 0
        hr = r["bat_home_runs"] or 0
        rbi = r["bat_rbi"] or 0
        runs = r["bat_runs"] or 0
        bb = r["bat_walks"] or 0
        k = r["bat_strike_outs"] or 0
        sb = r["bat_stolen_bases"] or 0
        hbp = r["bat_hbp"] or 0
        sf = r["bat_sac_flys"] or 0
        avg = formulas.batting_average(h, ab)
        obp = formulas.on_base_pct(h, bb, hbp, ab, sf)
        slg = formulas.slugging_pct(formulas.total_bases(h, d, tr, hr), ab)
        qualifies = ab >= min_ab
        ab_k = ab / k if k else 0.0
        ab_hr = ab / hr if hr else None
        bb_k = bb / k if k else None
        batters.append(
            {
                "player_id": r["player_id"],
                "name": f"{r['first_name']} {r['last_name']}",
                "team": f"{r['city']} {r['mascot']}",
                "team_id": r["team_id"],
                "is_mine": r["team_id"] == my_team_id,
                "qualifies": qualifies,
                "AVG": avg,
                "HR": hr,
                "RBI": rbi,
                "R": runs,
                "H": h,
                "SB": sb,
                "OBP": obp,
                "SLG": slg,
                "OPS": obp + slg,
                "2B": d,
                "3B": tr,
                "BB": bb,
                "K": k,
                "AB/K": ab_k,
                "AB/HR": ab_hr,
                "BB/K": bb_k,
            }
        )

    def bat_card(label, key, pool=None, asc=False, fmt=None):
        srt = sorted(
            pool if pool is not None else batters,
            key=lambda r: r[key],
            reverse=not asc,
        )[:10]
        rows = []
        for i, r in enumerate(srt, 1):
            val = r[key]
            disp = (
                fmt(val)
                if fmt
                else (
                    str(int(val))
                    if isinstance(val, float) and val == int(val)
                    else (f"{val:.3f}" if isinstance(val, float) else str(val))
                )
            )
            rows.append(
                {
                    "rank": i,
                    "name": r["name"],
                    "team": r["team"],
                    "player_id": r["player_id"],
                    "is_mine": r["is_mine"],
                    "val": disp,
                }
            )
        return {"label": label, "rows": rows}

    qualified = [b for b in batters if b["qualifies"]]
    all_bat = batters  # no AB minimum for counting stats

    def bat_card_q(label, key, pool=None, asc=False, fmt=None):
        return bat_card(label, key, pool=pool or qualified, asc=asc, fmt=fmt)

    bat_cats = [
        bat_card_q("AVG", "AVG", fmt=lambda v: f"{v:.3f}"[1:]),
        bat_card("HR", "HR", pool=all_bat),
        bat_card("RBI", "RBI", pool=all_bat),
        bat_card("R", "R", pool=all_bat),
        bat_card("H", "H", pool=all_bat),
        bat_card("SB", "SB", pool=all_bat),
        bat_card_q("OBP", "OBP", fmt=lambda v: f"{v:.3f}"[1:]),
        bat_card_q("SLG", "SLG", fmt=lambda v: f"{v:.3f}"),
        bat_card_q("OPS", "OPS", fmt=lambda v: f"{v:.3f}"),
        bat_card("2B", "2B", pool=all_bat),
        bat_card("3B", "3B", pool=all_bat),
        bat_card("BB", "BB", pool=all_bat),
        bat_card_q("AB/K", "AB/K", fmt=lambda v: f"{v:.1f}"),
        bat_card(
            "AB/HR",
            "AB/HR",
            pool=[b for b in qualified if b["AB/HR"] is not None],
            asc=True,
            fmt=lambda v: f"{v:.1f}",
        ),
        bat_card(
            "BB/K",
            "BB/K",
            pool=[b for b in qualified if b["BB/K"] is not None],
            fmt=lambda v: f"{v:.2f}",
        ),
    ]
    return bat_cats


def pitching_leaders(pit_rows: list, my_team_id: str | None, min_outs: int) -> list:
    pitchers = []
    for r in pit_rows:
        outs = r["pitch_outs"] or 0
        er = r["pitch_earned_runs"] or 0
        ph = r["pitch_hits"] or 0
        pbb = r["pitch_walks"] or 0
        pk = r["pitch_strike_outs"] or 0
        hr = r["pitch_home_runs"] or 0
        ip_f = formulas.innings(outs)
        era = formulas.era(er, outs)
        whip = formulas.whip(ph, pbb, outs)
        qualifies_p = outs >= min_outs
        bb9 = formulas.per_nine(pbb, outs)
        hr9 = formulas.per_nine(hr, outs)
        k9 = formulas.per_nine(pk, outs)
        pitchers.append(
            {
                "player_id": r["player_id"],
                "name": f"{r['first_name']} {r['last_name']}",
                "team": f"{r['city']} {r['mascot']}",
                "team_id": r["team_id"],
                "is_mine": r["team_id"] == my_team_id,
                "qualifies": qualifies_p,
                "ERA": era,
                "WHIP": whip,
                "W": r["pitch_wins"] or 0,
                "K": pk,
                "SV": r["pitch_saves"] or 0,
                "CG": r.get("pitch_complete_games") or 0,
                "SHO": r.get("pitch_shutouts") or 0,
                "IP": ip_f,
                "BB/9": bb9,
                "HR/9": hr9,
                "K/9": k9,
            }
        )

    def pit_card(label, key, pool=None, asc=False, fmt=None):
        srt = sorted(
            pool if pool is not None else pitchers,
            key=lambda r: r[key],
            reverse=not asc,
        )[:10]
        rows = []
        for i, r in enumerate(srt, 1):
            val = r[key]
            if fmt:
                disp = fmt(val)
            elif key == "IP":
                disp = formulas.ip_str(round(val * formulas.OUTS_PER_INNING))
            else:
                disp = str(int(val)) if val == int(val) else f"{val:.2f}"
            rows.append(
                {
                    "rank": i,
                    "name": r["name"],
                    "team": r["team"],
                    "player_id": r["player_id"],
                    "is_mine": r["is_mine"],
                    "val": disp,
                }
            )
        return {"label": label, "rows": rows}

    q_pit = [p for p in pitchers if p["qualifies"]]
    all_pit = pitchers

    def pit_card_q(label, key, asc=False, fmt=None):
        return pit_card(label, key, pool=q_pit, asc=asc, fmt=fmt)

    pit_cats = [
        pit_card_q("ERA", "ERA", asc=True, fmt=lambda v: f"{v:.2f}"),
        pit_card_q("WHIP", "WHIP", asc=True, fmt=lambda v: f"{v:.2f}"),
        pit_card("W", "W", pool=all_pit),
        pit_card("K", "K", pool=all_pit),
        pit_card("SV", "SV", pool=all_pit),
        pit_card("CG", "CG", pool=[p for p in all_pit if p["CG"]]),
        pit_card("SHO", "SHO", pool=[p for p in all_pit if p["SHO"]]),
        pit_card_q("IP", "IP"),
        pit_card_q("BB/9", "BB/9", asc=True, fmt=lambda v: f"{v:.2f}"),
        pit_card_q("HR/9", "HR/9", asc=True, fmt=lambda v: f"{v:.2f}"),
        pit_card_q("K/9", "K/9", fmt=lambda v: f"{v:.2f}"),
    ]
    return pit_cats


def defense_leaders(
    def_rows_raw: list, my_team_id: str | None, team_games: int
) -> list:
    def_cats = []
    def_data = []
    for r in def_rows_raw:
        po = r["po"] or 0
        a = r["a"] or 0
        e = r["e"] or 0
        pb = r["pb"] or 0
        g = r["g"] or 0
        denom = po + a + e
        fpct = (po + a) / denom if denom else 1.0
        def_data.append(
            {
                "player_id": r["player_id"],
                "name": r["name"],
                "team": f"{r['city']} {r['mascot']}",
                "team_id": r["team_id"],
                "is_mine": r["team_id"] == my_team_id,
                "pos": r["position"].upper(),
                "G": g,
                "PO": po,
                "A": a,
                "E": e,
                "PB": pb,
                "PB/G": round(pb / g, 2) if g else 0.0,
                "FPCT": fpct,
            }
        )

    def def_card(label, key, pool, asc=False, fmt=None):
        srt = sorted(pool, key=lambda r: r[key], reverse=not asc)[:10]
        rows = []
        for i, r in enumerate(srt, 1):
            val = r[key]
            if fmt:
                disp = fmt(val)
            elif isinstance(val, float):
                disp = f"{val:.3f}"
            else:
                disp = str(int(val))
            rows.append(
                {
                    "rank": i,
                    "name": r["name"],
                    "team": r["team"],
                    "player_id": r["player_id"],
                    "is_mine": r["is_mine"],
                    "val": disp,
                }
            )
        return {"label": label, "rows": rows}

    field_positions = [
        ("C", "C"),
        ("1B", "1B"),
        ("2B", "2B"),
        ("3B", "3B"),
        ("SS", "SS"),
        ("LF", "LF"),
        ("CF", "CF"),
        ("RF", "RF"),
    ]
    min_g_qual = max(5, team_games // 4)

    for pos_val, pos_label in field_positions:
        pool = [r for r in def_data if r["pos"] == pos_val]
        if not pool:
            continue
        q_pool = [r for r in pool if r["G"] >= min_g_qual] or pool
        def_cats.append(
            def_card(f"{pos_label} FPCT", "FPCT", q_pool, fmt=lambda v: f"{v:.3f}")
        )
        def_cats.append(def_card(f"{pos_label} PO", "PO", pool))
        def_cats.append(def_card(f"{pos_label} A", "A", pool))
        if pos_val == "C":
            def_cats.append(
                def_card("C PB/G", "PB/G", q_pool, asc=True, fmt=lambda v: f"{v:.2f}")
            )
    return def_cats
