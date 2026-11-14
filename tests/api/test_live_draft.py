# tests/api/test_live_draft.py
"""
Long Form's live draft (src/api/services/live_draft.py): AI teams pick the
moment they're up, people pick for themselves, the clock (multiplayer only)
makes the default pick when it runs out, and the short list shows the next
pick's likely options with the default first.
"""

import uuid

import pytest

from src.api.services import live_draft, ready_check
from src.api.services.live_draft import LiveDraft
from src.league.offseason.snake_draft import ROUNDS


def _person(db_conn, factory, team, league):
    gm = factory.gm(team=team, league=league, is_ai=False)
    uid = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO users (id, session_token, display_name, username) VALUES (%s, %s, 'P', %s)",
        (uid, uid, uid),
    )
    db_conn.execute("UPDATE gms SET user_id = %s WHERE id = %s", (uid, gm.id))
    return gm


@pytest.fixture
def setup(db_conn, factory):
    league = factory.league(state="draft", mode="longform")
    season = factory.season()
    factory.league_season(league, season)
    draft = factory.draft(league=league, season=season, fmt="interactive")
    ai1, me, ai2 = factory.team(), factory.team(), factory.team()
    factory.gm(team=ai1, league=league, is_ai=True)
    factory.gm(team=ai2, league=league, is_ai=True)
    gm = _person(db_conn, factory, me, league)
    factory.draft_order(draft, [ai1, me, ai2])
    for i in range(ROUNDS * 3 + 5):
        factory.prospect(league_id=league.id, stamina=30 + i % 40, strikes=30 + i % 37)
    return league, draft, ai1, me, ai2, gm


def _picks(db_conn, draft):
    return db_conn.execute(
        "SELECT pick_number, team_id, auto_picked FROM draft_picks"
        " WHERE draft_id = %s ORDER BY pick_number",
        (draft.id,),
    ).fetchall()


def test_start_makes_the_ai_picks_up_to_the_persons(db_conn, setup):
    _, draft, ai1, me, _, _ = setup
    live = LiveDraft(db_conn, draft.id, lock=True)
    live.start()
    picks = _picks(db_conn, draft)
    assert [p["team_id"] for p in picks] == [ai1.id]
    assert live.current().team_id == me.id
    # One person: no clock.
    assert live.draft["pick_deadline"] is None


def test_a_person_picks_only_on_their_turn(db_conn, setup):
    _, draft, _, me, ai2, _ = setup
    live = LiveDraft(db_conn, draft.id, lock=True)
    live.start()
    pid = live.default_pick(me.id)
    with pytest.raises(ValueError, match="isn't your pick"):
        live.pick(ai2.id, pid)
    live.pick(me.id, pid)
    picks = _picks(db_conn, draft)
    # Snake: pick 2 is mine, then ai2 at 3 and 4, then me again at 5.
    assert [p["team_id"] for p in picks[1:]] == [me.id, ai2.id, ai2.id]
    assert picks[1]["auto_picked"] is False
    assert live.current().pick == 5 and live.current().team_id == me.id
    status = db_conn.execute(
        "SELECT status FROM player_status WHERE player_id = %s", (pid,)
    ).fetchone()
    assert status["status"] == "minors"
    with pytest.raises(ValueError, match="already been picked"):
        live.pick(me.id, pid)


def test_short_list_puts_the_default_first(db_conn, setup):
    _, draft, _, me, _, _ = setup
    live = LiveDraft(db_conn, draft.id, lock=True)
    ahead = live.short_list(me.id)  # before the draft: ai1 picks first
    assert ahead["pick"] == 2 and ahead["away"] == 1
    live.start()
    now = live.short_list(me.id)
    assert now["pick"] == 2 and now["away"] == 0
    assert now["players"][0] == now["default"] == live.default_pick(me.id)
    assert len(now["players"]) == live_draft.SHORT_LIST
    live.pick(me.id, now["default"])
    later = live.short_list(me.id)
    assert later["pick"] == 5 and later["away"] == 0  # the AI picks came straight away
    assert later["default"] not in {p["player_id"] for p in live.picks()}


