# src/api/view_models/news.py
"""The News tab (src/api/services/news/) and the Standings tab's headlines
strip: stories grouped by league date, with each team's badge."""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from markupsafe import Markup, escape

from src.api.services.news.names import TOKEN
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
    "season_award": "🎖️",
    "division": "🚩",
    "series": "🥇",
    "champion": "🏆",
    "front_office": "💼",
    "retirement": "👋",
    "clubhouse": "😤",
    "hall_of_fame": "🏛️",
    "free_agency": "✍️",
    "record": "📖",
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
    "season_award": "Award",
    "division": "Division",
    "series": "Playoffs",
    "champion": "Champion",
    "front_office": "Front office",
    "retirement": "Retirement",
    "clubhouse": "Clubhouse",
    "hall_of_fame": "Hall of Fame",
    "free_agency": "Free agency",
    "record": "Record",
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
    items = _items(db, league_id, stories, my_team_id)
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
    return _items(db, league_id, stories, my_team_id)


def _items(
    db, league_id: str, stories: list[dict], my_team_id: str | None
) -> list[dict]:
    team_ids = {t for s in stories for t in s["team_ids"]}
    teams = {
        r["id"]: dict(r)
        for r in db.execute(
            "SELECT id, city, mascot FROM teams WHERE id = ANY(%s)", (list(team_ids),)
        ).fetchall()
    } if team_ids else {}  # fmt: skip
    gm_ids = {
        m[2] for s in stories for m in TOKEN.finditer(s["headline"] + s["body"])
        if m[1] == "g"
    }  # fmt: skip
    gms = {
        r["id"]: dict(r)
        for r in db.execute(
            """SELECT g.id, g.persona_id, u.username FROM gms g
               LEFT JOIN users u ON u.id = g.user_id WHERE g.id = ANY(%s)""",
            (list(gm_ids),),
        ).fetchall()
    } if gm_ids else {}  # fmt: skip
    out = []
    for s in stories:
        out.append(
            {
                **s,
                "headline_html": linked(s["headline"], league_id, gms),
                "body_html": linked(s["body"], league_id, gms),
                "icon": KIND_ICONS.get(s["kind"], "📰"),
                "label": KIND_LABELS.get(s["kind"], "News"),
                "teams": [teams[t] for t in s["team_ids"] if t in teams],
                "mine": bool(my_team_id and my_team_id in s["team_ids"]),
                "day": _day(s["news_date"]),
                "box_event": _box_event(s),
            }
        )
    return out


def _box_event(story: dict) -> str | None:
    """The All-Star break game a story is about ("all_star" or "rookie",
    news/events.py _game_story), for a Box score link to it
    (openAllStarBox), else None."""
    for event, prefix in (("all_star", "allstar:game:"), ("rookie", "rookie:game:")):
        if story.get("key") == f"{prefix}{story.get('season_id')}":
            return event
    return None


def linked(text: str, league_id: str, gms: dict[str, dict]) -> Markup:
    """A story's text with the players, teams and GMs it names as links
    (the tokens services/news/names.py writes)."""
    out, at = [], 0
    for m in TOKEN.finditer(text or ""):
        out.append(escape(text[at : m.start()]))
        out.append(_link(m[1], m[2], m[3], league_id, gms))
        at = m.end()
    out.append(escape((text or "")[at:]))
    return Markup("").join(out)


def _link(kind: str, ref: str, text: str, league_id: str, gms: dict) -> Markup:
    if kind == "p":
        return Markup(
            '<a class="news-link" href="#" onclick="event.preventDefault();'
            " openPlayerPanel('{}')\">{}</a>"
        ).format(ref, text)
    if kind == "t":
        url = f"/leagues/{league_id}/stats?team_id={ref}"
        return Markup(
            '<a class="news-link" href="{}" hx-get="{}" hx-target="#tab-content"'
            ' hx-push-url="true">{}</a>'
        ).format(url, url, text)
    gm = gms.get(ref) or {}
    if gm.get("persona_id"):
        url = f"/leagues/{league_id}/personas/{gm['persona_id']}?back=headlines"
    elif gm.get("username"):
        url = f"/leagues/{league_id}/gms/{quote(gm['username'])}?back=headlines"
    else:
        url = None
    if url:
        return Markup(
            'GM <a class="news-link" href="{}" hx-get="{}" hx-target="#tab-content"'
            ' hx-push-url="true">{}</a>'
        ).format(url, url, text)
    return Markup("GM {}").format(text)


def _day(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.strftime('%a')}, {d.strftime('%B')} {d.day}, {d.year}"
