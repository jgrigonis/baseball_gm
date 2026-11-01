# src/api/view_models/seasons.py
#
# Context for the end-of-season pages: season summary, retirements, and the
# league history list.

from __future__ import annotations

from src.api.services import awards as awards_service
from src.api.view_models.draft import draft_rounds
from src.api.view_models.leaders import leaders_context
from src.api.view_models.playoffs import playoffs_context
from src.api.view_models.standings import standings_rows
from src.db.repositories.all_star_repo import AllStarRepository
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.injury_repo import INJURY_TIERS, InjuryRepository
from src.db.repositories.player_games import PlayerGameRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.retirement_repo import RetirementRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.series_repo import SeriesRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.league import awards as awards_mod
from src.stats import formulas


def past_season(
    db, league_id: str, season_id: str | None, current_season_id: str | None
) -> dict | None:
    """The season row a history link asked for, when it belongs to the league
    and isn't the season the tabs already show; otherwise None."""
    if not season_id or season_id == current_season_id:
        return None
    return SeasonRepository(db).get_for_league(league_id, season_id)


# Leader categories the summary lists, in display order: (pane, label).
SUMMARY_LEADER_CATS = [
    ("bat", "AVG"),
    ("bat", "HR"),
    ("bat", "RBI"),
    ("bat", "SB"),
    ("pit", "ERA"),
    ("pit", "W"),
    ("pit", "K"),
    ("pit", "SV"),
]
# The top leader card, left to right.
TOP_LEADER_CATS = [("bat", "AVG"), ("bat", "HR"), ("pit", "ERA"), ("pit", "K")]
SUMMARY_LEADERS_SHOWN = 5


