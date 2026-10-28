# tests/api/test_ai_trades.py
"""AI teams starting trades (src/api/services/ai_trades.py): offers to GMs,
which pop up and wait, and the rare trade between two AI teams."""

import pytest

from src.api.services import ai_trades, trades
from src.api.services.trades import TradeError
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.trade_repo import TradeRepository
from src.league.trades import ai_evaluator
from tests.api.test_trades import _news, _offer, _team_of, lg  # noqa: F401

TODAY = "2025-04-04"


@pytest.fixture
def ai(lg, monkeypatch):  # noqa: F811
    """lg where the AI team is in the race and has a prospect to spare, and
    my team is out of it with a veteran it should sell. Every AI team looks
    for a deal on every run, wanting to win by the same margin every day."""
    stances = {lg.mine.id: "seller", lg.theirs.id: "contender"}
    monkeypatch.setattr(
        trades, "stance", lambda conn, l, s, team_id: stances.get(team_id, "neutral")
    )
    monkeypatch.setattr(ai_evaluator, "margin", lambda *a: ai_evaluator.BASE_MARGIN)
    for chance in ("ACT_CHANCE", "RUSH_ACT_CHANCE"):
        monkeypatch.setattr(ai_trades, chance, dict.fromkeys(stances.values(), 1.0))
    lg.stances = stances
    lg.veteran = lg.factory.rated_player(lg.mine, lg.league, 70, age=35, name="Vet")
    lg.prospect = lg.factory.rated_player(lg.theirs, lg.league, 65, age=22, name="Kid")
    return lg


def _run(ctx, on=TODAY, deadline="2025-04-06"):
    league = dict(
        ctx.db.execute(
            "SELECT * FROM leagues WHERE id = %s", (ctx.league.id,)
        ).fetchone()
    )
    return ai_trades.run(ctx.db, league, ctx.season.id, on, deadline)


def _ai_offers(ctx):
    return ctx.db.execute(
        "SELECT * FROM trade_offers WHERE from_ai AND league_id = %s"
        " ORDER BY created_at",
        (ctx.league.id,),
    ).fetchall()


def test_an_ai_team_makes_a_gm_an_offer_that_pops_up(ai):
    assert _run(ai) == {"offers": 1, "trades": 0}
    [offer] = _ai_offers(ai)
    assert offer["from_team_id"] == ai.theirs.id
    assert offer["to_team_id"] == ai.mine.id
    assert offer["status"] == "pending"
    assert offer["expires_on"] == "2025-04-07"  # three league days, one GM
    full = TradeRepository(ai.db).get(offer["id"])
    assert [p["player_id"] for p in full["received"]] == [ai.veteran.id]
    assert ai.prospect.id in [p["player_id"] for p in full["sent"]]
    news = _news(ai, ai.gm)
    assert [n["event"] for n in news] == ["offer"]
    assert news[0]["popup"]
    assert _team_of(ai.db, ai.veteran) == ai.mine.id  # nothing moves yet


def test_a_gm_gets_one_open_ai_offer_at_a_time(ai):
    _run(ai)
    assert _run(ai, "2025-04-05") == {"offers": 0, "trades": 0}
    assert len(_ai_offers(ai)) == 1


def _turn_down(ctx):
    """I turn the offer down, and have another veteran it could ask for: an
    AI team doesn't make the same offer twice."""
    ctx.db.execute(
        "UPDATE trade_offers SET status = 'rejected' WHERE league_id = %s",
        (ctx.league.id,),
    )
    ctx.factory.rated_player(ctx.mine, ctx.league, 70, age=35, name="Vet2")


def test_a_gm_waits_a_few_days_for_the_next_ai_offer(ai):
    _run(ai, "2025-04-04", deadline="2025-04-10")
    _turn_down(ai)
    assert _run(ai, "2025-04-06", deadline="2025-04-10")["offers"] == 0
    # Three days on, in the rush.
    assert _run(ai, "2025-04-07", deadline="2025-04-10")["offers"] == 1


def test_ai_offers_are_further_apart_before_the_rush(ai):
    _run(ai, "2025-04-04", deadline="2025-06-30")
    _turn_down(ai)
    assert _run(ai, "2025-04-10", deadline="2025-06-30")["offers"] == 0
    assert _run(ai, "2025-04-14", deadline="2025-06-30")["offers"] == 1


def test_most_ai_offers_are_saved_for_the_rush(ai, monkeypatch):
    monkeypatch.setattr(ai_trades, "MAX_AI_OFFERS_BEFORE_RUSH", 1)
    _run(ai, "2025-04-04", deadline="2025-06-30")
    _turn_down(ai)
    assert _run(ai, "2025-05-04", deadline="2025-06-30")["offers"] == 0
    assert _run(ai, "2025-06-20", deadline="2025-06-30")["offers"] == 1


def test_a_gm_gets_a_few_ai_offers_a_season(ai, monkeypatch):
    monkeypatch.setattr(ai_trades, "MAX_AI_OFFERS_A_SEASON", 1)
    _run(ai)
    _turn_down(ai)
    assert _run(ai, "2025-04-10")["offers"] == 0


