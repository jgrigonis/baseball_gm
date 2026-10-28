# tests/api/test_trade_picks.py
"""Draft picks in trades (src/league/trades/draft_picks.py,
src/api/services/trades.py), and trades in the offseason."""

import pytest

from src.api.services import offseason_service, team_states, trades
from src.api.services.trades import TradeError
from src.db.repositories.trade_repo import TradeRepository
from src.league.trades import draft_picks
from src.league.trades.draft_picks import Pick
from tests.api.test_trades import _human, _team_of, lg  # noqa: F401

NEXT = 2026  # the draft after the 2025 season


@pytest.fixture
def picks(lg):  # noqa: F811
    """lg with draft pick trades on."""
    lg.db.execute(
        "UPDATE leagues SET pick_trades = TRUE WHERE id = %s", (lg.league.id,)
    )
    return lg


def _league(ctx):
    return dict(
        ctx.db.execute(
            "SELECT * FROM leagues WHERE id = %s", (ctx.league.id,)
        ).fetchone()
    )


def _pick(team, rnd=1, year=NEXT):
    return Pick(year, rnd, team.id).id


def _owner(ctx, pick_id):
    return draft_picks.owner(ctx.db, ctx.league.id, draft_picks.parse(pick_id))


def _propose(ctx, give, get, to=None):
    return trades.propose(
        ctx.db, ctx.league.id, ctx.gm, (to or ctx.theirs).id, give, get
    )


def test_a_team_has_its_first_five_rounds_to_trade(picks):
    cards = trades.pick_cards(picks.db, _league(picks), picks.season.id, picks.mine.id)
    assert [c["player_id"] for c in cards] == [
        _pick(picks.mine, r) for r in range(1, 6)
    ]
    assert cards[0]["last_name"] == "2026 1st round (My Team)"
    assert cards[0]["roster_status"] == "pick"


def test_no_picks_unless_the_league_trades_them(lg):  # noqa: F811
    assert trades.pick_cards(lg.db, _league(lg), lg.season.id, lg.mine.id) == []
    spare = lg.factory.rated_player(lg.theirs, lg.league, 50, status="minors")
    with pytest.raises(TradeError, match="doesn't trade draft picks"):
        _propose(lg, [_pick(lg.mine)], [spare.id])


def test_an_ai_team_takes_a_first_round_pick_for_a_spare_player(picks):
    spare = picks.factory.rated_player(picks.theirs, picks.league, 52, status="minors")
    result = _propose(picks, [_pick(picks.mine)], [spare.id])
    assert result["accepted"], result["reason"]
    assert _owner(picks, _pick(picks.mine)) == picks.theirs.id
    assert _team_of(picks.db, spare) == picks.mine.id
    [trade] = TradeRepository(picks.db).history(picks.league.id)
    assert [p["last_name"] for p in trade["sent"]] == ["2026 1st round (My Team)"]


def test_an_ai_team_wont_give_its_first_rounder_for_nothing_much(picks):
    spare = picks.factory.rated_player(picks.mine, picks.league, 50, status="minors")
    result = _propose(picks, [spare.id], [_pick(picks.theirs)])
    assert not result["accepted"]
    assert _owner(picks, _pick(picks.theirs)) == picks.theirs.id


def test_picks_can_go_both_ways(picks):
    result = _propose(picks, [_pick(picks.mine, 1)], [_pick(picks.theirs, 3)])
    assert result["accepted"], result["reason"]
    assert _owner(picks, _pick(picks.mine, 1)) == picks.theirs.id
    assert _owner(picks, _pick(picks.theirs, 3)) == picks.mine.id


@pytest.mark.parametrize(
    "pick_id, error",
    [
        ("mine-r6", "first 5 rounds"),
        ("mine-2027", "2026 draft"),
        ("theirs-as-mine", "isn't that team's"),
        ("pick:garbage", "2026 draft"),
    ],
)
def test_only_owned_picks_in_the_next_drafts_first_rounds(picks, pick_id, error):
    pick_id = {
        "mine-r6": _pick(picks.mine, 6),
        "mine-2027": _pick(picks.mine, 1, year=2027),
        "theirs-as-mine": _pick(picks.theirs),
    }.get(pick_id, pick_id)
    spare = picks.factory.rated_player(picks.theirs, picks.league, 50, status="minors")
    with pytest.raises(TradeError, match=error):
        _propose(picks, [pick_id], [spare.id])


