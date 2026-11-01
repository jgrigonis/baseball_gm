# src/api/view_models/news.py
"""The News tab (src/api/services/news/) and the Standings tab's headlines
strip: stories grouped by league date, with each team's badge."""

from __future__ import annotations

from datetime import date

from src.db.repositories.news_repo import NewsRepository

PAGE = 60
HEADLINES = 3

KIND_ICONS = {
    "trade": "🔁",
    "verdict": "⚖️",
    "draft": "📋",
    "streak": "🔥",
    "no_hitter": "🚫",
    "cycle": "🔄",
    "big_game": "💥",
    "milestone": "🏅",
    "injury": "🩹",
    "all_star": "★",
    "award": "👑",
    "division": "🚩",
    "series": "🥇",
    "champion": "🏆",
    "front_office": "💼",
    "retirement": "👋",
}

KIND_LABELS = {
    "trade": "Trade",
    "verdict": "Trade verdict",
    "draft": "Draft",
    "streak": "Streak",
    "no_hitter": "No-hitter",
    "cycle": "Cycle",
    "big_game": "Big game",
    "milestone": "Milestone",
    "injury": "Injury",
    "all_star": "All-Stars",
    "award": "Stat crown",
    "division": "Division",
    "series": "Playoffs",
    "champion": "Champion",
    "front_office": "Front office",
    "retirement": "Retirement",
}


def news_context(
    db,
    league_id: str,
    my_team_id: str | None,
    season_id: str | None = None,
    mine: bool = False,
    before_id: int | None = None,
) -> dict:
    repo = NewsRepository(db)
    seasons = repo.seasons(league_id)
    if season_id is None and seasons:
        season_id = seasons[0]["id"]
    stories = repo.feed(
        league_id,
        season_id=season_id,
        team_id=my_team_id if mine and my_team_id else None,
        limit=PAGE + 1,
        before_id=before_id,
    )
    more = len(stories) > PAGE
    stories = stories[:PAGE]
    items = _items(db, stories, my_team_id)
    days: list[dict] = []
    for s in items:
        if not days or days[-1]["date"] != s["news_date"]:
            days.append(
                {"date": s["news_date"], "label": _day(s["news_date"]), "stories": []}
            )
        days[-1]["stories"].append(s)
    return {
        "news_days": days,
        "news_seasons": seasons,
        "news_season_id": season_id,
        "news_mine": mine,
        "news_more_before": stories[-1]["id"] if more and stories else None,
        "news_newest_id": repo.newest_id(league_id),
    }


def headlines(db, league_id: str, my_team_id: str | None) -> list[dict]:
    """The newest big stories, for the top of the Standings tab."""
    stories = NewsRepository(db).feed(league_id, min_weight=2, limit=HEADLINES)
    return _items(db, stories, my_team_id)


def _items(db, stories: list[dict], my_team_id: str | None) -> list[dict]:
    team_ids = {t for s in stories for t in s["team_ids"]}
    teams = {
        r["id"]: dict(r)
        for r in db.execute(
            "SELECT id, city, mascot FROM teams WHERE id = ANY(%s)", (list(team_ids),)
        ).fetchall()
    } if team_ids else {}  # fmt: skip
    out = []
    for s in stories:
        out.append(
            {
                **s,
                "icon": KIND_ICONS.get(s["kind"], "📰"),
                "label": KIND_LABELS.get(s["kind"], "News"),
                "teams": [teams[t] for t in s["team_ids"] if t in teams],
                "mine": bool(my_team_id and my_team_id in s["team_ids"]),
                "day": _day(s["news_date"]),
            }
        )
    return out


def _day(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.strftime('%a')}, {d.strftime('%B')} {d.day}, {d.year}"