def test_an_ai_offer_expires_after_its_last_day(ai):
    _run(ai)
    [offer] = _ai_offers(ai)
    trades.close_due_on(ai.db, ai.league.id, "2025-04-06")
    assert TradeRepository(ai.db).get(offer["id"])["status"] == "pending"
    trades.close_due_on(ai.db, ai.league.id, "2025-04-07")
    assert TradeRepository(ai.db).get(offer["id"])["status"] == "expired"


def test_accepting_an_ai_offer_makes_the_trade(ai):
    _run(ai)
    [offer] = _ai_offers(ai)
    result = trades.respond(ai.db, ai.league.id, ai.gm, offer["id"], "accept")
    assert result["status"] == "accepted"
    assert _team_of(ai.db, ai.veteran) == ai.theirs.id
    assert _team_of(ai.db, ai.prospect) == ai.mine.id


def test_an_ai_team_that_no_longer_wants_its_deal_calls_it_off(ai, monkeypatch):
    _run(ai)
    [offer] = _ai_offers(ai)
    monkeypatch.setattr(trades, "_ai_still_wants", lambda *a: False)
    with pytest.raises(TradeError, match="changed their mind"):
        trades.respond(ai.db, ai.league.id, ai.gm, offer["id"], "accept")
    assert TradeRepository(ai.db).get(offer["id"])["status"] != "pending"
    assert _team_of(ai.db, ai.veteran) == ai.mine.id


def test_a_counter_to_an_ai_offer_gets_an_answer_at_once(ai):
    _run(ai)
    [offer] = _ai_offers(ai)
    result = trades.propose(
        ai.db,
        ai.league.id,
        ai.gm,
        ai.theirs.id,
        [ai.veteran.id],
        [ai.prospect.id],
        counter_of=offer["id"],
    )
    assert "accepted" in result
    assert TradeRepository(ai.db).get(offer["id"])["status"] == "countered"


def _all_ai(ctx):
    """Nobody runs my team any more: both teams are the AI's."""
    ctx.db.execute("UPDATE gms SET is_ai = TRUE WHERE team_id = %s", (ctx.mine.id,))
    ctx.stances[ctx.mine.id] = "seller"


def test_two_ai_teams_trade_at_once(ai):
    _all_ai(ai)
    assert list(GMRepository(ai.db).get_human_team_ids(ai.league.id)) == []
    assert _run(ai) == {"offers": 0, "trades": 1}
    [offer] = _ai_offers(ai)
    assert offer["status"] == "accepted"
    assert _team_of(ai.db, ai.veteran) == ai.theirs.id
    assert _team_of(ai.db, ai.prospect) == ai.mine.id


def test_an_ai_team_makes_one_ai_trade_a_season(ai):
    _all_ai(ai)
    _run(ai)
    # Another deal both would take.
    ai.factory.rated_player(ai.mine, ai.league, 70, age=35, name="Vet2")
    ai.factory.rated_player(ai.theirs, ai.league, 65, age=22, name="Kid2")
    assert _run(ai, "2025-04-05")["trades"] == 0


def test_the_ai_doesnt_look_after_the_deadline(ai):
    ai.db.execute(
        "UPDATE games SET completed = 1 WHERE season_id = %s", (ai.season.id,)
    )
    assert ai_trades.after_day(ai.db, ai.league.id, "2025-04-07") == {
        "offers": 0,
        "trades": 0,
    }
    assert _ai_offers(ai) == []


def test_the_ai_looks_every_day_in_the_deadline_rush():
    assert ai_trades._looks_today("2025-07-10", "2025-07-22")
    looks = [
        ai_trades._looks_today(f"2025-05-{d:02d}", "2025-07-31") for d in range(1, 31)
    ]
    assert sum(looks) == 10  # every third day before it


def test_neutral_ai_teams_dont_trade_with_each_other(ai):
    _all_ai(ai)
    ai.stances[ai.mine.id] = ai.stances[ai.theirs.id] = "neutral"
    ai_trades.ACT_CHANCE["neutral"] = ai_trades.RUSH_ACT_CHANCE["neutral"] = 1.0
    assert _run(ai)["trades"] == 0


def test_a_league_saves_most_ai_trades_for_the_rush():
    assert ai_trades.league_ai_trades(30, rush=True) == 5
    assert ai_trades.league_ai_trades(30, rush=False) == 1
    assert ai_trades.league_ai_trades(4, rush=True) == 1


def test_an_ai_team_doesnt_make_the_same_offer_twice(ai):
    _run(ai, "2025-04-04", deadline="2025-04-10")
    ai.db.execute(
        "UPDATE trade_offers SET status = 'rejected' WHERE league_id = %s",
        (ai.league.id,),
    )
    _run(ai, "2025-04-08", deadline="2025-04-10")
    repo = TradeRepository(ai.db)
    made = [repo.get(o["id"]) for o in _ai_offers(ai)]
    players = [
        frozenset(p["player_id"] for p in o["sent"] + o["received"]) for o in made
    ]
    assert len(set(players)) == len(players)
