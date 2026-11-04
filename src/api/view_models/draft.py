# src/api/view_models/draft.py
#
# Context for the draft results: every pick, grouped by round. And for the
# draft board: how the GM's team finished last season.

from __future__ import annotations

from src.api.view_models.line_score import _ordinal
from src.api.view_models.standings import standings_rows
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.series_repo import SeriesRepository


def draft_rounds(
    db, league_id: str, draft_id: str, my_team_id: str | None
) -> list[dict]:
    """[{round, picks}] in pick order, with the GM's and other humans' picks
    flagged."""
    picks = DraftRepository(db).get_picks_with_details(draft_id)
    human_team_ids = GMRepository(db).get_human_team_ids(league_id)

    rounds_map: dict[int, list] = {}
    for pick in picks:
        is_mine = pick["team_id"] == my_team_id
        is_human = pick["team_id"] in human_team_ids and not is_mine
        rounds_map.setdefault(pick["round"], []).append(
            {
                "pick_number": pick["pick_number"],
                "team_id": pick["team_id"],
                "player_id": pick["player_id"],
                "team_name": f"{pick['city']} {pick['mascot']}",
                "player_name": f"{pick['first_name']} {pick['last_name']}",
                "position": pick["position"] or "%s",
                "auto_picked": bool(pick["auto_picked"]),
                "is_mine": is_mine,
                "is_human": is_human,
            }
        )
    return [{"round": r, "picks": p} for r, p in sorted(rounds_map.items())]


def _playoff_finish(result: str | None, had_playoffs: bool) -> str | None:
    """SeriesRepository.get_team_playoff_result, in words."""
    if result is None:
        return "missed the playoffs" if had_playoffs else None
    if result.startswith("Won Finals"):
        return "won the championship"
    if result.startswith("Won "):
        return "won a playoff series"  # the next round was never played
    if "first round" in result:
        return "lost in the first round"
    if "semi-finals" in result:
        return "lost in the semifinals"
    return "lost in the Finals"


def last_season(db, league_id: str, team_id: str, draft_season_id: str) -> dict | None:
    """The GM's team's last finished season: {year, w, l, place, teams,
    playoffs}, where playoffs is how it ended ("lost in the semifinals") or
    None before a postseason. None before the league's first season.
    Once the draft's season is under way, still the season before it."""
    seasons = SeasonRepository(db)
    this = seasons.get_year(draft_season_id)
    season = seasons.get_last_with_completed_games(
        league_id, before_year=this["year"] if this else None
    )
    if not season or season["id"] == draft_season_id:
        return None
    rows = standings_rows(db, league_id, season["id"], team_id)
    place = next((i for i, r in enumerate(rows, 1) if r["team_id"] == team_id), None)
    if place is None:
        return None
    me = rows[place - 1]
    series = SeriesRepository(db)
    return {
        "year": season["year"],
        "w": me["wins"],
        "l": me["losses"],
        "place": _ordinal(place),
        "teams": len(rows),
        "playoffs": _playoff_finish(
            series.get_team_playoff_result(team_id, season["id"]),
            series.get_finals_id(season["id"]) is not None,
        ),
    }