def season_summary_context(
    db,
    league_id: str,
    season_id: str | None,
    default_season_id: str | None,
    my_team_id: str | None,
) -> dict:
    """`season_id` comes from a history link; without one, show the last
    season with playoff series, then `default_season_id`."""
    season_repo = SeasonRepository(db)
    series_repo = SeriesRepository(db)
    tg_repo = TeamGameRepository(db)

    # Use explicit season_id (from history link) or fall back to last season with series
    if season_id and not season_repo.get_for_league(league_id, season_id):
        season_id = None
    if not season_id:
        season_id = season_repo.get_last_with_series(league_id) or default_season_id

    ctx = {
        "summary_season_id": season_id,
        "my_record": None,
        "champion": None,
        "best_record": None,
        "my_playoff_result": None,
        "top_leaders": [],
        "leader_cats": [],
        "standings": [],
        "playoff_rounds": [],
        "draft_round": None,
        "draft_rounds_total": 0,
        "injuries": [],
        "injuries_league_wide": my_team_id is None,
        "injury_days_total": 0,
        # Sorts the Injury column worst first: each tier by its longest layoff
        "severity_rank": {tier: hi for tier, (_, hi) in INJURY_TIERS.items()},
        "season_year": None,
        "no_hitters": [],
        "awards": [],
    }
    if not season_id:
        return ctx

    s = season_repo.get_season(season_id)
    ctx["season_year"] = s["year"] if s else None

    # My team record and playoff result
    if my_team_id:
        ctx["my_record"] = tg_repo.get_team_wl(my_team_id, season_id)
        ctx["my_playoff_result"] = series_repo.get_team_playoff_result(
            my_team_id, season_id
        )

    # Champion
    champ = series_repo.get_champion(season_id)
    if champ:
        ctx["champion"] = {
            "team_id": champ["team_id"],
            "name": f"{champ['city']} {champ['mascot']}",
            "is_mine": champ["team_id"] == my_team_id,
        }

    # Final standings; the first row is the best regular-season record
    standings = standings_rows(db, league_id, season_id, my_team_id)
    if standings and standings[0]["wins"] + standings[0]["losses"]:
        ctx["standings"] = standings
        best = standings[0]
        ctx["best_record"] = {
            "team_id": best["team_id"],
            "name": f"{best['city']} {best['mascot']}",
            "wins": best["wins"],
            "losses": best["losses"],
            "is_mine": best["is_mine"],
        }

    # Stat leaders, the same lists the Leaders tab shows for this season
    leaders = leaders_context(db, league_id, season_id, my_team_id)
    cats = {
        "bat": {c["label"]: c for c in leaders["bat_cats"]},
        "pit": {c["label"]: c for c in leaders["pit_cats"]},
    }
    for pane, label in TOP_LEADER_CATS:
        cat = cats[pane].get(label)
        if cat and cat["rows"]:
            ctx["top_leaders"].append({"label": label, **cat["rows"][0]})
    for pane, label in SUMMARY_LEADER_CATS:
        cat = cats[pane].get(label)
        if cat and cat["rows"]:
            ctx["leader_cats"].append(
                {"label": label, "rows": cat["rows"][:SUMMARY_LEADERS_SHOWN]}
            )

    ctx["awards"] = season_awards(db, season_id, my_team_id)

    # No-hitters thrown this season
    for nh in PlayerGameRepository(db).get_no_hitters(season_id):
        ctx["no_hitters"].append(
            {
                "player_id": nh["player_id"],
                "name": f"{nh['first_name']} {nh['last_name']}",
                "team": f"{nh['city']} {nh['mascot']}",
                "opponent": f"{nh['opp_city']} {nh['opp_mascot']}",
                "game_date": nh["game_date"],
                "postseason": nh["postseason"],
                "K": nh["K"],
                "BB": nh["BB"],
                "is_mine": nh["team_id"] == my_team_id,
            }
        )

    # Playoff results, one line per decided or started series
    bracket = playoffs_context(db, league_id, season_id, my_team_id)["bracket"]
    for rd in bracket:
        series = []
        for sr in rd["series"]:
            if len(sr["teams"]) < 2 or not sr["games_played"]:
                continue
            ordered = sorted(sr["teams"], key=lambda t: -t["wins"])
            series.append(
                {
                    "leader": ordered[0],
                    "trailer": ordered[1],
                    "decided": sr["decided"],
                }
            )
        if series:
            ctx["playoff_rounds"].append({"name": rd["name"], "series": series})

    # The draft held before this season: its first round here, the rest a link away
    draft = DraftRepository(db).get_for_season(league_id, season_id)
    if draft:
        rounds = draft_rounds(db, league_id, draft["id"], my_team_id)
        if rounds:
            ctx["draft_round"] = rounds[0]
            ctx["draft_rounds_total"] = len(rounds)

    # Injuries: the GM's own team; a viewer with no team sees every team's
    injuries = InjuryRepository(db, league_id).get_season_injuries(
        season_id, my_team_id
    )
    for inj in injuries:
        inj["team"] = f"{inj['city']} {inj['mascot']}" if inj["city"] else ""
    ctx["injuries"] = injuries
    ctx["injury_days_total"] = sum(inj["days_missed"] for inj in injuries)

    return ctx


def season_awards(db, season_id: str, my_team_id: str | None) -> list[dict]:
    """The season's awards, one entry per award with its winners: the
    league it was given in (Atlantic, Pacific, or blank), who and the team,
    and the season (or series) in a few words."""
    out: list[dict] = []
    for r in awards_service.for_season(db, season_id):
        award = awards_mod.BY_KEY[r["award"]]
        if not out or out[-1]["key"] != award.key:
            out.append(
                {
                    "key": award.key,
                    "name": award.name,
                    "icon": award.icon,
                    "winners": [],
                }
            )
        if r["player_id"]:
            who = f"{r['first_name']} {r['last_name']}"
        else:
            who = f"GM {r['gm_name']}" if r["gm_name"] else "—"
        scope = r["scope"]
        out[-1]["winners"].append(
            {
                "scope": scope.removesuffix(" League")
                if scope.endswith("League")
                else "",
                "player_id": r["player_id"],
                "name": who,
                "team": f"{r['city']} {r['mascot']}" if r["city"] else "",
                "line": r["line"],
                "is_mine": bool(my_team_id and r["team_id"] == my_team_id),
            }
        )
    return out


