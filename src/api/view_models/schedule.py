# src/api/view_models/schedule.py
#
# Context for the schedule tab: the GM's upcoming games (with opponent
# records) and completed results.

from __future__ import annotations

from src.db.repositories.games_repo import GameRepository
from src.db.repositories.team_game_repo import TeamGameRepository


def schedule_context(db, season_id: str | None, my_team_id: str | None) -> dict:
    upcoming = []
    recent = []

    if season_id and my_team_id:
        game_repo = GameRepository(db)
        tg_repo = TeamGameRepository(db)

        up_rows = game_repo.get_team_upcoming(season_id, my_team_id)
        opp_team_ids = {
            r["away_team_id"] if r["home_team_id"] == my_team_id else r["home_team_id"]
            for r in up_rows
        }
        opp_records = tg_repo.get_records_for_teams(season_id, opp_team_ids)

        for r in up_rows:
            is_home = r["home_team_id"] == my_team_id
            opp_id = r["away_team_id"] if is_home else r["home_team_id"]
            upcoming.append(
                {
                    "date": r["game_date"],
                    "home_away": "vs" if is_home else "@",
                    "opp_id": opp_id,
                    "opp_city": r["away_city"] if is_home else r["home_city"],
                    "opp_mascot": r["away_mascot"] if is_home else r["home_mascot"],
                    "opp_record": opp_records.get(opp_id, "0-0"),
                    "is_home": is_home,
                }
            )

        for r in game_repo.get_team_results(season_id, my_team_id):
            is_home = r["home_team_id"] == my_team_id
            my_score = r["home_score"] if is_home else r["away_score"]
            opp_score = r["away_score"] if is_home else r["home_score"]
            won = (my_score or 0) > (opp_score or 0)
            extra = (
                f" ({r['innings_played']})"
                if r["innings_played"] and r["innings_played"] != 9
                else ""
            )
            recent.append(
                {
                    "game_id": r["game_id"],
                    "date": r["game_date"],
                    "home_away": "vs" if is_home else "@",
                    "opp_city": r["away_city"] if is_home else r["home_city"],
                    "opp_mascot": r["away_mascot"] if is_home else r["home_mascot"],
                    "my_score": my_score,
                    "opp_score": opp_score,
                    "result": "W" if won else "L",
                    "extra": extra,
                }
            )

    return {"upcoming": upcoming, "recent": recent}
