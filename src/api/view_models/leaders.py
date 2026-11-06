# src/api/view_models/leaders.py
#
# Context for the leaders tab: top-10 cards for batting, pitching and
# defense in one season.

from __future__ import annotations

from src.db.repositories.player_games import PlayerGameRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.season_repo import SeasonRepository
from src.stats import advanced, formulas, qualifiers as q

# The rookie cards: (pane, label) from the full batting and pitching cards.
ROOKIE_CATS = [
    ("bat", "AVG"), ("bat", "OBP"), ("bat", "OPS"),
    ("bat", "HR"), ("bat", "RBI"), ("bat", "SB"),
    ("pit", "ERA"), ("pit", "WHIP"), ("pit", "K/9"),
    ("pit", "K"), ("pit", "W"), ("pit", "SV"),
]  # fmt: skip


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
    rel_cats = []
    rookie_cats = []
    def_cats = []
    rookie_ids: set[str] = set()

    if season_id:
        pss_repo = PlayerSeasonStatsRepository(db)
        team_games = pss_repo.get_max_games_played(season_id)
        bat = pss_repo.get_batting_for_league(league_id, season_id)
        pit = pss_repo.get_pitching_for_league(league_id, season_id)
        lg = advanced.LeagueRates.of(pss_repo.get_season_totals(season_id))

        bat_cats = batting_leaders(bat, my_team_id, q.min_pa(team_games), lg)
        pit_cats = pitching_leaders(pit, my_team_id, q.min_outs(team_games), lg)
        rel_cats = relief_leaders(
            pit, my_team_id, q.min_outs(team_games, reliever=True), lg
        )
        rookie_ids = pss_repo.get_rookie_ids(league_id, season_id)
        rookie_cats = rookie_leaders(bat, pit, my_team_id, rookie_ids, team_games, lg)
        def_cats = defense_leaders(
            PlayerGameRepository(db).get_league_fielding_by_position(season_id),
            my_team_id,
            team_games,
            {r["player_id"]: r["pitch_outs"] or 0 for r in pit},
        )

    return {
        "leaders_season_id": season_id,
        "leaders_season_name": display_season["name"] if display_season else "",
        "leaders_seasons": all_seasons,
        "bat_cats": bat_cats,
        "pit_cats": pit_cats,
        "rel_cats": rel_cats,
        "rookie_cats": rookie_cats,
        "def_cats": def_cats,
        "rookie_ids": rookie_ids,
    }


def team_leaders(
    db, league_id: str, season_id: str, team_id: str, cats: list[tuple[str, str]]
) -> list[dict]:
    """One team's leader in each of `cats`, a (pane, label) list with pane
    "bat" or "pit": the label plus the top row of the league-wide card,
    counting only this team's players. Rate stats still need the league's
    qualifying plate appearances or innings; a category no one on the team
    qualifies for is left out."""
    pss_repo = PlayerSeasonStatsRepository(db)
    team_games = pss_repo.get_max_games_played(season_id)
    min_pa, min_outs = q.min_pa(team_games), q.min_outs(team_games)
    lg = advanced.LeagueRates.of(pss_repo.get_season_totals(season_id))
    bat = [
        r
        for r in pss_repo.get_batting_for_league(league_id, season_id)
        if r["team_id"] == team_id
    ]
    pit = [
        r
        for r in pss_repo.get_pitching_for_league(league_id, season_id)
        if r["team_id"] == team_id
    ]
    by_label = {
        "bat": {c["label"]: c for c in batting_leaders(bat, team_id, min_pa, lg)},
        "pit": {c["label"]: c for c in pitching_leaders(pit, team_id, min_outs, lg)},
    }
    out = []
    for pane, label in cats:
        cat = by_label[pane].get(label)
        if cat and cat["rows"]:
            out.append({"label": label, **cat["rows"][0]})
    return out


def rookie_leaders(
    bat_rows: list,
    pit_rows: list,
    my_team_id: str | None,
    rookie_ids: set[str],
    team_games: int,
    lg: advanced.LeagueRates | None = None,
) -> list:
    """The ROOKIE_CATS cards among this season's rookies, who qualify for the
    rate stats at half the usual playing time (1.55 PA or 0.5 IP a team
    game). None in a season without rookies."""
    bat = [r for r in bat_rows if r["player_id"] in rookie_ids]
    pit = [r for r in pit_rows if r["player_id"] in rookie_ids]
    if not bat and not pit:
        return []
    by_label = {
        "bat": {
            c["label"]: c
            for c in batting_leaders(
                bat, my_team_id, q.min_pa(team_games, rookie=True), lg
            )
        },
        "pit": {
            c["label"]: c
            for c in pitching_leaders(
                pit, my_team_id, q.min_outs(team_games, rookie=True), lg
            )
        },
    }
    return [by_label[pane][label] for pane, label in ROOKIE_CATS]