def retirement_context(
    db, league_id: str, my_team_id: str | None, season_id: str | None = None
) -> dict:
    """`season_id` comes from a history link and names the season the players
    retired after; without one, show this offseason's retirements."""
    season_repo = SeasonRepository(db)
    current_season_id = season_repo.get_current_id_for_league(league_id)

    # Retirements happened in the season just before the current one
    prev_season = None
    if current_season_id:
        current_year = (season_repo.get_season(current_season_id) or {}).get("year")
        if current_year:
            prev_season = season_repo.get_by_league_and_year(
                league_id, current_year - 1
            )

    # A history link to an earlier offseason shows that one instead.
    history_season = None
    if season_id and season_id != (prev_season or {}).get("id"):
        history_season = season_repo.get_for_league(league_id, season_id)
        if history_season:
            prev_season = history_season

    prev_season_id = prev_season["id"] if prev_season else None
    player_repo = PlayerRepository(db)
    retired_players = []
    if prev_season_id:
        rows = player_repo.get_retired_players_career_stats(
            my_team_id, league_id, prev_season_id
        )

        for r in rows:
            r = dict(r)
            ab = r.get("bat_ab") or 0
            hits = r.get("bat_hits") or 0
            bb = r.get("bat_walks") or 0
            outs = r.get("pitch_outs") or 0
            er = r.get("pitch_earned_runs") or 0
            hbp = r.get("bat_hbp") or 0
            sf = r.get("bat_sac_flys") or 0
            pbb = r.get("pitch_walks") or 0
            ph = r.get("pitch_hits") or 0
            r["has_bat_stats"] = ab > 0
            r["has_pit_stats"] = outs > 0
            # is_pitcher: used for games column; show pitching if outs dominate or no AB
            r["is_pitcher"] = outs > 0 and (ab == 0 or outs / 3 >= ab / 10)
            r["avg"] = f"{formulas.batting_average(hits, ab):.3f}" if ab else "—"
            r["obp"] = (
                f"{formulas.on_base_pct(hits, bb, hbp, ab, sf):.3f}"
                if ab + bb + hbp + sf
                else "—"
            )
            r["era"] = f"{formulas.era(er, outs):.2f}" if outs else "—"
            r["ip"] = formulas.ip_str(outs)
            r["whip"] = f"{formulas.whip(ph, pbb, outs):.2f}" if outs else "—"
            retired_players.append(r)

        # A star by the name of every career All-Star.
        years = AllStarRepository(db).years_by_player(
            [r["player_id"] for r in retired_players]
        )
        for r in retired_players:
            r["all_star_years"] = years.get(r["player_id"], [])

    return {
        "retired_players": retired_players,
        "my_team_id": my_team_id,
        "history_season": history_season,
    }


def history_context(db, league_id: str, my_team_id: str | None) -> dict:
    """One row per season: champion, the GM's record, whether the season
    has a draft to link to, and how many players retired after it."""
    season_repo = SeasonRepository(db)
    series_repo = SeriesRepository(db)
    tg_repo = TeamGameRepository(db)
    draft_repo = DraftRepository(db)
    retired_counts = RetirementRepository(db).counts_by_season(league_id)

    seasons = season_repo.get_seasons_for_league(league_id)

    history_rows = []
    for s in seasons:
        champ = series_repo.get_champion(s["id"])
        season_awards_rows = awards_service.for_season(db, s["id"])
        champion_name = f"{champ['city']} {champ['mascot']}" if champ else None

        my_w = my_l = None
        if my_team_id:
            wl = tg_repo.get_team_wl(my_team_id, s["id"])
            if wl:
                my_w, my_l = wl["w"], wl["l"]

        history_rows.append(
            {
                "season_id": s["id"],
                "year": s["year"],
                "name": s["name"],
                "is_backstory": s["is_backstory"],
                "champion": champion_name,
                "my_w": my_w,
                "my_l": my_l,
                "has_draft": draft_repo.get_for_season(league_id, s["id"]) is not None,
                "retired": retired_counts.get(s["id"], 0),
                "has_awards": bool(season_awards_rows),
                "mvps": [
                    {
                        "player_id": r["player_id"],
                        "name": f"{r['first_name']} {r['last_name']}",
                        "scope": r["scope"].removesuffix(" League")
                        if r["scope"].endswith("League")
                        else "",
                        "line": r["line"],
                    }
                    for r in season_awards_rows
                    if r["award"] == "mvp"
                ],
            }
        )

    return {"history_rows": history_rows}
