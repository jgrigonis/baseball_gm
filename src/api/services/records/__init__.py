# src/api/services/records/__init__.py
"""
The league record book (the Records tab, below Hall of Fame).

  season      most (or best) in a season, plus record watch    seasons.py, watch.py
  game        most in one game                                 stored.py
  streaks     players' and clubs' streaks                      stored.py
  career      most in a career                                 seasons.py
  postseason  playoff games, series, careers and titles        postseason.py
  team        a club's season and its single games             teams.py
  gms         the people who ran clubs here                    gms.py

Every view can be narrowed to one club (franchise records). Season, career,
team and postseason records are worked out from the season lines and games
on each visit; single games and streaks are kept as games are played
(play.py), with the backstory replayed into games to start them
(replay.py). Backstory seasons count like played ones, so a new league's
book starts full.
"""

from __future__ import annotations

from src.api.services.records import gms, postseason, seasons, stored, teams, watch

VIEWS = [
    ("season", "Season"),
    ("game", "Single game"),
    ("streaks", "Streaks"),
    ("career", "Career"),
    ("postseason", "Postseason"),
    ("team", "Team"),
    ("gms", "GMs"),
]
VIEW_KEYS = {k for k, _ in VIEWS}


def current_season(conn, league_id: str) -> str | None:
    row = conn.execute(
        """SELECT s.id FROM seasons s
           JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s AND NOT s.is_backstory
           ORDER BY s.year DESC LIMIT 1""",
        (league_id,),
    ).fetchone()
    return row["id"] if row else None


def clubs(conn, league_id: str) -> list[dict]:
    """The league's clubs now, for the franchise picker, by city."""
    sid = current_season(conn, league_id)
    if not sid:
        return []
    rows = conn.execute(
        """SELECT t.id, t.city, t.mascot FROM league_season_teams lst
           JOIN teams t ON t.id = lst.team_id
           WHERE lst.league_id = %s AND lst.season_id = %s
           ORDER BY t.city, t.mascot""",
        (league_id, sid),
    ).fetchall()
    return [{"id": r["id"], "name": f"{r['city']} {r['mascot']}"} for r in rows]


def book(
    conn,
    league_id: str,
    view: str,
    team_id: str | None,
    my_team_id: str | None,
    my_user_id: str | None = None,
) -> dict:
    """The page's context: ``sections`` is a list of (title, [Card])."""
    if view not in VIEW_KEYS:
        view = "season"
    club_list = clubs(conn, league_id)
    if team_id and not any(c["id"] == team_id for c in club_list):
        team_id = None
    sections: list[tuple[str, list]] = []
    watching: list[dict] = []
    if view == "season" and not team_id:
        watching = watch.watch(
            conn, league_id, current_season(conn, league_id), my_team_id
        )
    if view in ("season", "career"):
        rows = seasons.load(conn, league_id, team_id)
        if view == "season":
            cards = seasons.season_cards(
                rows, seasons.season_info(conn, league_id), my_team_id, team_id
            )
        else:
            cards = seasons.career_cards(
                rows, current_season(conn, league_id), my_team_id, team_id
            )
        sections = [("Batting", cards["batting"]), ("Pitching", cards["pitching"])]
    elif view == "team":
        info = seasons.season_info(conn, league_id)
        sections = [
            (
                "Season",
                teams.season_cards(
                    teams.season_lines(conn, league_id), info, my_team_id, team_id
                ),
            ),
            ("Single game", teams.game_cards(conn, league_id, my_team_id, team_id)),
        ]
    elif view == "game":
        cards = stored.game_cards(conn, league_id, my_team_id, team_id)
        sections = [("Batting", cards["batting"]), ("Pitching", cards["pitching"])]
    elif view == "streaks":
        cards = stored.streak_cards(conn, league_id, my_team_id, team_id)
        sections = [("Players", cards["players"]), ("Clubs", cards["teams"])]
    elif view == "postseason":
        series = postseason.series_cards(conn, league_id, my_team_id, team_id)
        sections = [
            (
                "Titles",
                postseason.team_title_cards(conn, league_id, my_team_id, team_id),
            ),
            (
                "Single game",
                postseason.game_cards(conn, league_id, my_team_id, team_id),
            ),
            ("Series", series["counts"]),
            ("Series rates: top ten", series["rates"]),
            ("Career", postseason.career_cards(conn, league_id, my_team_id, team_id)),
        ]
    elif view == "gms":
        sections = [("People", gms.cards(conn, league_id, my_user_id, team_id))]
    return {
        "rec_view": view,
        "rec_views": VIEWS,
        "rec_team_id": team_id,
        "rec_team_name": next(
            (c["name"] for c in club_list if c["id"] == team_id), None
        ),
        "rec_clubs": club_list,
        "rec_sections": sections,
        "rec_watch": watching,
        "rec_empty": all(c.empty for _, cs in sections for c in cs),
    }
