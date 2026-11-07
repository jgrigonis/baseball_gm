"""Franchise icons (src/api/services/icons.py): long-tenured, high-value
players, and the owner review counting the ones a team let go."""

from types import SimpleNamespace

import pytest

from src.api.services import icons, owner_review


@pytest.fixture
def lg(db_conn, factory):
    league = factory.league(state="season")
    seasons = [factory.season(year=2020 + i) for i in range(icons.ICON_SEASONS)]
    for s in seasons:
        factory.league_season(league, s)
    home = factory.team(city="Home", mascot="Club")
    away = factory.team(city="Away", mascot="Club")
    for t in (home, away):
        factory.league_season_team(league, seasons[-1], t)
    return SimpleNamespace(
        db=db_conn, f=factory, league=league, seasons=seasons, home=home, away=away
    )


def _played(x, player, team, seasons):
    for s in seasons:
        x.db.execute(
            """INSERT INTO player_season_stats
               (player_id, season_id, team_id, bat_games_played)
               VALUES (%s, %s, %s, 100)""",
            (player.id, s.id, team.id),
        )


def test_a_long_time_star_is_an_icon(lg):
    star = lg.f.rated_player(lg.home, lg.league, level=85)
    _played(lg, star, lg.home, lg.seasons)
    assert icons.find(lg.db, [(star.id, lg.home.id)]) == {
        (star.id, lg.home.id): icons.ICON_SEASONS
    }


def test_too_few_seasons_is_not(lg):
    star = lg.f.rated_player(lg.home, lg.league, level=85)
    _played(lg, star, lg.home, lg.seasons[1:])
    assert icons.find(lg.db, [(star.id, lg.home.id)]) == {}


def test_a_washed_up_veteran_is_not(lg):
    vet = lg.f.rated_player(lg.home, lg.league, level=40, age=36)
    _played(lg, vet, lg.home, lg.seasons)
    assert icons.find(lg.db, [(vet.id, lg.home.id)]) == {}


def test_seasons_elsewhere_dont_count(lg):
    star = lg.f.rated_player(lg.home, lg.league, level=85)
    _played(lg, star, lg.away, lg.seasons[:2])
    _played(lg, star, lg.home, lg.seasons[2:])
    assert icons.find(lg.db, [(star.id, lg.home.id)]) == {}


def test_attach_marks_roster_cards(lg):
    star = lg.f.rated_player(lg.home, lg.league, level=85)
    other = lg.f.rated_player(lg.home, lg.league, level=85)
    _played(lg, star, lg.home, lg.seasons)
    cards = [
        {"player_id": star.id, "overall": "A"},
        {"player_id": other.id, "overall": "A"},
    ]
    icons.attach(lg.db, lg.home.id, cards)
    assert cards[0]["icon_seasons"] == icons.ICON_SEASONS
    assert "icon_seasons" not in cards[1]


def test_the_review_counts_icons_traded_away(lg):
    star = lg.f.rated_player(lg.home, lg.league, level=85)
    vet = lg.f.rated_player(lg.home, lg.league, level=40, age=36)
    for p in (star, vet):
        _played(lg, p, lg.home, lg.seasons)
    last = lg.seasons[-1]
    lg.db.execute(
        """INSERT INTO trade_offers (id, league_id, season_id, from_team_id,
               to_team_id, status, created_on)
           VALUES ('t1', %s, %s, %s, %s, 'accepted', '2024-06-01')""",
        (lg.league.id, last.id, lg.home.id, lg.away.id),
    )
    for p in (star, vet):
        lg.db.execute(
            "INSERT INTO trade_offer_items VALUES ('t1', %s, %s)",
            (p.id, lg.home.id),
        )
    lost = owner_review._icons_lost(lg.db, lg.league.id, last.id, last.year)
    assert lost == {lg.home.id: 1}
