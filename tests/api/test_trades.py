# tests/api/test_trades.py
"""Offering trades to AI teams: the rules, the AI's answer, and what a trade
moves (src/api/services/trades.py)."""

from types import SimpleNamespace

import pytest

from src.api.services import trades
from src.api.services.trades import TradeError
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.trade_repo import TradeRepository


def _schedule(db, factory, season, a, b, start=4, completed=False):
    """One 3-game series between a and b in April: the deadline is its last
    day."""
    for day in range(start, start + 3):
        db.execute(
            """INSERT INTO games (id, game_date, season_id, home_team_id,
                                  away_team_id, completed)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (factory._id(), f"2025-04-0{day}", season.id, a.id, b.id, int(completed)),
        )


@pytest.fixture
def lg(db_conn, factory):
    league = factory.league(state="season", mode="blitz")
    season = factory.season(year=2025)
    factory.league_season(league, season)
    mine = factory.team(city="My", mascot="Team")
    theirs = factory.team(city="AI", mascot="Club")
    for t in (mine, theirs):
        factory.league_season_team(league, season, t)
    gm = factory.gm(team=mine, league=league, is_ai=False)
    factory.gm(team=theirs, league=league, is_ai=True)
    _schedule(db_conn, factory, season, mine, theirs)

    # Both teams: 13 hitters at 58 and 13 pitchers at 58 on the 40-man.
    for t in (mine, theirs):
        for _ in range(13):
            factory.rated_player(t, league, 58)
            factory.rated_player(t, league, 58, pitcher=True)
    return SimpleNamespace(
        db=db_conn,
        league=league,
        season=season,
        mine=mine,
        theirs=theirs,
        gm={"id": gm.id, "team_id": mine.id},
        factory=factory,
    )


def _offer(lg, give, get, to=None):
    return trades.propose(
        lg.db,
        lg.league.id,
        lg.gm,
        (to or lg.theirs).id,
        [p.id for p in give],
        [p.id for p in get],
    )


def _team_of(db, player):
    row = db.execute(
        "SELECT team_id FROM team_players WHERE player_id = %s", (player.id,)
    ).fetchone()
    return row["team_id"] if row else None


def test_a_good_offer_is_accepted_and_moves_the_players(lg):
    star = lg.factory.rated_player(lg.mine, lg.league, 72, name="Star")
    spare = lg.factory.rated_player(lg.theirs, lg.league, 52, status="minors")

    result = _offer(lg, [star], [spare])

    assert result["accepted"]
    assert result["arrived"] == ["Test Player"]
    assert _team_of(lg.db, star) == lg.theirs.id
    assert _team_of(lg.db, spare) == lg.mine.id
    # Players arrive in the organization, never on the 40-man.
    assert PlayerStatusRepository(lg.db).get_status(spare.id) == "minors"
    history = TradeRepository(lg.db).history(lg.league.id)
    assert len(history) == 1
    assert [p["player_id"] for p in history[0]["sent"]] == [star.id]
    assert [p["player_id"] for p in history[0]["received"]] == [spare.id]


def test_the_ai_team_puts_a_good_arrival_on_its_40_man(lg):
    star = lg.factory.rated_player(lg.mine, lg.league, 72)
    spare = lg.factory.rated_player(lg.theirs, lg.league, 52, status="minors")
    _offer(lg, [star], [spare])
    assert PlayerStatusRepository(lg.db).get_status(star.id) in ("26man", "40man")


def test_a_bad_offer_is_turned_down_and_nothing_moves(lg):
    scrub = lg.factory.rated_player(lg.mine, lg.league, 50, status="minors")
    star = lg.factory.rated_player(lg.theirs, lg.league, 72)

    result = _offer(lg, [scrub], [star])

    assert not result["accepted"]
    assert result["reason"]
    assert _team_of(lg.db, star) == lg.theirs.id
    assert _team_of(lg.db, scrub) == lg.mine.id
    offers = TradeRepository(lg.db).offers_from_team(lg.league.id, lg.mine.id)
    assert offers[0]["status"] == "rejected"
    assert offers[0]["reason"] == result["reason"]


def test_three_average_players_dont_buy_a_star(lg):
    mine = [lg.factory.rated_player(lg.mine, lg.league, 60) for _ in range(3)]
    star = lg.factory.rated_player(lg.theirs, lg.league, 74)
    assert not _offer(lg, mine, [star])["accepted"]


def test_each_side_has_to_give_someone(lg):
    star = lg.factory.rated_player(lg.theirs, lg.league, 72)
    with pytest.raises(TradeError, match="at least one"):
        _offer(lg, [], [star])


def test_at_most_five_a_side(lg):
    mine = [lg.factory.rated_player(lg.mine, lg.league, 60) for _ in range(6)]
    theirs = [lg.factory.rated_player(lg.theirs, lg.league, 50)]
    with pytest.raises(TradeError, match="At most 5"):
        _offer(lg, mine, theirs)


def test_a_player_has_to_belong_to_the_side_giving_him_up(lg):
    theirs_a = lg.factory.rated_player(lg.theirs, lg.league, 60)
    theirs_b = lg.factory.rated_player(lg.theirs, lg.league, 60)
    with pytest.raises(TradeError, match="isn't on that team"):
        _offer(lg, [theirs_a], [theirs_b])


def test_no_trades_after_the_deadline(lg):
    # A game played after the deadline (April 6, the end of the only other
    # series) closes the window.
    other = lg.factory.team(city="Other", mascot="Club")
    lg.factory.league_season_team(lg.league, lg.season, other)
    _schedule(lg.db, lg.factory, lg.season, lg.mine, other, start=7, completed=True)
    a = lg.factory.rated_player(lg.mine, lg.league, 60)
    b = lg.factory.rated_player(lg.theirs, lg.league, 50)
    with pytest.raises(TradeError, match="closed"):
        _offer(lg, [a], [b])


def test_speed_blitz_has_no_trades(lg):
    lg.db.execute(
        "UPDATE leagues SET mode = 'speed_blitz' WHERE id = %s", (lg.league.id,)
    )
    a = lg.factory.rated_player(lg.mine, lg.league, 60)
    b = lg.factory.rated_player(lg.theirs, lg.league, 50)
    with pytest.raises(TradeError, match="doesn't have trades"):
        _offer(lg, [a], [b])


def test_trades_with_other_human_gms_arent_open_yet(lg):
    other = lg.factory.team(city="Other", mascot="Human")
    lg.factory.league_season_team(lg.league, lg.season, other)
    lg.factory.gm(team=other, league=lg.league, is_ai=False)
    a = lg.factory.rated_player(lg.mine, lg.league, 60)
    b = lg.factory.rated_player(other, lg.league, 50)
    with pytest.raises(TradeError, match="coming soon"):
        _offer(lg, [a], [b], to=other)


def test_a_traded_player_cant_go_back_this_season(lg):
    star = lg.factory.rated_player(lg.mine, lg.league, 72)
    spare = lg.factory.rated_player(lg.theirs, lg.league, 52, status="minors")
    assert _offer(lg, [star], [spare])["accepted"]

    other = lg.factory.rated_player(lg.theirs, lg.league, 50, status="minors")
    with pytest.raises(TradeError, match="can't come back"):
        _offer(lg, [lg.factory.rated_player(lg.mine, lg.league, 70)], [star])
    with pytest.raises(TradeError, match="can't go back"):
        _offer(lg, [spare], [other])


def test_an_ai_team_stops_listening_after_three_rejections_a_day(lg):
    star = lg.factory.rated_player(lg.theirs, lg.league, 74)
    for _ in range(trades.MAX_REJECTIONS_A_DAY):
        scrub = lg.factory.rated_player(lg.mine, lg.league, 50, status="minors")
        assert not _offer(lg, [scrub], [star])["accepted"]
    scrub = lg.factory.rated_player(lg.mine, lg.league, 50, status="minors")
    with pytest.raises(TradeError, match="aren't taking any more calls"):
        _offer(lg, [scrub], [star])


def test_the_same_offer_gets_the_same_answer_all_day(lg):
    a = lg.factory.rated_player(lg.mine, lg.league, 63)
    b = lg.factory.rated_player(lg.theirs, lg.league, 63)
    first = _offer(lg, [a], [b])
    if first["accepted"]:
        pytest.skip("accepted the first time, nothing to repeat")
    assert _offer(lg, [a], [b])["accepted"] is False


def test_a_traded_player_leaves_the_old_teams_rotation_and_lineup(lg):
    pitcher = lg.factory.rated_player(lg.mine, lg.league, 70, pitcher=True)
    spare = lg.factory.rated_player(lg.theirs, lg.league, 52, status="minors")
    lg.db.execute(
        """INSERT INTO team_rotations (team_id, season_id, player_id,
                                       rotation_order, effective_date)
           VALUES (%s, %s, %s, 1, '2025-03-30')""",
        (lg.mine.id, lg.season.id, pitcher.id),
    )
    lg.db.execute(
        """INSERT INTO gm_lineup_preferences (gm_id, player_id, batting_order)
           VALUES (%s, %s, 9)""",
        (lg.gm["id"], pitcher.id),
    )

    assert _offer(lg, [pitcher], [spare])["accepted"]

    rotation = lg.db.execute(
        "SELECT end_date FROM team_rotations WHERE team_id = %s AND player_id = %s",
        (lg.mine.id, pitcher.id),
    ).fetchone()
    # Out from the next game on (the first unplayed date).
    assert rotation["end_date"] == "2025-04-04"
    assert not lg.db.execute(
        "SELECT 1 FROM gm_lineup_preferences WHERE player_id = %s", (pitcher.id,)
    ).fetchone()


def test_the_answer_says_how_many_are_left_on_the_40_man(lg):
    star = lg.factory.rated_player(lg.mine, lg.league, 72)
    spare = lg.factory.rated_player(lg.theirs, lg.league, 52, status="minors")
    result = _offer(lg, [star], [spare])
    # 26 on the 40-man to start, the star leaves, the spare joins the minors.
    assert result["playing_count"] == 26
