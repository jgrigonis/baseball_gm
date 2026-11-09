# tests/api/test_trades.py
"""Offering trades to AI teams: the rules, the AI's answer, and what a trade
moves (src/api/services/trades.py)."""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.api.services import trades
from src.api.services import ready_check
from src.api.services.injury_news import take_injury_news
from src.api.services.trades import TradeError
from src.api.services.news.names import plain
from src.db.repositories.news_repo import NewsRepository
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


def test_a_trade_makes_the_league_news(lg):
    star = lg.factory.rated_player(lg.mine, lg.league, 72, name="Star")
    spare = lg.factory.rated_player(lg.theirs, lg.league, 52, status="minors")

    _offer(lg, [star], [spare])

    (story,) = NewsRepository(lg.db).feed(lg.league.id)
    story["headline"] = plain(story["headline"])
    assert story["kind"] == "trade"
    # The fixture's schedule puts the deadline days away.
    assert (
        story["headline"]
        == "Deadline deal: GM GM's Team land Test Player from the Club"
    )
    assert set(story["team_ids"]) == {lg.mine.id, lg.theirs.id}


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
    offers = TradeRepository(lg.db).offers_for_team(lg.league.id, lg.mine.id)
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


def test_a_league_with_trades_off_has_no_trades(lg):
    lg.db.execute(
        "UPDATE leagues SET trades_enabled = false WHERE id = %s", (lg.league.id,)
    )
    a = lg.factory.rated_player(lg.mine, lg.league, 60)
    b = lg.factory.rated_player(lg.theirs, lg.league, 50)
    with pytest.raises(TradeError, match="doesn't have trades"):
        _offer(lg, [a], [b])


def test_a_traded_player_cant_go_back_this_season(lg):
    star = lg.factory.rated_player(lg.mine, lg.league, 72)
    spare = lg.factory.rated_player(lg.theirs, lg.league, 52, status="minors")
    assert _offer(lg, [star], [spare])["accepted"]

    other = lg.factory.rated_player(lg.theirs, lg.league, 50, status="minors")
    with pytest.raises(TradeError, match="can.t go back to the My Team"):
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


# ── Trades between GMs ───────────────────────────────────────────────────


def _human(lg, team, name):
    """A person running `team`: a GM row with a user."""
    gm = lg.factory.gm(team=team, league=lg.league, is_ai=False)
    user_id = str(uuid.uuid4())
    lg.db.execute(
        "INSERT INTO users (id, session_token, display_name) VALUES (%s, %s, %s)",
        (user_id, user_id, name),
    )
    lg.db.execute(
        "UPDATE gms SET user_id = %s, display_name = %s WHERE id = %s",
        (user_id, name, gm.id),
    )
    return {"id": gm.id, "team_id": team.id}


@pytest.fixture
def gms(lg):
    """lg with people running both teams, plus `voters` more GMs running
    teams of their own: call gms(n)."""
    lg.db.execute(
        "DELETE FROM gms WHERE team_id = ANY(%s)", ([lg.mine.id, lg.theirs.id],)
    )
    lg.gm = _human(lg, lg.mine, "Me")
    lg.other = _human(lg, lg.theirs, "Them")

    def make(voters=0, vote=True):
        lg.db.execute(
            "UPDATE leagues SET trade_vote = %s WHERE id = %s", (vote, lg.league.id)
        )
        lg.voters = []
        for i in range(voters):
            team = lg.factory.team(city=f"Voter{i}", mascot="Club")
            lg.factory.league_season_team(lg.league, lg.season, team)
            lg.voters.append(_human(lg, team, f"Voter {i}"))
        return lg

    return make


def _answer(lg, offer_id, action, gm=None):
    return trades.respond(lg.db, lg.league.id, gm or lg.other, offer_id, action)


def _news(lg, gm):
    return take_injury_news(lg.db, gm["id"])["trades"]


def _two_players(lg):
    return (
        lg.factory.rated_player(lg.mine, lg.league, 60, name="Mine"),
        lg.factory.rated_player(lg.theirs, lg.league, 60, name="Theirs"),
    )