def test_a_traded_pick_calls_off_other_offers_for_it(picks):
    picks.db.execute("DELETE FROM gms WHERE team_id = %s", (picks.theirs.id,))
    other = _human(picks, picks.theirs, "Them")
    third = picks.factory.team(city="Third", mascot="Club")
    picks.factory.league_season_team(picks.league, picks.season, third)
    picks.factory.gm(team=third, league=picks.league, is_ai=True)
    picks.db.execute(
        "UPDATE leagues SET trade_vote = FALSE WHERE id = %s", (picks.league.id,)
    )
    a = picks.factory.rated_player(picks.theirs, picks.league, 52, status="minors")
    waiting = _propose(picks, [_pick(picks.mine)], [a.id])["offer_id"]
    b = picks.factory.rated_player(third, picks.league, 52, status="minors")
    assert _propose(picks, [_pick(picks.mine)], [b.id], to=third)["accepted"]
    assert TradeRepository(picks.db).get(waiting)["status"] == "void"
    with pytest.raises(TradeError):
        trades.respond(picks.db, picks.league.id, other, waiting, "accept")


# ── The offseason ────────────────────────────────────────────────────────


def _offseason(ctx):
    ctx.db.execute(
        "UPDATE games SET completed = 1 WHERE season_id = %s", (ctx.season.id,)
    )
    ctx.db.execute(
        "UPDATE leagues SET state = 'offseason' WHERE id = %s", (ctx.league.id,)
    )


def test_trades_open_again_in_the_offseason(picks):
    _offseason(picks)
    spare = picks.factory.rated_player(picks.theirs, picks.league, 52, status="minors")
    result = _propose(picks, [_pick(picks.mine)], [spare.id])
    assert result["accepted"], result["reason"]


def test_ai_teams_judge_offseason_trades_without_last_seasons_race(picks):
    _offseason(picks)
    [row] = [
        r
        for t, r in team_states.current(
            picks.db, picks.league.id, picks.season.id, "2025-11-01"
        ).items()
        if t == picks.theirs.id
    ]
    assert row["inputs"]["games_back"] is None
    assert not team_states.in_race(row)


def test_the_offseason_closes_offers_from_the_season_before(picks, monkeypatch):
    picks.db.execute("DELETE FROM gms WHERE team_id = %s", (picks.theirs.id,))
    _human(picks, picks.theirs, "Them")
    a = picks.factory.rated_player(picks.theirs, picks.league, 52, status="minors")
    offer_id = _propose(picks, [_pick(picks.mine)], [a.id])["offer_id"]
    _offseason(picks)

    class Stop(Exception):
        pass

    def close_then_stop(conn, league_id):
        close_all(conn, league_id)
        raise Stop  # the rest of the offseason isn't this test's

    close_all = trades.close_all
    monkeypatch.setattr(trades, "close_all", close_then_stop)
    with pytest.raises(Stop):
        offseason_service.run_offseason(picks.league.id, picks.db)
    assert TradeRepository(picks.db).get(offer_id)["status"] == "expired"


def test_the_draft_calls_off_offers_with_its_picks(picks):
    picks.db.execute("DELETE FROM gms WHERE team_id = %s", (picks.theirs.id,))
    _human(picks, picks.theirs, "Them")
    a = picks.factory.rated_player(picks.theirs, picks.league, 52, status="minors")
    with_pick = _propose(picks, [_pick(picks.mine)], [a.id])["offer_id"]
    trades.draft_run(picks.db, picks.league.id, NEXT)
    assert TradeRepository(picks.db).get(with_pick)["status"] == "void"


def test_in_the_draft_its_own_picks_trade_until_it_runs(picks):
    picks.db.execute(
        "UPDATE leagues SET state = 'draft' WHERE id = %s", (picks.league.id,)
    )
    draft = picks.factory.draft(league=picks.league, season=picks.season)
    league = _league(picks)
    assert draft_picks.draft_year(picks.db, league, 2025) == 2025
    picks.db.execute("UPDATE drafts SET state = 'complete' WHERE id = %s", (draft.id,))
    assert draft_picks.draft_year(picks.db, league, 2025) == 2026


# ── How the AI values a pick ─────────────────────────────────────────────


def test_an_early_pick_is_worth_more_than_a_late_one():
    early = draft_picks.expected_rating(Pick(2026, 1, "a"), 1, 30)
    late = draft_picks.expected_rating(Pick(2026, 1, "b"), 30, 30)
    second = draft_picks.expected_rating(Pick(2026, 2, "a"), 1, 30)
    assert early > late > second  # the 2nd round snakes back: "a" picks last


def test_a_pick_counts_for_the_future_only():
    asset = draft_picks.asset(Pick(2026, 1, "a"), 1, 30, "A")
    assert asset.future_only and asset.age == draft_picks.PICK_AGE
