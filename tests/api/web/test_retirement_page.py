# tests/api/web/test_retirement_page.py
"""The retirement page puts a ★ by every retiree who was ever an All-Star,
with the count when there was more than one selection."""

from src.api.view_models.seasons import retirement_context
from src.db.repositories.all_star_repo import AllStarRepository
from src.web.utils import templates


def _all_star(db, season, player, team):
    AllStarRepository(db).save_all_stars(
        season.id,
        [
            {
                "player_id": player.id,
                "team_id": team.id,
                "slot": "lf",
                "points": 10,
                "wildcard": False,
            }
        ],
    )


def _retire(db, league, season, player, team):
    db.execute(
        "INSERT INTO player_retirements (player_id, league_id, season_id, former_team_id)"
        " VALUES (%s, %s, %s, %s)",
        (player.id, league.id, season.id, team.id),
    )


def test_retirees_carry_their_all_star_years(db_conn, factory):
    db = db_conn
    league = factory.league(state="offseason")
    seasons = [factory.season(year=y) for y in (2025, 2026, 2027)]
    for s in seasons:
        factory.league_season(league, s)
    team = factory.team()
    star, twice, plain = (factory.prospect(league.id) for _ in range(3))
    _all_star(db, seasons[1], star, team)
    _all_star(db, seasons[0], twice, team)
    _all_star(db, seasons[1], twice, team)
    for p in (star, twice, plain):
        _retire(db, league, seasons[1], p, team)

    ctx = retirement_context(db, league.id, team.id)

    years = {r["player_id"]: r["all_star_years"] for r in ctx["retired_players"]}
    assert years == {star.id: [2026], twice.id: [2025, 2026], plain.id: []}

    html = templates.get_template("dashboard/partials/retirement.html").render(
        league_id=league.id, is_viewer=False, **ctx
    )
    assert 'title="All-Star 2026">★</span>' in html
    assert 'title="All-Star 2025, 2026">★2×</span>' in html
    assert html.count("all-star-tag") == 2


def test_no_retirees_no_query(db_conn):
    assert AllStarRepository(db_conn).years_by_player([]) == {}