def test_an_offer_to_a_gm_waits_for_them_and_pops_up(gms):
    lg = gms()
    a, b = _two_players(lg)
    result = _offer(lg, [a], [b])
    assert result["pending"]
    assert _team_of(lg.db, a) == lg.mine.id  # nothing moves yet
    news = _news(lg, lg.other)
    assert [n["event"] for n in news] == ["offer"]
    assert news[0]["popup"] and news[0]["offer_id"] == result["offer_id"]
    assert trades.inbox_count(lg.db, lg.league.id, lg.other) == 1


def test_accepting_moves_the_players_and_tells_the_proposer(gms):
    lg = gms()
    a, b = _two_players(lg)
    offer_id = _offer(lg, [a], [b])["offer_id"]
    result = _answer(lg, offer_id, "accept")
    assert result["status"] == "accepted"
    assert _team_of(lg.db, a) == lg.theirs.id
    assert _team_of(lg.db, b) == lg.mine.id
    assert PlayerStatusRepository(lg.db).get_status(a.id) == "minors"
    assert [n["event"] for n in _news(lg, lg.gm)] == ["accepted"]


def test_rejecting_tells_the_proposer(gms):
    lg = gms()
    a, b = _two_players(lg)
    offer_id = _offer(lg, [a], [b])["offer_id"]
    assert _answer(lg, offer_id, "reject")["status"] == "rejected"
    assert _team_of(lg.db, a) == lg.mine.id
    assert [n["event"] for n in _news(lg, lg.gm)] == ["rejected"]


def test_only_the_proposer_can_withdraw_and_only_the_other_side_can_accept(gms):
    lg = gms()
    a, b = _two_players(lg)
    offer_id = _offer(lg, [a], [b])["offer_id"]
    with pytest.raises(TradeError, match="wasn't made to you"):
        _answer(lg, offer_id, "accept", gm=lg.gm)
    with pytest.raises(TradeError, match="Only the team that made"):
        _answer(lg, offer_id, "withdraw", gm=lg.other)
    assert _answer(lg, offer_id, "withdraw", gm=lg.gm)["status"] == "withdrawn"
    with pytest.raises(TradeError, match="already been answered"):
        _answer(lg, offer_id, "accept")


def test_a_counter_replaces_the_offer(gms):
    lg = gms()
    a, b = _two_players(lg)
    extra = lg.factory.rated_player(lg.mine, lg.league, 55)
    offer_id = _offer(lg, [a], [b])["offer_id"]
    counter = trades.propose(
        lg.db,
        lg.league.id,
        lg.other,
        lg.mine.id,
        [b.id],
        [a.id, extra.id],
        counter_of=offer_id,
    )
    assert counter["pending"]
    repo = TradeRepository(lg.db)
    assert repo.get(offer_id)["status"] == "countered"
    assert repo.get(counter["offer_id"])["parent_id"] == offer_id
    assert [n["event"] for n in _news(lg, lg.gm)] == ["counter"]
    # One counter per offer: the first one replaced it.
    with pytest.raises(TradeError, match="already countered"):
        trades.propose(
            lg.db,
            lg.league.id,
            lg.other,
            lg.mine.id,
            [b.id],
            [a.id],
            counter_of=offer_id,
        )
    # Now it's mine to answer.
    result = trades.respond(lg.db, lg.league.id, lg.gm, counter["offer_id"], "accept")
    assert result["status"] == "accepted"
    assert _team_of(lg.db, extra) == lg.theirs.id


def test_only_the_gm_it_was_made_to_can_counter(gms):
    lg = gms()
    a, b = _two_players(lg)
    offer_id = _offer(lg, [a], [b])["offer_id"]
    with pytest.raises(TradeError, match="can't be countered"):
        trades.propose(
            lg.db,
            lg.league.id,
            lg.gm,
            lg.theirs.id,
            [a.id],
            [b.id],
            counter_of=offer_id,
        )


def test_one_open_offer_to_a_team_at_a_time(gms):
    lg = gms()
    a, b = _two_players(lg)
    _offer(lg, [a], [b])
    c = lg.factory.rated_player(lg.mine, lg.league, 58)
    with pytest.raises(TradeError, match="already have an offer out"):
        _offer(lg, [c], [b])