def batting_leaders(
    bat_rows: list,
    my_team_id: str | None,
    min_pa: int,
    lg: advanced.LeagueRates | None = None,
) -> list:
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
        qualifies = q.plate_appearances(r) >= min_pa
        ab_k = ab / k if k else 0.0
        ab_hr = ab / hr if hr else None
        bb_k = bb / k if k else None
        adv = advanced.batting(r, lg)
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
                "wOBA": adv["wOBA"] or 0.0,
                "wRC+": adv["wRC_PLUS"],
                "OPS+": adv["OPS_PLUS"],
                "ISO": adv["ISO"] or 0.0,
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
        bat_card_q("AVG", "AVG", fmt=lambda v: f"{v:.3f}".lstrip("0")),
        bat_card("HR", "HR", pool=all_bat),
        bat_card("RBI", "RBI", pool=all_bat),
        bat_card("R", "R", pool=all_bat),
        bat_card("H", "H", pool=all_bat),
        bat_card("SB", "SB", pool=all_bat),
        bat_card_q("OBP", "OBP", fmt=lambda v: f"{v:.3f}".lstrip("0")),
        bat_card_q("SLG", "SLG", fmt=lambda v: f"{v:.3f}"),
        bat_card_q("OPS", "OPS", fmt=lambda v: f"{v:.3f}"),
        bat_card_q("wOBA", "wOBA", fmt=lambda v: f"{v:.3f}".lstrip("0")),
        *(
            [
                bat_card(
                    label,
                    label,
                    pool=[b for b in qualified if b[label] is not None],
                    fmt=str,
                )
                for label in ("wRC+", "OPS+")
            ]
            if lg
            else []
        ),
        bat_card_q("ISO", "ISO", fmt=lambda v: f"{v:.3f}".lstrip("0")),
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


def _pitchers(
    pit_rows: list,
    my_team_id: str | None,
    min_outs: int,
    lg: advanced.LeagueRates | None = None,
) -> list:
    pitchers = []
    for r in pit_rows:
        outs = r["pitch_outs"] or 0
        er = r["pitch_earned_runs"] or 0
        ph = r["pitch_hits"] or 0
        pbb = r["pitch_walks"] or 0
        pk = r["pitch_strike_outs"] or 0
        hr = r["pitch_home_runs"] or 0
        g = r.get("pitch_games_played") or 0
        gs = r.get("pitch_games_started") or 0
        adv = advanced.pitching(r, lg)
        pitchers.append(
            {
                "player_id": r["player_id"],
                "name": f"{r['first_name']} {r['last_name']}",
                "team": f"{r['city']} {r['mascot']}",
                "team_id": r["team_id"],
                "is_mine": r["team_id"] == my_team_id,
                "qualifies": outs >= min_outs,
                "reliever": q.is_reliever(g, gs),
                "ERA": formulas.era(er, outs),
                "WHIP": formulas.whip(ph, pbb, outs),
                "W": r["pitch_wins"] or 0,
                "K": pk,
                "SV": r["pitch_saves"] or 0,
                "HLD": r.get("pitch_holds") or 0,
                "CG": r.get("pitch_complete_games") or 0,
                "SHO": r.get("pitch_shutouts") or 0,
                "IP": formulas.innings(outs),
                "BB/9": formulas.per_nine(pbb, outs),
                "HR/9": formulas.per_nine(hr, outs),
                "K/9": formulas.per_nine(pk, outs),
                "FIP": adv["FIP"] if adv["FIP"] is not None else 99.0,
                # A 0.00 ERA has no ERA+; it ranks first.
                "ERA+": adv["ERA_PLUS"] if adv["ERA_PLUS"] is not None else 9999,
                "K%": adv["K_PCT"] or 0.0,
            }
        )
    return pitchers


def _pit_card(pitchers, label, key, pool=None, asc=False, fmt=None):
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


def _f2(v):
    return f"{v:.2f}"


def _plus(v):
    return "∞" if v >= 9999 else str(v)


def _pct(v):
    return f"{v:.1f}%"


