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


def test_history_links_each_seasons_retirements(db_conn, factory):
    """History counts each season's retirees and links to them; the link
    shows that season, not this offseason, and has no draft button."""
    from src.api.view_models.seasons import history_context

    db = db_conn
    league = factory.league(state="offseason")
    seasons = [factory.season(year=y) for y in (2025, 2026, 2027)]
    for s in seasons:
        factory.league_season(league, s)
    team = factory.team()
    old, recent = factory.prospect(league.id), factory.prospect(league.id)
    _retire(db, league, seasons[0], old, team)
    _retire(db, league, seasons[1], recent, team)

    rows = {r["year"]: r for r in history_context(db, league.id, None)["history_rows"]}
    assert (rows[2025]["retired"], rows[2026]["retired"], rows[2027]["retired"]) == (
        1,
        1,
        0,
    )
    html = templates.get_template("dashboard/partials/history.html").render(
        league_id=league.id, is_viewer=True, history_rows=list(rows.values())
    )
    assert f"/retirement?season_id={seasons[0].id}" in html
    assert f"/retirement?season_id={seasons[2].id}" not in html

    ctx = retirement_context(db, league.id, team.id, seasons[0].id)
    assert [r["player_id"] for r in ctx["retired_players"]] == [old.id]
    html = templates.get_template("dashboard/partials/retirement.html").render(
        league_id=league.id, is_viewer=False, **ctx
    )
    assert "after the 2025 season" in html
    assert "Continue to Draft" not in html

    # No season, or the season that just ended, is this offseason's page.
    for sid in (None, seasons[1].id):
        ctx = retirement_context(db, league.id, team.id, sid)
        assert [r["player_id"] for r in ctx["retired_players"]] == [recent.id]
        assert ctx["history_season"] is None


def test_retirement_ignores_another_leagues_season(db_conn, factory):
    db = db_conn
    league, other = factory.league(state="offseason"), factory.league()
    seasons = [factory.season(year=y) for y in (2025, 2026)]
    for s in seasons:
        factory.league_season(league, s)
    foreign = factory.season(year=2020)
    factory.league_season(other, foreign)

    ctx = retirement_context(db, league.id, None, foreign.id)
    assert ctx["history_season"] is None
