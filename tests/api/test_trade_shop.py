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
    assert result["why"] == {"fit": ["AI Club"]}
    assert result["close"] == []


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


# ── Dumping salary ─────────────────────────────────────────────────────────


def test_dump_lists_who_would_take_him_and_the_trade_goes_through(lg):  # noqa: F811
    regular = lg.factory.rated_player(lg.mine, lg.league, 68)
    lg.factory.rated_player(lg.theirs, lg.league, 40, status="minors")
    result = trade_shop.dump(lg.db, lg.league.id, lg.gm, regular.id)
    (offer,) = result["offers"]
    assert offer["team_id"] == lg.theirs.id
    assert len(offer["give"]) == 1
    assert all(_team_of_id(lg.db, pid) == lg.theirs.id for pid in offer["give"])
    taken = trade_shop.dump_take(lg.db, lg.league.id, lg.gm, regular.id, lg.theirs.id)
    assert taken["accepted"]
    assert _team_of(lg.db, regular) == lg.theirs.id
    for pid in offer["add"]:
        assert _team_of_id(lg.db, pid) == lg.theirs.id
    assert _team_of_id(lg.db, offer["give"][0]) == lg.mine.id


def test_the_kept_shop_stamp_changes_when_a_roster_does(lg):  # noqa: F811
    """The Trades tab shows a kept shop list again only while the stamp is
    the same: shopping doesn't change it, a trade does."""
    star = lg.factory.rated_player(lg.mine, lg.league, 72)
    _with_prospects(lg)
    before = trade_shop.stamp(lg.db, lg.league.id)
    assert before
    _shop(lg, star)
    assert trade_shop.stamp(lg.db, lg.league.id) == before
    trade_shop.take(lg.db, lg.league.id, lg.gm, star.id, lg.theirs.id)
    assert trade_shop.stamp(lg.db, lg.league.id) != before


def _deal(lg, player, team, salary, guaranteed):  # noqa: F811
    from src.db.repositories.contract_repo import ContractRepository
    from src.player import contracts as ct

    lg.db.execute("DELETE FROM player_contracts WHERE player_id = %s", (player.id,))
    ContractRepository(lg.db).insert_deal(
        player.id,
        lg.league.id,
        team.id,
        ct.Deal(salary, 3, "rookie"),
        2025,
        guaranteed,
    )


def test_dump_savings_are_net_of_the_throw_in_who_lands_in_the_minors(lg):  # noqa: F811
    """A just-drafted rookie on the 40-man: on the payroll, not guaranteed.
    A guaranteed throw-in's salary counts against the savings; one whose
    deal isn't guaranteed doesn't (he joins the minors) but is shown."""
    rookie = lg.factory.rated_player(lg.mine, lg.league, 50)
    _deal(lg, rookie, lg.mine, 780_000, False)
    owed = lg.factory.rated_player(lg.theirs, lg.league, 50)
    _deal(lg, owed, lg.theirs, 1_600_000, True)
    farm = lg.factory.rated_player(lg.theirs, lg.league, 50, status="minors")
    _deal(lg, farm, lg.theirs, 3_500_000, False)
    ctx = SimpleNamespace(season_id=lg.season.id, player_id=rookie.id)
    offers = [{"give": [owed.id], "add": []}, {"give": [farm.id], "add": []}]
    deal = trade_shop._payroll_effects(lg.db, ctx, offers)
    assert not deal["guaranteed"]
    assert offers[0]["saved"] == 780_000 - 1_600_000
    assert offers[0]["unguaranteed"] == 0
    assert offers[1]["saved"] == 780_000
    assert offers[1]["unguaranteed"] == 3_500_000
