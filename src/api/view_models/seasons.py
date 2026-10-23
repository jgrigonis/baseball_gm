# src/api/view_models/seasons.py
#
# Context for the end-of-season pages: season summary, retirements, and the
# league history list.

from __future__ import annotations

from src.db.repositories.games_repo import GameRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.series_repo import SeriesRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.stats import formulas


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
    game_repo = GameRepository(db)
    pss_repo = PlayerSeasonStatsRepository(db)

    # Use explicit season_id (from history link) or fall back to last season with series
    if not season_id:
        season_id = season_repo.get_last_with_series(league_id) or default_season_id

    # My team record
    my_record = None
    if my_team_id and season_id:
        my_record = tg_repo.get_team_wl(my_team_id, season_id)

    # Champion
    champion = None
    if season_id:
        champ = series_repo.get_champion(season_id)
        if champ:
            champion = {
                "team_id": champ["team_id"],
                "name": f"{champ['city']} {champ['mascot']}",
                "is_mine": champ["team_id"] == my_team_id,
            }

    # My playoff result
    my_playoff_result = None
    if my_team_id and season_id:
        my_playoff_result = series_repo.get_team_playoff_result(my_team_id, season_id)

    # Stat leaders — compute qualification thresholds from actual games played
    bat_leader = pit_leader = None
    if season_id:
        games_total = game_repo.get_completed_regular_season_count(season_id)
        num_teams = season_repo.get_team_count(season_id) or 30
        games_per_team = (games_total * 2) / num_teams if num_teams else 0
        min_ab = int(3.1 * games_per_team)
        min_outs = int(3 * games_per_team)

        br = pss_repo.get_batting_leader(league_id, season_id, min_ab)
        if br:
            bat_leader = {
                "name": f"{br['first_name']} {br['last_name']}",
                "team": f"{br['city']} {br['mascot']}",
                "stat": f"{br['avg']:.3f}",
                "label": "AVG",
            }

        pr = pss_repo.get_pitching_leader(league_id, season_id, min_outs)
        if pr:
            pit_leader = {
                "name": f"{pr['first_name']} {pr['last_name']}",
                "team": f"{pr['city']} {pr['mascot']}",
                "stat": f"{pr['era']:.2f}",
                "label": "ERA",
            }

    # Season year
    season_year = None
    if season_id:
        s = season_repo.get_season(season_id)
        season_year = s["year"] if s else None

    return {
        "my_record": my_record,
        "champion": champion,
        "my_playoff_result": my_playoff_result,
        "bat_leader": bat_leader,
        "pit_leader": pit_leader,
        "season_year": season_year,
    }


def retirement_context(db, league_id: str, my_team_id: str | None) -> dict:
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

    return {"retired_players": retired_players, "my_team_id": my_team_id}


def history_context(db, league_id: str, my_team_id: str | None) -> dict:
    """One row per season: champion and the GM's record."""
    season_repo = SeasonRepository(db)
    series_repo = SeriesRepository(db)
    tg_repo = TeamGameRepository(db)

    seasons = season_repo.get_seasons_for_league(league_id)

    history_rows = []
    for s in seasons:
        champ = series_repo.get_champion(s["id"])
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
                "champion": champion_name,
                "my_w": my_w,
                "my_l": my_l,
            }
        )

    return {"history_rows": history_rows}