def test_an_accept_checks_the_rules_again(gms):
    lg = gms()
    a, b = _two_players(lg)
    offer_id = _offer(lg, [a], [b])["offer_id"]
    # b leaves the other team some other way before the answer.
    lg.db.execute("DELETE FROM team_players WHERE player_id = %s", (b.id,))
    with pytest.raises(TradeError, match="can't go through"):
        _answer(lg, offer_id, "accept")
    assert TradeRepository(lg.db).get(offer_id)["status"] == "void"


def test_a_trade_calls_off_other_offers_for_the_same_player(gms):
    lg = gms(voters=1, vote=False)
    a, b = _two_players(lg)
    first = _offer(lg, [a], [b])["offer_id"]
    # A third GM wants b too.
    voter = lg.voters[0]
    c = lg.factory.rated_player(SimpleNamespace(id=voter["team_id"]), lg.league, 60)
    second = trades.propose(lg.db, lg.league.id, voter, lg.theirs.id, [c.id], [b.id])[
        "offer_id"
    ]
    _answer(lg, first, "accept")
    assert TradeRepository(lg.db).get(second)["status"] == "void"
    assert any(n["event"] == "void" for n in _news(lg, voter))


def test_offers_expire_before_the_period_after_next_runs(gms):
    lg = gms()
    a, b = _two_players(lg)
    offer_id = _offer(lg, [a], [b])["offer_id"]
    period = lg.db.execute(
        "SELECT sim_period FROM leagues WHERE id = %s", (lg.league.id,)
    ).fetchone()["sim_period"]
    repo = TradeRepository(lg.db)
    trades.close_due(lg.db, lg.league.id, period)  # this period runs
    assert repo.get(offer_id)["status"] == "pending"
    trades.close_due(lg.db, lg.league.id, period + 1)  # the next one
    assert repo.get(offer_id)["status"] == "expired"
    assert [n["event"] for n in _news(lg, lg.gm)] == ["expired"]


def test_the_ready_check_expires_offers_before_running_a_period(gms, db_conn):
    lg = gms()
    a, b = _two_players(lg)
    offer_id = _offer(lg, [a], [b])["offer_id"]
    lg.db.execute(
        "UPDATE leagues SET sim_period = sim_period + 1 WHERE id = %s", (lg.league.id,)
    )
    for g in (lg.gm, lg.other):
        lg.db.execute(
            "UPDATE gms SET ready_period = (SELECT sim_period FROM leagues"
            " WHERE id = %s) WHERE id = %s",
            (lg.league.id, g["id"]),
        )
    with patch.object(ready_check, "_run_period", return_value=False):
        assert ready_check.advance_if_due(lg.db, lg.league.id)
    assert TradeRepository(lg.db).get(offer_id)["status"] == "expired"


def test_everything_open_expires_at_the_deadline(gms):
    lg = gms(voters=1)
    a, b = _two_players(lg)
    offer_id = _offer(lg, [a], [b])["offer_id"]
    # Deadline day's games are played (the deadline is April 6).
    lg.db.execute(
        "UPDATE games SET completed = 1 WHERE season_id = %s", (lg.season.id,)
    )
    trades.close_at_deadline(lg.db, lg.league.id)
    assert TradeRepository(lg.db).get(offer_id)["status"] == "expired"


def test_nothing_expires_before_deadline_day(gms):
    lg = gms()
    a, b = _two_players(lg)
    offer_id = _offer(lg, [a], [b])["offer_id"]
    trades.close_at_deadline(lg.db, lg.league.id)
    assert TradeRepository(lg.db).get(offer_id)["status"] == "pending"


# ── The league vote ──────────────────────────────────────────────────────


def _agreed(lg):
    a, b = _two_players(lg)
    offer_id = _offer(lg, [a], [b])["offer_id"]
    return offer_id, _answer(lg, offer_id, "accept"), a


def _vote(lg, voter, offer_id, yes):
    return trades.vote(lg.db, lg.league.id, voter, offer_id, yes)


def test_with_two_gms_theres_no_vote(gms):
    lg = gms(voters=0)
    _, result, a = _agreed(lg)
    assert result["status"] == "accepted"
    assert _team_of(lg.db, a) == lg.theirs.id


