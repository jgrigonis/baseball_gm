# src/api/view_models/playoffs.py
#
# Context for the playoffs tab: the bracket, round by round.

from __future__ import annotations

from src.db.repositories.games_repo import GameRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.playoff_repo import PlayoffRepository
from src.db.repositories.team_repo import TeamRepository
from src.league import divisions


def playoffs_context(
    db, league_id: str, season_id: str | None, my_team_id: str | None
) -> dict:
    human_team_ids = GMRepository(db).get_human_team_ids(league_id)
    bracket = (
        load_bracket(db, season_id, my_team_id, human_team_ids) if season_id else []
    )
    _label_by_league(db, league_id, bracket)
    champion = None
    if bracket and bracket[-1]["decided"]:
        finals = bracket[-1]["series"][0]
        champion = next(
            (t for t in finals["teams"] if t["team_id"] == finals["winner_id"]), None
        )
    return {"bracket": bracket, "champion": champion, "my_team_id": my_team_id}


# With leagues and divisions each league seeds its own four (divisions.
# playoff_order), so a first-round series is that league's 1 v 4 or 2 v 3.
_IN_LEAGUE = {"1v8": "1 v 4", "4v5": "2 v 3", "2v7": "1 v 4", "3v6": "2 v 3"}


def _label_by_league(db, league_id: str, bracket: list) -> None:
    """Give each series a header naming its league, for leagues with
    divisions: "Atlantic League · 1 v 4", "Pacific League final"."""
    conf_of = {
        t: conf.name for conf in divisions.load(db, league_id) for t in conf.team_ids
    }
    if not conf_of:
        return
    for rd in bracket:
        for s in rd["series"]:
            confs = {conf_of.get(t["team_id"]) for t in s["teams"]}
            if len(confs) != 1 or None in confs:
                continue
            conf = confs.pop()
            if s["name"] in _IN_LEAGUE:
                s["label"] = f"{conf} · {_IN_LEAGUE[s['name']]}"
            elif s["name"] != "Finals":
                s["label"] = f"{conf} final"


def load_bracket(
    db,
    season_id: str,
    my_team_id: str | None,
    human_team_ids: set[str] | None = None,
) -> list:
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
    # Map a later-round series → the series that feed into it, and their
    # best-of (to know when a feeder has a winner).
    _FEEDERS = {
        "[1,8]v[4,5]": (("1v8", "4v5"), 5),
        "[2,7]v[3,6]": (("2v7", "3v6"), 5),
        "Finals": (("[1,8]v[4,5]", "[2,7]v[3,6]"), 7),
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
        # try to show the known winner(s) from the feeder series.
        if not team_ids and series_name in _FEEDERS:
            feeders, feeder_best_of = _FEEDERS[series_name]
            for feeder_name in feeders:
                feeder_sid = por.get_series_id(season_id, feeder_name)
                if feeder_sid:
                    w = por.get_series_winner(feeder_sid, feeder_best_of)
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
                    "is_human": tid in (human_team_ids or ()) and tid != my_team_id,
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
                "game_date": g["game_date"],
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
    _mark_latest_day(rounds)
    return rounds


def _mark_latest_day(rounds: list) -> None:
    """Flag the games of the last playoff day played (and the day before),
    for the bracket's dots: the latest day's dots show larger, and during a
    live sim they ripple in. Series that played that day get a running order
    top to bottom so they light up one after another, and a series won that
    day is marked clinched."""
    dates = sorted(
        {
            g["game_date"]
            for rd in rounds
            for s in rd["series"]
            for g in s.get("completed_games", [])
        }
    )
    latest = dates[-1] if dates else None
    prev = dates[-2] if len(dates) > 1 else None
    order = 0
    for rd in rounds:
        for s in rd["series"]:
            games = s.get("completed_games", [])
            for g in games:
                g["latest"] = g["game_date"] == latest
                g["prev"] = g["game_date"] == prev
            played_today = any(g["latest"] for g in games)
            s["latest_order"] = order if played_today else None
            if played_today:
                order += 1
            s["clinched_today"] = s["decided"] and played_today
