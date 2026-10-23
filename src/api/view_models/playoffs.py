# src/api/view_models/playoffs.py
#
# Context for the playoffs tab: the bracket, round by round.

from __future__ import annotations

from src.db.repositories.games_repo import GameRepository
from src.db.repositories.playoff_repo import PlayoffRepository
from src.db.repositories.team_repo import TeamRepository


def playoffs_context(db, season_id: str | None, my_team_id: str | None) -> dict:
    bracket = load_bracket(db, season_id, my_team_id) if season_id else []
    champion = None
    if bracket and bracket[-1]["decided"]:
        finals = bracket[-1]["series"][0]
        champion = next(
            (t for t in finals["teams"] if t["team_id"] == finals["winner_id"]), None
        )
    return {"bracket": bracket, "champion": champion, "my_team_id": my_team_id}


def load_bracket(db, season_id: str, my_team_id: str | None) -> list:
    """Load full bracket state for template rendering."""
    ROUND_DEFS = [
        {"name": "Round 1", "series_names": ["1v8", "4v5", "2v7", "3v6"], "best_of": 5},
        {
            "name": "Semifinals",
            "series_names": ["[1,8]v[4,5]", "[2,7]v[3,6]"],
            "best_of": 7,
        },
        {"name": "Finals", "series_names": ["Finals"], "best_of": 7},
    ]
    # Map semifinal series name → which round-1 series feed into it
    _SEMI_FEEDERS = {
        "[1,8]v[4,5]": ("1v8", "4v5"),
        "[2,7]v[3,6]": ("2v7", "3v6"),
    }

    def _team_name(tid):
        tr = TeamRepository(db)
        return tr.get_city_mascot(team_id=tid)

    def load_series(series_name, best_of):
        por = PlayoffRepository(db)
        sid = por.get_series_id(season_id, series_name)
        if not sid:
            return {
                "name": series_name,
                "series_id": None,
                "best_of": best_of,
                "teams": [],
                "games_played": 0,
                "decided": False,
                "winner_id": None,
            }

        games = GameRepository(db).get_series_games(sid)

        team_ids = []
        seen = set()
        for g in games:
            for tid in (g["home_team_id"], g["away_team_id"]):
                if tid not in seen:
                    team_ids.append(tid)
                    seen.add(tid)

        # If this series has no games yet (prior round not fully complete),
        # try to show the known winner(s) from the feeder round-1 series.
        if not team_ids and series_name in _SEMI_FEEDERS:
            for feeder_name in _SEMI_FEEDERS[series_name]:
                feeder_sid = por.get_series_id(season_id, feeder_name)
                if feeder_sid:
                    w = por.get_series_winner(feeder_sid, 5)
                    if w and w not in seen:
                        team_ids.append(w)
                        seen.add(w)

        teams = []
        for tid in team_ids:
            wins = sum(1 for g in games if g["completed"] and g["winner_id"] == tid)
            teams.append(
                {
                    "team_id": tid,
                    "name": _team_name(tid),
                    "wins": wins,
                    "is_mine": tid == my_team_id,
                    "pending": len(games) == 0,
                }
            )

        wins_needed = {5: 3, 7: 4}[best_of]
        winner_id = next(
            (t["team_id"] for t in teams if t["wins"] >= wins_needed), None
        )
        games_played = sum(1 for g in games if g["completed"])
        completed_games = [
            {
                "id": g["id"],
                "winner_id": g["winner_id"],
                "home_score": g["home_score"],
                "away_score": g["away_score"],
            }
            for g in games
            if g["completed"]
        ]

        return {
            "name": series_name,
            "series_id": sid,
            "best_of": best_of,
            "wins_needed": wins_needed,
            "teams": teams,
            "games_played": games_played,
            "completed_games": completed_games,
            "decided": winner_id is not None,
            "winner_id": winner_id,
        }

    rounds = []
    for rd in ROUND_DEFS:
        series_list = [load_series(sn, rd["best_of"]) for sn in rd["series_names"]]
        rounds.append(
            {
                "name": rd["name"],
                "best_of": rd["best_of"],
                "series": series_list,
                "decided": all(s["decided"] for s in series_list),
            }
        )
    return rounds