def test_with_the_vote_off_trades_go_straight_through(gms):
    lg = gms(voters=2, vote=False)
    _, result, _ = _agreed(lg)
    assert result["status"] == "accepted"


def test_an_agreed_trade_waits_for_the_vote(gms):
    lg = gms(voters=1)
    offer_id, result, a = _agreed(lg)
    assert result == {"status": "pending_vote", "voters": 1}
    assert _team_of(lg.db, a) == lg.mine.id
    news = _news(lg, lg.voters[0])
    assert [n["event"] for n in news] == ["vote"] and news[0]["popup"]
    assert trades.inbox_count(lg.db, lg.league.id, lg.voters[0]) == 1


def test_one_voter_saying_yes_passes_it(gms):
    lg = gms(voters=1)
    offer_id, _, a = _agreed(lg)
    assert _vote(lg, lg.voters[0], offer_id, True)["status"] == "accepted"
    assert _team_of(lg.db, a) == lg.theirs.id
    events = [n["event"] for n in _news(lg, lg.other)]
    assert events[-1] == "accepted"  # the GM who accepted hears it went through


def test_a_split_vote_fails(gms):
    # Four GMs: two in the trade, two voting. 1-1 isn't more than half.
    lg = gms(voters=2)
    offer_id, _, a = _agreed(lg)
    assert _vote(lg, lg.voters[0], offer_id, True)["status"] == "pending_vote"
    assert _vote(lg, lg.voters[1], offer_id, False)["status"] == "voted_down"
    assert _team_of(lg.db, a) == lg.mine.id


def test_the_vote_ends_once_it_cant_pass(gms):
    lg = gms(voters=3)  # needs 2 of 3
    offer_id, _, _ = _agreed(lg)
    assert _vote(lg, lg.voters[0], offer_id, False)["status"] == "pending_vote"
    assert _vote(lg, lg.voters[1], offer_id, False)["status"] == "voted_down"


def test_a_missing_vote_counts_as_no(gms):
    lg = gms(voters=2)
    offer_id, _, a = _agreed(lg)
    _vote(lg, lg.voters[0], offer_id, True)
    period = TradeRepository(lg.db).get(offer_id)["vote_period"]
    trades.close_due(lg.db, lg.league.id, period)
    assert TradeRepository(lg.db).get(offer_id)["status"] == "voted_down"
    assert _team_of(lg.db, a) == lg.mine.id


def test_the_vote_stays_open_until_its_period(gms):
    lg = gms(voters=2)
    offer_id, _, _ = _agreed(lg)
    period = TradeRepository(lg.db).get(offer_id)["vote_period"]
    trades.close_due(lg.db, lg.league.id, period - 1)
    assert TradeRepository(lg.db).get(offer_id)["status"] == "pending_vote"


def test_away_gms_dont_vote(gms):
    lg = gms(voters=2)
    lg.db.execute("UPDATE gms SET is_away = TRUE WHERE id = %s", (lg.voters[1]["id"],))
    offer_id, result, _ = _agreed(lg)
    assert result["voters"] == 1
    with pytest.raises(TradeError, match="don't have a vote"):
        _vote(lg, lg.voters[1], offer_id, True)


def test_the_gms_in_the_trade_cant_vote(gms):
    lg = gms(voters=1)
    offer_id, _, _ = _agreed(lg)
    with pytest.raises(TradeError, match="don't have a vote"):
        _vote(lg, lg.gm, offer_id, True)


def test_a_gm_leaving_calls_off_their_offers(gms):
    from src.api.services.leave_league import leave_league

    lg = gms()
    a, b = _two_players(lg)
    offer_id = _offer(lg, [a], [b])["offer_id"]
    leave_league(lg.db, lg.league.id, lg.other["id"])
    assert TradeRepository(lg.db).get(offer_id)["status"] == "void"
    assert [n["event"] for n in _news(lg, lg.gm)] == ["void"]


