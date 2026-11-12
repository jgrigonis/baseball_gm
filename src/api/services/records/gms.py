# src/api/services/records/gms.py
"""
GM records: what the people who ran clubs in this league did, from their
career seasons (gm_career_seasons, the profile page's source). AI GMs keep
no career, so it's people only. A season still being played counts for
wins, marked live.
"""

from __future__ import annotations

from collections import defaultdict

from src.api.services.records.core import Card, card, rate3

MIN_PCT_SEASONS = 3


def cards(conn, league_id: str, my_user_id: str | None, team_id=None) -> list[Card]:
    rows = conn.execute(
        """SELECT c.user_id, c.season_id, c.season_year, c.team_city, c.team_mascot,
                  c.wins, c.losses, c.playoff_result, c.final,
                  COALESCE(u.username, u.display_name) AS name, u.username,
                  t.id AS team_id
           FROM gm_career_seasons c
           JOIN users u ON u.id = c.user_id
           LEFT JOIN league_season_teams lst
             ON lst.league_id = c.league_id AND lst.season_id = c.season_id
           LEFT JOIN teams t ON t.id = lst.team_id
             AND t.city = c.team_city AND t.mascot = c.team_mascot
           WHERE c.league_id = %s""",
        (league_id,),
    ).fetchall()
    rows = [r for r in rows if r["team_id"] or not team_id]
    if team_id:
        rows = [r for r in rows if r["team_id"] == team_id]
    per: dict[str, dict] = defaultdict(lambda: {"seasons": [], "w": 0, "l": 0})
    for r in rows:
        p = per[r["user_id"]]
        p.update(name=r["name"], username=r["username"], user_id=r["user_id"])
        p["seasons"].append(r)
        p["w"] += r["wins"]
        p["l"] += r["losses"]

    def perf(p, value, shown, detail="", order=None, active=False):
        years = sorted(s["season_year"] for s in p["seasons"])
        return {
            "value": value,
            "shown": shown,
            "order": order or f"{years[0]:05d}",
            "name": p["name"],
            "team": "",
            "detail": detail
            or (f"{years[0]}–{years[-1]}" if years[0] != years[-1] else str(years[0])),
            "href": f"/gms/{p['username']}" if p.get("username") else None,
            "active": active,
            "is_mine": p["user_id"] == my_user_id,
        }

    people = list(per.values())
    titles = [
        perf(p, n, str(n))
        for p in people
        if (n := sum(1 for s in p["seasons"] if s["playoff_result"] == "Champion"))
    ]
    trips = [
        perf(p, n, str(n))
        for p in people
        if (n := sum(1 for s in p["seasons"] if s["playoff_result"]))
    ]
    wins = [perf(p, p["w"], str(p["w"])) for p in people if p["w"]]
    seasons_run = [perf(p, len(p["seasons"]), str(len(p["seasons"]))) for p in people]
    pct = [
        perf(p, round(p["w"] / (p["w"] + p["l"]), 4), rate3(p["w"] / (p["w"] + p["l"])))
        for p in people
        if sum(1 for s in p["seasons"] if s["final"]) >= MIN_PCT_SEASONS
        and p["w"] + p["l"]
    ]
    best = []
    for p in people:
        for s in p["seasons"]:
            if s["wins"]:
                best.append(
                    perf(
                        p, s["wins"], f"{s['wins']}-{s['losses']}",
                        f"{s['season_year']} · {s['team_city']} {s['team_mascot']}",
                        order=f"{s['season_year']:05d}", active=not s["final"],
                    )
                )  # fmt: skip
    return [
        card("gm-titles", "Most titles", titles),
        card("gm-trips", "Most playoff trips", trips),
        card("gm-wins", "Most wins", wins, note="Regular season"),
        card("gm-best", "Best season", best, note="Most wins"),
        card(
            "gm-pct",
            "Best winning percentage",
            pct,
            note=f"{MIN_PCT_SEASONS} finished seasons",
        ),  # fmt: skip
        card("gm-seasons", "Most seasons", seasons_run),
    ]
