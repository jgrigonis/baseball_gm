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
    # Enough for the notice to open Trades with his team and him picked.
    assert news[0]["team_id"] == lg.mine.id
    assert news[0]["player_id"] == star.id
    # Not the GM doing the shopping.
    assert take_injury_news(lg.db, lg.gm["id"])["trades"] == []


# ── Dumping salary ─────────────────────────────────────────────────────────


def test_dump_lists_who_would_take_him_and_the_trade_goes_through(lg):  # noqa: F811
    regular = lg.factory.rated_player(lg.mine, lg.league, 68)
    _deal(lg, regular, lg.mine, 1_000_000, True)
    lg.factory.rated_player(lg.theirs, lg.league, 40, status="minors")
    result = trade_shop.dump(lg.db, lg.league.id, lg.gm, regular.id)
    (offer,) = result["offers"]
    assert offer["team_id"] == lg.theirs.id
    assert offer["saved"] > 0
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
    """A throw-in on his team's payroll counts against the savings, even if
    his deal isn't guaranteed yet; a farm throw-in's doesn't but is shown."""
    rookie = lg.factory.rated_player(lg.mine, lg.league, 50)
    _deal(lg, rookie, lg.mine, 780_000, True)
    owed = lg.factory.rated_player(lg.theirs, lg.league, 50)
    _deal(lg, owed, lg.theirs, 1_600_000, True)
    fresh = lg.factory.rated_player(lg.theirs, lg.league, 50)
    _deal(lg, fresh, lg.theirs, 2_000_000, False)
    farm = lg.factory.rated_player(lg.theirs, lg.league, 50, status="minors")
    _deal(lg, farm, lg.theirs, 3_500_000, False)
    ctx = SimpleNamespace(season_id=lg.season.id, player_id=rookie.id)
    offers = [
        {"give": [owed.id], "add": []},
        {"give": [farm.id], "add": []},
        {"give": [fresh.id], "add": []},
    ]
    trade_shop._payroll_effects(lg.db, ctx, offers)
    assert offers[0]["saved"] == 780_000 - 1_600_000
    assert offers[0]["unguaranteed"] == 0
    assert offers[1]["saved"] == 780_000
    assert offers[1]["unguaranteed"] == 3_500_000
    assert offers[2]["saved"] == 780_000 - 2_000_000
    assert offers[2]["unguaranteed"] == 0


def test_no_dump_for_a_deal_that_isnt_guaranteed(lg):  # noqa: F811
    """A just-drafted rookie on the 40-man: sending him down or releasing
    him clears his salary for free, so there's nothing to dump."""
    rookie = lg.factory.rated_player(lg.mine, lg.league, 68)
    _deal(lg, rookie, lg.mine, 780_000, False)
    lg.factory.rated_player(lg.theirs, lg.league, 40, status="minors")
    result = trade_shop.dump(lg.db, lg.league.id, lg.gm, rookie.id)
    assert result["guaranteed"] is False
    assert result["offers"] == []
    with pytest.raises(TradeError, match="isn't guaranteed"):
        trade_shop.dump_take(lg.db, lg.league.id, lg.gm, rookie.id, lg.theirs.id)


# ── Absorbing salary ───────────────────────────────────────────────────────


def test_absorb_lists_big_contracts_for_him_and_the_trade_goes_through(lg):  # noqa: F811
    """They send a big contract they'd do better without (a blitz league has
    no budgets, so here it's one worth less to them than he is) and the
    trade goes through; the payroll line counts the deal coming your way."""
    from unittest.mock import patch

    from src.league.trades.ai_proposer import AbsorbOffer

    kid = lg.factory.rated_player(lg.mine, lg.league, 60)
    _deal(lg, kid, lg.mine, 780_000, True)
    vet = lg.factory.rated_player(lg.theirs, lg.league, 62)
    _deal(lg, vet, lg.theirs, 2_000_000, True)

    def fake(ai, seller, target, days_left, blocked, fits):
        big = next(a for a in ai.roster if a.id == vet.id)
        return AbsorbOffer([big], big.salary - target.salary, 3.0)

    with patch.object(trade_shop, "absorb_offer_or_why", fake):
        result = trade_shop.absorb(lg.db, lg.league.id, lg.gm, kid.id)
        (offer,) = result["offers"]
        assert offer["give"] == [vet.id]
        assert offer["saved"] == 780_000 - 2_000_000
        assert offer["through"] == {vet.id: 2027}
        with patch.object(
            trades, "ai_answer", lambda *a: SimpleNamespace(accept=True, reason="Deal.")
        ):
            taken = trade_shop.absorb_take(
                lg.db, lg.league.id, lg.gm, kid.id, lg.theirs.id
            )
    assert taken["accepted"]
    assert _team_of(lg.db, kid) == lg.theirs.id
    assert _team_of_id(lg.db, vet.id) == lg.mine.id


def test_absorb_says_why_a_team_has_nothing(lg):  # noqa: F811
    kid = lg.factory.rated_player(lg.mine, lg.league, 60)
    _deal(lg, kid, lg.mine, 30_000_000, True)
    result = trade_shop.absorb(lg.db, lg.league.id, lg.gm, kid.id)
    assert result["offers"] == []
    assert result["why"] == {"big": ["AI Club"]}


def test_absorb_stays_inside_your_owners_limit(lg):  # noqa: F811
    """A package past your owner's hard limit isn't offered: they'd refuse it."""
    kid = lg.factory.rated_player(lg.mine, lg.league, 60)
    _deal(lg, kid, lg.mine, 780_000, True)
    ctx = trade_shop._Ctx(lg.db, lg.league.id, lg.gm, kid.id)
    fits = ctx.owner_fits()
    assert fits is not None
    assert fits(500_000)
    assert not fits(50_000_000)