def test_a_voter_leaving_can_settle_the_vote(gms):
    from src.api.services.leave_league import leave_league

    lg = gms(voters=2)
    offer_id, _, a = _agreed(lg)
    _vote(lg, lg.voters[0], offer_id, True)
    # 1 of 2 isn't enough; once the other voter leaves, 1 of 1 is.
    leave_league(lg.db, lg.league.id, lg.voters[1]["id"])
    assert TradeRepository(lg.db).get(offer_id)["status"] == "accepted"
    assert _team_of(lg.db, a) == lg.theirs.id


def test_a_vote_that_ends_early_tells_the_voter_who_hadnt_voted(gms):
    # Three voters: two yes votes settle it.
    lg = gms(voters=3)
    offer_id, _, _ = _agreed(lg)
    _vote(lg, lg.voters[0], offer_id, True)
    assert _vote(lg, lg.voters[1], offer_id, True)["status"] == "accepted"
    # The third voter's vote popup, unseen, is gone; the news says it's over.
    news = _news(lg, lg.voters[2])
    assert [n["event"] for n in news] == ["vote_over"]
    assert "passed" in news[0]["text"]
    assert trades.inbox_count(lg.db, lg.league.id, lg.voters[2]) == 0
    # The voters who voted hear nothing more (and their own popups, never
    # opened here, are dropped too).
    assert _news(lg, lg.voters[1]) == []


def test_a_withdrawn_offer_doesnt_pop_up_later(gms):
    lg = gms()
    a, b = _two_players(lg)
    offer_id = _offer(lg, [a], [b])["offer_id"]
    _answer(lg, offer_id, "withdraw", gm=lg.gm)
    assert [n["event"] for n in _news(lg, lg.other)] == ["withdrawn"]


def test_a_counter_drops_the_popup_for_the_offer_it_replaces(gms):
    lg = gms()
    a, b = _two_players(lg)
    offer_id = _offer(lg, [a], [b])["offer_id"]
    # The proposer's own unseen popup can't exist, so check the other way:
    # Them counter before they've seen the popup for the first offer.
    trades.propose(
        lg.db, lg.league.id, lg.other, lg.mine.id, [b.id], [a.id], counter_of=offer_id
    )
    assert _news(lg, lg.other) == []


# ── Contracts in the AI's price ───────────────────────────────────────────────


def _signed(lg, team, level, salary, years=3):  # noqa: F811
    from src.db.repositories.budget_repo import BudgetRepository
    from src.db.repositories.contract_repo import ContractRepository
    from src.player import contracts as ct

    p = lg.factory.rated_player(team, lg.league, level)
    contracts = ContractRepository(lg.db)
    contracts.sign_unsigned(lg.league.id, 2025)
    lg.db.execute("DELETE FROM player_contracts WHERE player_id = %s", (p.id,))
    contracts.insert_deal(
        p.id, lg.league.id, team.id, ct.Deal(salary, years, "standard"), 2025, True
    )
    BudgetRepository(lg.db).for_league(lg.league.id, 2025)
    return p


def _ai_says(lg, give, get):  # noqa: F811
    return trades.ai_answer(
        lg.db, lg.league.id, lg.season.id, lg.theirs.id, lg.mine.id,
        [p.id for p in give], [p.id for p in get], "2025-06-01",
    )  # fmt: skip


def test_the_ai_turns_down_a_player_for_his_contract(lg):  # noqa: F811
    from src.player import contracts as ct

    theirs = lg.factory.rated_player(lg.theirs, lg.league, 58)
    fair = _signed(lg, lg.mine, 61, ct.prime_salary(61, "hitter"))
    over = _signed(lg, lg.mine, 61, 14_000_000, years=5)
    # Just room enough for his salary, so only the money differs.
    from src.api.services import owners

    room = owners.pay_rooms(lg.db, lg.league.id, lg.season.id)[lg.theirs.id]
    lg.db.execute(
        "UPDATE team_budgets SET budget = budget + %s WHERE team_id = %s",
        (max(0, 12_000_000 - room), lg.theirs.id),
    )
    yes = _ai_says(lg, [theirs], [fair])
    no = _ai_says(lg, [theirs], [over])
    assert yes.details["d_money"] > no.details["d_money"]
    assert no.score < yes.score
    assert yes.accept and not no.accept
    assert "contract" in no.reason