def pitching_leaders(
    pit_rows: list,
    my_team_id: str | None,
    min_outs: int,
    lg: advanced.LeagueRates | None = None,
) -> list:
    """The pitching cards. Rate stats need min_outs, the full inning a team
    game for starters and relievers alike. FIP and ERA+ need `lg`."""
    pitchers = _pitchers(pit_rows, my_team_id, min_outs, lg)
    q_pit = [p for p in pitchers if p["qualifies"]]

    def card(label, key, pool=None, asc=False, fmt=None):
        return _pit_card(pitchers, label, key, pool, asc, fmt)

    return [
        card("ERA", "ERA", pool=q_pit, asc=True, fmt=_f2),
        card("WHIP", "WHIP", pool=q_pit, asc=True, fmt=_f2),
        *(
            [
                card("FIP", "FIP", pool=q_pit, asc=True, fmt=_f2),
                card("ERA+", "ERA+", pool=q_pit, fmt=_plus),
            ]
            if lg
            else []
        ),
        card("W", "W"),
        card("K", "K"),
        card("SV", "SV"),
        card("CG", "CG", pool=[p for p in pitchers if p["CG"]]),
        card("SHO", "SHO", pool=[p for p in pitchers if p["SHO"]]),
        card("IP", "IP", pool=q_pit),
        card("BB/9", "BB/9", pool=q_pit, asc=True, fmt=_f2),
        card("HR/9", "HR/9", pool=q_pit, asc=True, fmt=_f2),
        card("K/9", "K/9", pool=q_pit, fmt=_f2),
        card("K%", "K%", pool=q_pit, fmt=_pct),
    ]


def relief_leaders(
    pit_rows: list,
    my_team_id: str | None,
    min_outs: int,
    lg: advanced.LeagueRates | None = None,
) -> list:
    """Cards for relievers only (fewer than half their games started). Rate
    stats need min_outs, half an inning a team game."""
    pitchers = [
        p for p in _pitchers(pit_rows, my_team_id, min_outs, lg) if p["reliever"]
    ]
    q_rel = [p for p in pitchers if p["qualifies"]]

    def card(label, key, pool=None, asc=False, fmt=None):
        return _pit_card(pitchers, label, key, pool, asc, fmt)

    return [
        card("SV", "SV", pool=[p for p in pitchers if p["SV"]]),
        card("HLD", "HLD", pool=[p for p in pitchers if p["HLD"]]),
        card("ERA", "ERA", pool=q_rel, asc=True, fmt=_f2),
        card("WHIP", "WHIP", pool=q_rel, asc=True, fmt=_f2),
        *([card("FIP", "FIP", pool=q_rel, asc=True, fmt=_f2)] if lg else []),
        card("K/9", "K/9", pool=q_rel, fmt=_f2),
        card("BB/9", "BB/9", pool=q_rel, asc=True, fmt=_f2),
    ]


def defense_leaders(
    def_rows_raw: list,
    my_team_id: str | None,
    team_games: int,
    pitcher_outs: dict[str, int] | None = None,
) -> list:
    """FPCT, putouts and the like at each position. FPCT needs games there:
    half the team's games at catcher, two thirds elsewhere. Pitchers (P
    FPCT, from pitcher_outs, each pitcher's outs pitched) need an inning a
    team game, unless one with fewer has a better FPCT in more chances."""
    pitcher_outs = pitcher_outs or {}
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
                "DP": r["dp"] or 0,
                "PB": pb,
                "PB/G": round(pb / g, 2) if g else 0.0,
                "FPCT": fpct,
                "TC": denom,
            }
        )

    def def_card(label, key, pool, asc=False, fmt=None):
        # Ties (a lot of 1.000s) go to the one with more chances.
        srt = sorted(pool, key=lambda r: (r[key], r["TC"]), reverse=not asc)[:10]
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
    for pos_val, pos_label in field_positions:
        pool = [r for r in def_data if r["pos"] == pos_val]
        if not pool:
            continue
        min_g = q.min_field_games(pos_val, team_games)
        q_pool = [r for r in pool if r["G"] >= min_g] or pool
        def_cats.append(
            def_card(f"{pos_label} FPCT", "FPCT", q_pool, fmt=lambda v: f"{v:.3f}")
        )
        def_cats.append(def_card(f"{pos_label} PO", "PO", pool))
        def_cats.append(def_card(f"{pos_label} A", "A", pool))
        if pos_val in ("1B", "2B", "3B", "SS"):
            def_cats.append(def_card(f"{pos_label} DP", "DP", pool))
        if pos_val == "C":
            def_cats.append(
                def_card("C PB/G", "PB/G", q_pool, asc=True, fmt=lambda v: f"{v:.2f}")
            )

    pitchers = [r for r in def_data if r["pos"] == "P"]
    if pitchers:
        for r in pitchers:
            r["outs"] = pitcher_outs.get(r["player_id"], 0)
        p_pool = q.pitcher_fpct_pool(
            [{**r, "fpct": r["FPCT"], "chances": r["TC"]} for r in pitchers],
            team_games,
        )
        def_cats.append(
            def_card("P FPCT", "FPCT", p_pool or pitchers, fmt=lambda v: f"{v:.3f}")
        )
    return def_cats
