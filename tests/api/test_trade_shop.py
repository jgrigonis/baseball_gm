# tests/api/test_trade_shop.py
"""Shopping a player: every AI team's best offer at once, and taking one
(src/api/services/trade_shop.py)."""

from types import SimpleNamespace

import pytest

from src.api.services import trade_shop, trades
from src.api.services.injury_news import take_injury_news
from src.api.services.trades import TradeError
from tests.api.test_trades import _human, _offer, _team_of, lg  # noqa: F401


def _team_of_id(db, pid):
    return _team_of(db, SimpleNamespace(id=pid))


def _shop(lg, player):  # noqa: F811
    return trade_shop.shop(lg.db, lg.league.id, lg.gm, player.id)


def _with_prospects(lg):  # noqa: F811
    return [
        lg.factory.rated_player(lg.theirs, lg.league, r, status="minors")
        for r in (62, 60)
    ]


def test_an_ai_team_offers_its_best_package(lg):  # noqa: F811
    star = lg.factory.rated_player(lg.mine, lg.league, 72, name="Star")
    _with_prospects(lg)
    result = _shop(lg, star)
    assert result["player"].endswith("Star")
    (offer,) = result["offers"]
    assert offer["team_id"] == lg.theirs.id
    assert 1 <= len(offer["give"]) <= 2
    assert all(_team_of_id(lg.db, pid) == lg.theirs.id for pid in offer["give"])
    assert result["no_interest"] == []


def test_the_ai_takes_the_offer_it_made(lg):  # noqa: F811
    star = lg.factory.rated_player(lg.mine, lg.league, 72)
    _with_prospects(lg)
    (offer,) = _shop(lg, star)["offers"]
    result = trade_shop.take(lg.db, lg.league.id, lg.gm, star.id, lg.theirs.id)
    assert result["accepted"]
    assert _team_of(lg.db, star) == lg.theirs.id
    for pid in offer["give"]:
        assert _team_of_id(lg.db, pid) == lg.mine.id


def test_a_player_nobody_wants_gets_no_interest(lg):  # noqa: F811
    scrub = lg.factory.rated_player(lg.mine, lg.league, 45, status="minors")
    result = _shop(lg, scrub)
    assert result["offers"] == []
    assert result["no_interest"] == ["AI Club"]


def test_you_can_only_shop_your_own_player(lg):  # noqa: F811
    theirs = lg.factory.rated_player(lg.theirs, lg.league, 70)
    with pytest.raises(TradeError, match="isn't on your team"):
        _shop(lg, theirs)


def test_taking_a_shop_offer_skips_the_days_call_limit(lg):  # noqa: F811
    star = lg.factory.rated_player(lg.mine, lg.league, 72)
    _with_prospects(lg)
    big = lg.factory.rated_player(lg.theirs, lg.league, 76)
    for _ in range(trades.MAX_REJECTIONS_A_DAY):
        scrub = lg.factory.rated_player(lg.mine, lg.league, 50, status="minors")
        assert not _offer(lg, [scrub], [big])["accepted"]
    assert _shop(lg, star)["offers"]
    assert trade_shop.take(lg.db, lg.league.id, lg.gm, star.id, lg.theirs.id)[
        "accepted"
    ]


def test_other_people_hear_hes_on_the_block_once_a_day(lg):  # noqa: F811
    team = lg.factory.team(city="Other", mascot="Folks")
    lg.factory.league_season_team(lg.league, lg.season, team)
    other = _human(lg, team, "Other")
    star = lg.factory.rated_player(lg.mine, lg.league, 72, name="Star")
    _shop(lg, star)
    _shop(lg, star)
    news = take_injury_news(lg.db, other["id"])["trades"]
    assert len(news) == 1
    assert news[0]["event"] == "block"
    assert "are shopping" in news[0]["text"]
    # Not the GM doing the shopping.
    assert take_injury_news(lg.db, lg.gm["id"])["trades"] == []