def test_multiplayer_clock_runs_out_into_the_default_pick(db_conn, factory, setup):
    league, draft, _, me, ai2, _ = setup
    _person(db_conn, factory, factory.team(), league)  # a second person
    db_conn.execute(
        "UPDATE leagues SET pick_timer_sec = 45 WHERE id = %s", (league.id,)
    )
    live = LiveDraft(db_conn, draft.id, lock=True)
    live.start()
    assert live.draft["pick_deadline"] is not None
    assert live.state(me.id)["seconds_left"] in (44, 45)
    assert live.expire() is False  # time left
    db_conn.execute(
        "UPDATE drafts SET pick_deadline = NOW() - INTERVAL '1 second' WHERE id = %s",
        (draft.id,),
    )
    assert live_draft.expire_due(db_conn) >= 1
    mine = [p for p in _picks(db_conn, draft) if p["team_id"] == me.id]
    assert mine and mine[0]["auto_picked"] is True


def test_away_person_gets_the_default_straight_away(db_conn, factory, setup):
    league, draft, _, me, _, gm = setup
    _person(db_conn, factory, factory.team(), league)  # multiplayer
    db_conn.execute("UPDATE gms SET is_away = TRUE WHERE id = %s", (gm.id,))
    live = LiveDraft(db_conn, draft.id, lock=True)
    live.start()
    assert any(p["team_id"] == me.id for p in _picks(db_conn, draft))


def test_auto_draft_the_rest_then_finish(db_conn, setup):
    league, draft, _, me, _, _ = setup
    live = LiveDraft(db_conn, draft.id, lock=True)
    live.start()
    live.scouts_pick(me.id, rest=True)
    assert live.done
    picks = _picks(db_conn, draft)
    assert len(picks) == ROUNDS * 3
    assert sum(p["team_id"] == me.id for p in picks) == ROUNDS
    # The last pick queued the job that finishes it (the tests run jobs
    # straight away); finishing twice does nothing.
    job = db_conn.execute(
        "SELECT kind FROM sim_jobs WHERE league_id = %s", (league.id,)
    ).fetchone()
    assert job["kind"] == "draft"
    live_draft.finish(db_conn, draft.id)
    row = db_conn.execute(
        "SELECT d.state, l.state AS league_state FROM drafts d"
        " JOIN leagues l ON l.id = d.league_id WHERE d.id = %s",
        (draft.id,),
    ).fetchone()
    assert row["state"] == "complete" and row["league_state"] == "preseason"


def test_take_over_stops_the_scouts(db_conn, factory, setup):
    league, draft, _, me, _, _ = setup
    live = LiveDraft(db_conn, draft.id, lock=True)
    live.start()
    live.scouts_pick(me.id)  # just this pick
    assert live.current().team_id == me.id and live.current().pick == 5
    live.scouts_pick(me.id, rest=True)
    live2 = LiveDraft(db_conn, draft.id, lock=True)
    assert live2.done
    # Nothing left to take back, but it doesn't fail.
    live2.take_over(me.id)


def test_ready_check_leaves_an_open_live_draft_alone(db_conn, factory, setup):
    league, draft, *_ = setup
    _person(db_conn, factory, factory.team(), league)
    LiveDraft(db_conn, draft.id, lock=True).start()
    assert live_draft.is_open(db_conn, league.id)
    assert ready_check.advance_if_due(db_conn, league.id) is False
    gm_id = db_conn.execute(
        "SELECT id FROM gms WHERE league_id = %s AND NOT is_ai LIMIT 1", (league.id,)
    ).fetchone()["id"]
    assert ready_check.status(db_conn, league.id, gm_id)["live_draft"] is True
