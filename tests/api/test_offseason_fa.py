# tests/api/test_offseason_fa.py
"""Offseason free agency: the re-sign window, bids from the draft into the
preseason, and players picking a bid (src/api/services/offseason_fa.py)."""

from types import SimpleNamespace

import pytest

from src.api.services import ai_free_agents, free_agents, offseason_fa
from src.api.services.free_agents import FreeAgentError
from src.api.services.news.names import plain
from src.api.services.offseason_fa import OffseasonFAError
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.player import contracts as ct
from src.player import happiness as hp

# The real refusal rule, for its own test: every other test turns refusals
# off, since the draw is seeded by each player's random id.
REFUSES_TO_RESIGN = hp.refuses_to_resign


@pytest.fixture
def lg(db_conn, factory):
    league = factory.league(state="offseason", mode="blitz")
    season = factory.season(year=2026)
    factory.league_season(league, season)
    mine = factory.team(city="My", mascot="Team")
    ai = factory.team(city="Ai", mascot="Club")
    other = factory.team(city="Other", mascot="Club")
    for t in (mine, ai, other):
        factory.league_season_team(league, season, t)
    factory.gm(team=mine, league=league, is_ai=False)
    factory.gm(team=ai, league=league, is_ai=True)
    factory.gm(team=other, league=league, is_ai=True)
    BudgetRepository(db_conn).for_league(league.id, 2026)
    return SimpleNamespace(
        db=db_conn,
        factory=factory,
        league=league,
        season=season,
        mine=mine,
        ai=ai,
        other=other,
        contracts=ContractRepository(db_conn),
        status=PlayerStatusRepository(db_conn),
    )


@pytest.fixture(autouse=True)
def roomy_owners(monkeypatch):
    monkeypatch.setattr(BudgetRepository, "refusal", lambda *a, **k: None)
    monkeypatch.setattr(ai_free_agents, "_budget_room", lambda *a: float("inf"))
    monkeypatch.setattr(offseason_fa, "_room", _roomy)
    monkeypatch.setattr(offseason_fa, "_bank", lambda *a: 0)
    monkeypatch.setattr(hp, "refuses_to_resign", lambda *a: None)


def _roomy(conn, league_id, team_id, year, human):
    return ai_free_agents._budget_room(conn, league_id, team_id, year)


def _expiring(lg, team, start, years, level=60, status="40man"):
    """A player whose deal (start..start+years-1) ends with 2026."""
    pid = lg.factory.rated_player(team, lg.league, level=level, status=status).id
    lg.contracts.insert_deal(
        pid, lg.league.id, team.id, ct.Deal(5_000_000, years, "standard"), start
    )
    return pid


def _on(lg, team):
    return PlayerRepository(lg.db).get_player_ids_from_team_players(team.id)


def _set_state(lg, state):
    lg.db.execute(
        "UPDATE leagues SET state = %s, fa_bidding = (%s = 'draft') WHERE id = %s",
        (state, state, lg.league.id),
    )


# ── The re-sign window ────────────────────────────────────────────────────────


def test_veterans_go_to_market_and_others_dont(lg):
    vet = _expiring(lg, lg.mine, 2021, 6)  # 6 seasons
    young = _expiring(lg, lg.mine, 2024, 3)  # 3 seasons
    rows = {r["player_id"]: r for r in offseason_fa.expiring(lg.db, lg.league.id, 2026)}
    assert rows[vet]["market"] == "veteran"
    assert rows[young]["market"] is None
    # His new deal is priced from next season.
    assert rows[vet]["deal"].salary > 0


def test_a_deal_that_runs_on_isnt_expiring(lg):
    _expiring(lg, lg.mine, 2026, 3)
    assert offseason_fa.expiring(lg.db, lg.league.id, 2026) == []


def test_closing_the_window_follows_the_gms_calls(lg):
    vet = _expiring(lg, lg.mine, 2020, 7)
    kept_vet = _expiring(lg, lg.mine, 2020, 7)
    young = _expiring(lg, lg.mine, 2024, 3)
    cut = _expiring(lg, lg.mine, 2024, 3)
    offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, kept_vet, "resign")
    offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, cut, "let_go")

    out = offseason_fa.close_window(lg.db, lg.league.id)

    assert out == {"resigned": 2, "to_market": 2}
    assert lg.status.get_status(vet) == "free_agent" and vet not in _on(lg, lg.mine)
    assert lg.status.get_status(cut) == "free_agent"
    new = lg.contracts.active(kept_vet, 2027)
    assert new["start_year"] == 2027 and new["guaranteed"]
    # Anyone else is tendered by default, now.
    assert lg.contracts.active(young, 2027)["start_year"] == 2027


def _deals(lg):
    return {
        r["player_id"]: r["deal"].salary
        for r in offseason_fa.expiring(lg.db, lg.league.id, 2026)
    }


def _room_this_season(monkeypatch, room):
    monkeypatch.setattr(ai_free_agents, "_budget_room", lambda *a: room)


def test_a_default_tender_the_owner_cant_cover_goes_to_market(lg, monkeypatch):
    young = _expiring(lg, lg.mine, 2024, 3, level=75)
    kept = _expiring(lg, lg.mine, 2024, 3, level=75)
    # Next season: this season's room plus both $5M salaries coming off,
    # enough for one of them at his new price.
    _room_this_season(monkeypatch, _deals(lg)[kept] - 10_000_000)
    offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, kept, "resign")
    offseason_fa.close_window(lg.db, lg.league.id)
    # His own call stands; the default can't get past the owner.
    assert lg.contracts.active(kept, 2027) is not None
    assert lg.status.get_status(young) == "free_agent"


def test_re_signs_are_judged_on_next_season(lg, monkeypatch):
    a = _expiring(lg, lg.mine, 2024, 3, level=75)
    b = _expiring(lg, lg.mine, 2024, 3, level=75)
    deals = _deals(lg)
    # Over the limit this season, but the $10M coming off covers one more.
    _room_this_season(monkeypatch, max(deals.values()) - 10_000_000)
    offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, a, "resign")
    with pytest.raises(OffseasonFAError, match="dipping into their bank"):
        offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, b, "resign")
    money = offseason_fa.next_season_money(lg.db, lg.league.id, lg.mine.id)
    assert money["left"] == max(deals.values()) - deals[a]
    fates = {
        r["player_id"]: r["fate"]
        for r in offseason_fa.expiring_view(lg.db, lg.league.id, lg.mine.id)
    }
    assert fates == {a: "resign", b: "no_room"}
    # Letting the first go makes room for the second.
    offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, a, "let_go")
    offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, b, "resign")


def test_your_own_re_signs_can_dip_into_the_owners_bank(lg, monkeypatch):
    a = _expiring(lg, lg.mine, 2024, 3, level=75)
    b = _expiring(lg, lg.mine, 2024, 3, level=75)
    deals = _deals(lg)
    # No room at all next season; the bank covers the first only.
    _room_this_season(monkeypatch, -10_000_000)
    monkeypatch.setattr(offseason_fa, "_bank", lambda *_: deals[a] + 1)
    offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, a, "resign")
    with pytest.raises(OffseasonFAError, match="bank"):
        offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, b, "resign")
    money = offseason_fa.next_season_money(lg.db, lg.league.id, lg.mine.id)
    assert money["over"] and money["left"] == -deals[a]
    # The default tender still can't: only your own call goes past the limit.
    offseason_fa.close_window(lg.db, lg.league.id)
    assert lg.contracts.active(a, 2027) is not None
    assert lg.status.get_status(b) == "free_agent"


def test_re_sign_all_only_when_the_bank_covers_everyone(lg, monkeypatch):
    a = _expiring(lg, lg.mine, 2024, 3, level=75)
    b = _expiring(lg, lg.mine, 2024, 3, level=75)
    deals = _deals(lg)
    total = deals[a] + deals[b]
    # Next season's room is this season's plus the $10M coming off.
    _room_this_season(monkeypatch, total - 10_000_000 - 3_000_000)
    monkeypatch.setattr(offseason_fa, "_bank", lambda *_: 2_000_000)
    assert offseason_fa.resign_all_plan(lg.db, lg.league.id, lg.mine.id) is None
    with pytest.raises(OffseasonFAError, match="bank"):
        offseason_fa.resign_all(lg.db, lg.league.id, lg.mine.id)
    # A bigger bank covers it, and the plan says how much comes out.
    monkeypatch.setattr(offseason_fa, "_bank", lambda *_: 5_000_000)
    plan = offseason_fa.resign_all_plan(lg.db, lg.league.id, lg.mine.id)
    assert plan["from_bank"] == 3_000_000 and plan["bank"] == 5_000_000
    assert plan["count"] == 2 and plan["cost"] == total
    offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, b, "let_go")
    assert offseason_fa.resign_all(lg.db, lg.league.id, lg.mine.id) == {"count": 2}
    offseason_fa.close_window(lg.db, lg.league.id)
    assert lg.contracts.active(a, 2027) is not None
    assert lg.contracts.active(b, 2027) is not None


def test_re_sign_all_inside_the_limit_needs_no_bank(lg, monkeypatch):
    _expiring(lg, lg.mine, 2024, 3, level=60)
    plan = offseason_fa.resign_all_plan(lg.db, lg.league.id, lg.mine.id)
    assert plan["fits"] and plan["from_bank"] == 0


def test_a_pay_cut_isnt_free_when_over_the_limit(lg, monkeypatch):
    pid = _expiring(lg, lg.mine, 2024, 3, level=40)
    lg.db.execute(
        "UPDATE player_contracts SET salary = 40000000 WHERE player_id = %s", (pid,)
    )
    _room_this_season(monkeypatch, -40_000_000)  # $40M over this season
    with pytest.raises(OffseasonFAError):
        offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, pid, "resign")


def test_ai_teams_tender_the_best_first_while_the_budget_lasts(lg, monkeypatch):
    star = _expiring(lg, lg.ai, 2024, 3, level=85)
    good = _expiring(lg, lg.ai, 2024, 3, level=70)
    rows = {r["player_id"]: r for r in offseason_fa.expiring(lg.db, lg.league.id, 2026)}
    room = rows[star]["deal"].salary - 5_000_000
    monkeypatch.setattr(ai_free_agents, "_budget_room", lambda *a: room)
    offseason_fa.close_window(lg.db, lg.league.id)
    assert lg.contracts.active(star, 2027) is not None
    assert lg.status.get_status(good) == "free_agent"


def test_ai_teams_let_fringe_players_go_rather_than_pay_them(lg):
    # Every level from fringe up: a C- or worse player is kept only at the
    # minimum, anyone better whenever the budget has room.
    ids = [_expiring(lg, lg.ai, 2025, 2, level=lv) for lv in range(20, 61, 4)]
    rows = {r["player_id"]: r for r in offseason_fa.expiring(lg.db, lg.league.id, 2026)}
    offseason_fa.close_window(lg.db, lg.league.id)
    let_go = 0
    for pid in ids:
        r = rows[pid]
        minimum = ct.round_salary(ct.MIN_SALARY * r["scale"], r["scale"])
        priced_out = free_agents.is_fringe(r["player"]) and r["deal"].salary > minimum
        let_go += priced_out
        kept = lg.contracts.active(pid, 2027) is not None
        assert kept != priced_out
    assert let_go  # some fringe players asked for more than the minimum


def test_ai_teams_keep_their_40_man_vets_they_can_afford(lg, monkeypatch):
    kept = _expiring(lg, lg.ai, 2020, 7)
    prospect = _expiring(lg, lg.ai, 2020, 7, status="minors")
    offseason_fa.close_window(lg.db, lg.league.id)
    assert lg.contracts.active(kept, 2027) is not None
    assert lg.status.get_status(prospect) == "free_agent"


def test_ai_teams_let_vets_go_without_budget_room(lg, monkeypatch):
    monkeypatch.setattr(ai_free_agents, "_budget_room", lambda *a: 0)
    pid = _expiring(lg, lg.ai, 2020, 7, level=70)
    offseason_fa.close_window(lg.db, lg.league.id)
    assert lg.status.get_status(pid) == "free_agent"


def _news(lg, prefix):
    return lg.db.execute(
        "SELECT * FROM league_news WHERE league_id = %s AND key LIKE %s ORDER BY key",
        (lg.league.id, prefix + "%"),
    ).fetchall()


def test_good_players_who_leave_get_a_story_each(lg):
    star = _expiring(lg, lg.mine, 2024, 3, level=80)
    offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, star, "let_go")
    vet = _expiring(lg, lg.ai, 2020, 7, level=80, status="minors")
    offseason_fa.close_window(lg.db, lg.league.id)

    stories = {r["player_ids"][0]: r for r in _news(lg, "fa-leave:")}
    assert set(stories) == {star, vet}
    mine = stories[star]
    assert plain(mine["headline"]) == "Test Player leaves the Team for free agency"
    assert plain(mine["body"]).startswith("The Team let him go. ")
    assert mine["team_ids"] == [lg.mine.id] and mine["weight"] == 3
    assert "after 7 seasons" in stories[vet]["body"]


def test_the_rest_from_your_team_share_one_story(lg):
    star = _expiring(lg, lg.mine, 2024, 3, level=80)
    cuts = [_expiring(lg, lg.mine, 2024, 3, level=30) for _ in range(2)]
    ai_cut = _expiring(lg, lg.ai, 2024, 3, level=30)
    for pid in cuts + [star]:
        offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, pid, "let_go")
    offseason_fa.choose(lg.db, lg.league.id, lg.ai.id, ai_cut, "let_go")
    offseason_fa.close_window(lg.db, lg.league.id)

    assert all(
        offseason_fa.GRADES.index(
            offseason_fa.shown_grade(PlayerRepository(lg.db).look_up(pid))
        )
        > offseason_fa.GRADES.index(offseason_fa.DEPARTURE_STORY_GRADE)
        for pid in cuts
    )
    rest = _news(lg, "fa-leave-rest:")
    assert len(rest) == 1  # only a person's team gets a roundup
    assert plain(rest[0]["headline"]) == "2 more players leave the Team for free agency"
    assert set(rest[0]["player_ids"]) == set(cuts)


def test_a_signing_names_the_team_he_left(lg, monkeypatch):
    monkeypatch.setattr(offseason_fa, "_ai_bids", lambda *a: 0)
    pid = _expiring(lg, lg.mine, 2024, 3, level=70)
    offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, pid, "let_go")
    offseason_fa.close_window(lg.db, lg.league.id)
    _set_state(lg, "draft")
    ask = _ask(lg, pid).salary
    offseason_fa.place_bid(lg.db, lg.league.id, lg.ai.id, pid, ask, 2)
    offseason_fa.settle(lg.db, lg.league.id)
    story = _news(lg, "fa-sign:")[0]
    assert plain(story["body"]).endswith("He leaves the Team.")
    assert set(story["team_ids"]) == {lg.ai.id, lg.mine.id}


def test_choices_only_in_the_offseason(lg):
    pid = _expiring(lg, lg.mine, 2024, 3)
    _set_state(lg, "draft")
    with pytest.raises(OffseasonFAError):
        offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, pid, "resign")


def test_you_cant_decide_for_another_teams_player(lg):
    pid = _expiring(lg, lg.ai, 2024, 3)
    with pytest.raises(OffseasonFAError):
        offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, pid, "let_go")


# ── Bidding ───────────────────────────────────────────────────────────────────


def _free_agent(lg, level=60, **kw):
    pid = lg.factory.rated_player(
        lg.mine, lg.league, level=level, status="free_agent", **kw
    ).id
    lg.db.execute("DELETE FROM team_players WHERE player_id = %s", (pid,))
    return pid


def _ask(lg, pid):
    p = PlayerRepository(lg.db).look_up(pid)
    return offseason_fa.asking(lg.db, lg.league.id, p, 2026)


def test_free_agents_take_bids_during_the_draft(lg):
    _set_state(lg, "draft")
    pid = _free_agent(lg)
    with pytest.raises(FreeAgentError, match="bids"):
        free_agents.sign(lg.db, lg.league.id, lg.mine.id, pid)
    offseason_fa.place_bid(lg.db, lg.league.id, lg.mine.id, pid, 3_000_000, 2)
    preview = offseason_fa.bid_preview(lg.db, lg.league.id, lg.mine.id, pid)
    assert preview["bid"] == {"salary": 3_000_000, "years": 2}
    assert preview["bids"] == 1
    offseason_fa.withdraw_bid(lg.db, lg.league.id, lg.mine.id, pid)
    assert offseason_fa.bid_counts(lg.db, lg.league.id, 2026) == {}


def test_bids_need_the_draft_and_sane_terms(lg):
    pid = _free_agent(lg)
    with pytest.raises(OffseasonFAError, match="closed"):
        offseason_fa.place_bid(lg.db, lg.league.id, lg.mine.id, pid, 3_000_000, 2)
    _set_state(lg, "draft")
    with pytest.raises(OffseasonFAError, match="seasons"):
        offseason_fa.place_bid(lg.db, lg.league.id, lg.mine.id, pid, 3_000_000, 9)
    with pytest.raises(OffseasonFAError, match="at least"):
        offseason_fa.place_bid(lg.db, lg.league.id, lg.mine.id, pid, 1000, 2)


def test_he_takes_the_better_money_when_fit_is_even(lg, monkeypatch):
    monkeypatch.setattr(offseason_fa, "_ai_bids", lambda *a: 0)
    monkeypatch.setattr(offseason_fa, "team_fit_for", lambda *a: (0.0, 0.5))
    _set_state(lg, "draft")
    pid = _free_agent(lg)
    ask = _ask(lg, pid).salary
    offseason_fa.place_bid(lg.db, lg.league.id, lg.mine.id, pid, ask, 2)
    offseason_fa.place_bid(lg.db, lg.league.id, lg.ai.id, pid, int(ask * 1.2), 2)

    signed = offseason_fa.settle(lg.db, lg.league.id)

    assert [(s["player_id"], s["team_id"]) for s in signed] == [(pid, lg.ai.id)]
    deal = lg.contracts.active(pid, 2026)
    assert (deal["team_id"], deal["salary"], deal["years"]) == (
        lg.ai.id,
        int(ask * 1.2),
        2,
    )
    assert deal["guaranteed"] and lg.status.get_status(pid) == "minors"
    assert offseason_fa.bid_counts(lg.db, lg.league.id, 2026) == {}


def test_a_good_fit_beats_a_little_more_money(lg, monkeypatch):
    monkeypatch.setattr(offseason_fa, "_ai_bids", lambda *a: 0)
    _set_state(lg, "draft")
    pid = _free_agent(lg)
    fit = {lg.mine.id: (1.0, 1.0), lg.ai.id: (-0.5, 1.0)}
    monkeypatch.setattr(
        offseason_fa, "team_fit_for", lambda person, p, home, team: team["fit"]
    )
    real = offseason_fa._fits

    def fits(conn, league_id, season_id, year, team_ids):
        out = real(conn, league_id, season_id, year, team_ids)
        for t in out:
            out[t]["fit"] = fit[t]
        return out

    monkeypatch.setattr(offseason_fa, "_fits", fits)
    ask = _ask(lg, pid).salary
    offseason_fa.place_bid(lg.db, lg.league.id, lg.mine.id, pid, ask, 2)
    offseason_fa.place_bid(lg.db, lg.league.id, lg.ai.id, pid, int(ask * 1.1), 2)
    signed = offseason_fa.settle(lg.db, lg.league.id)
    assert signed[0]["team_id"] == lg.mine.id


def test_a_lowball_bid_is_turned_down(lg, monkeypatch):
    monkeypatch.setattr(offseason_fa, "_ai_bids", lambda *a: 0)
    _set_state(lg, "draft")
    pid = _free_agent(lg, level=70)
    ask = _ask(lg, pid).salary
    offseason_fa.place_bid(lg.db, lg.league.id, lg.mine.id, pid, int(ask * 0.5), 3)
    assert offseason_fa.settle(lg.db, lg.league.id) == []
    assert lg.status.get_status(pid) == "free_agent"


def test_ai_teams_bid_on_free_agents_who_fill_holes(lg):
    _set_state(lg, "draft")
    lg.factory.rated_player(lg.ai, lg.league, level=40)
    pid = _free_agent(lg, level=75, pitcher=True)
    signed = offseason_fa.settle(lg.db, lg.league.id)
    assert pid in {s["player_id"] for s in signed}
    assert lg.contracts.active(pid, 2026)["team_id"] in (lg.ai.id, lg.other.id)


def test_older_players_value_years_more():
    ask = ct.Deal(10_000_000, 2, "standard")
    young = offseason_fa.bid_value(10_000_000, 5, ask, 26, 0, 0) - 1
    old = offseason_fa.bid_value(10_000_000, 5, ask, 33, 0, 0) - 1
    assert old > young > 0


def _rookie_expiring(lg, team, start, years):
    """A player who came up on a rookie deal (start..start+years-1) ending
    with 2026, so his next deal is an arbitration one."""
    pid = lg.factory.rated_player(team, lg.league, level=70, status="40man").id
    lg.contracts.insert_deal(
        pid, lg.league.id, team.id, ct.Deal(780_000, years, "rookie"), start
    )
    return pid


def test_an_unhappy_arbitration_player_cant_walk(lg, monkeypatch):
    from src.db.repositories.happiness_repo import HappinessRepository

    arb = _rookie_expiring(lg, lg.mine, 2024, 3)  # 2027 is his 4th season
    vet_unhappy = _expiring(lg, lg.mine, 2024, 3)
    monkeypatch.setattr(
        HappinessRepository, "latest_moods", lambda self, ids: {i: -0.9 for i in ids}
    )
    rows = {r["player_id"]: r for r in offseason_fa.expiring(lg.db, lg.league.id, 2026)}
    assert rows[arb]["deal"].kind == "arbitration"
    assert rows[arb]["arb_season"] == 4
    assert rows[arb]["market"] is None
    assert rows[arb]["market_salary"] > rows[arb]["deal"].salary
    # A non-arbitration unhappy player still goes to market.
    assert rows[vet_unhappy]["market"] == "unhappy"

    view = {
        v["player_id"]: v
        for v in offseason_fa.expiring_view(lg.db, lg.league.id, lg.mine.id)
    }
    assert view[arb]["arb_season"] == 4 and view[arb]["arb_of"] == 6
    assert view[arb]["arb_share"] == 55
    assert view[arb]["fate"] == "auto"
    assert view[vet_unhappy]["arb_season"] is None


# ── Bids through the preseason (Josh, 2026-11-12) ─────────────────────────────


def _league_row(lg):
    return lg.db.execute(
        "SELECT state, fa_bidding FROM leagues WHERE id = %s", (lg.league.id,)
    ).fetchone()


def test_the_draft_opens_bidding_and_it_lasts_into_the_preseason(lg):
    from src.db.repositories.league_repo import LeagueRepository

    lr = LeagueRepository(lg.db)
    lr.set_state(lg.league.id, "draft")
    assert _league_row(lg)["fa_bidding"] is True
    lr.set_state(lg.league.id, "preseason")
    assert _league_row(lg)["fa_bidding"] is True
    pid = _free_agent(lg)
    offseason_fa.place_bid(lg.db, lg.league.id, lg.mine.id, pid, 3_000_000, 2)
    with pytest.raises(FreeAgentError, match="bids"):
        free_agents.sign(lg.db, lg.league.id, lg.mine.id, pid)
    # Full price while the bids are open, the preseason step off after.
    assert free_agents.market_discount(lg.db, lg.league.id) == 1.0
    lr.set_state(lg.league.id, "season")
    assert _league_row(lg)["fa_bidding"] is False


def test_close_bidding_settles_once_and_closes(lg, monkeypatch):
    monkeypatch.setattr(offseason_fa, "_ai_bids", lambda *a: 0)
    from src.db.repositories.league_repo import LeagueRepository

    LeagueRepository(lg.db).set_state(lg.league.id, "draft")
    LeagueRepository(lg.db).set_state(lg.league.id, "preseason")
    pid = _free_agent(lg, level=70)
    ask = _ask(lg, pid).salary
    offseason_fa.place_bid(lg.db, lg.league.id, lg.mine.id, pid, ask, 2)
    lg.db.execute(
        "UPDATE gms SET roster_seen_season_id = 'x' WHERE team_id = %s", (lg.mine.id,)
    )
    signed = offseason_fa.close_bidding(lg.db, lg.league.id)
    assert [s["player_id"] for s in signed] == [pid]
    assert lg.contracts.active(pid, 2026)["team_id"] == lg.mine.id
    assert _league_row(lg)["fa_bidding"] is False
    assert not offseason_fa.bidding_open(lg.db, lg.league.id)
    assert free_agents.market_discount(lg.db, lg.league.id) == pytest.approx(0.9)
    # The GM who signed him gets the Roster step again.
    seen = lg.db.execute(
        "SELECT roster_seen_season_id FROM gms WHERE team_id = %s", (lg.mine.id,)
    ).fetchone()
    assert seen["roster_seen_season_id"] is None
    # A second close does nothing.
    assert offseason_fa.close_bidding(lg.db, lg.league.id) == []
    with pytest.raises(OffseasonFAError, match="closed"):
        offseason_fa.place_bid(
            lg.db, lg.league.id, lg.mine.id, _free_agent(lg), 3_000_000, 2
        )


def test_ai_teams_that_sign_rebuild_their_rosters(lg, monkeypatch):
    from src.api.services import front_office
    from src.db.repositories.league_repo import LeagueRepository

    monkeypatch.setattr(offseason_fa, "_ai_bids", lambda *a: 0)
    replanned = []
    monkeypatch.setattr(
        front_office,
        "replan_roster",
        lambda conn, lid, sid, tid, o, d: replanned.append(tid),
    )
    LeagueRepository(lg.db).set_state(lg.league.id, "draft")
    pid = _free_agent(lg, level=70)
    ask = _ask(lg, pid).salary
    offseason_fa.place_bid(lg.db, lg.league.id, lg.ai.id, pid, ask, 2)
    offseason_fa.close_bidding(lg.db, lg.league.id)
    assert replanned == [lg.ai.id]


def test_a_full_minors_skips_the_bid(lg, monkeypatch):
    monkeypatch.setattr(offseason_fa, "_ai_bids", lambda *a: 0)
    monkeypatch.setattr(offseason_fa, "MINORS_LIMIT", 0)
    _set_state(lg, "draft")
    pid = _free_agent(lg, level=70)
    offseason_fa.place_bid(
        lg.db, lg.league.id, lg.mine.id, pid, _ask(lg, pid).salary, 2
    )
    assert offseason_fa.settle(lg.db, lg.league.id) == []


# ── Veterans who won't re-sign (Josh, 2026-11-13) ─────────────────────────────


def test_refusals_are_rare_and_only_for_miserable_or_fame_driven_players():
    fame = hp.Personality("Spotlight Seeker", {d: 20 for d in hp.DRIVES} | {"fame": 90},
                          {"ego": 50, "temper": 50, "loyalty": 50})  # fmt: skip
    plain_guy = hp.Personality("Easygoing", {d: 20 for d in hp.DRIVES},
                               {"ego": 50, "temper": 50, "loyalty": 50})  # fmt: skip
    assert REFUSES_TO_RESIGN(-0.9, plain_guy, 3, 0.1) == "miserable"
    assert REFUSES_TO_RESIGN(-0.9, plain_guy, 3, 0.8) is None
    assert REFUSES_TO_RESIGN(-0.5, plain_guy, 1, 0.0) is None  # just unhappy
    assert REFUSES_TO_RESIGN(0.0, fame, 1, 0.1) == "fame"
    assert REFUSES_TO_RESIGN(0.0, fame, 3, 0.1) == "fame"
    assert REFUSES_TO_RESIGN(0.0, fame, 4, 0.1) is None  # a big market
    assert REFUSES_TO_RESIGN(0.0, fame, 1, 0.6) is None
    assert REFUSES_TO_RESIGN(0.5, fame, 1, 0.1) is None  # happy there
    assert REFUSES_TO_RESIGN(0.0, plain_guy, 1, 0.1) is None


def test_a_refusing_veteran_cant_be_re_signed_and_leaves(lg, monkeypatch):
    monkeypatch.setattr(offseason_fa.hp, "refuses_to_resign", lambda *a: "miserable")
    vet = _expiring(lg, lg.mine, 2021, 6, level=80)
    young = _expiring(lg, lg.mine, 2024, 3)  # under team control: never refuses
    ai_vet = _expiring(lg, lg.ai, 2021, 6, level=80)
    rows = {r["player_id"]: r for r in offseason_fa.expiring(lg.db, lg.league.id, 2026)}
    assert rows[vet]["refuses"] == "miserable"
    assert rows[young]["refuses"] is None
    with pytest.raises(OffseasonFAError, match="any price"):
        offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, vet, "resign")
    view = {
        v["player_id"]: v
        for v in offseason_fa.expiring_view(lg.db, lg.league.id, lg.mine.id)
    }
    assert view[vet]["fate"] == "go" and "any price" in view[vet]["refuses_text"]
    # Re-sign All skips him.
    plan = offseason_fa.resign_all_plan(lg.db, lg.league.id, lg.mine.id)
    assert plan["count"] == 1

    offseason_fa.close_window(lg.db, lg.league.id)
    assert lg.status.get_status(vet) == "free_agent"
    assert lg.status.get_status(ai_vet) == "free_agent"  # AI can't keep him
    assert lg.contracts.active(young, 2027)["start_year"] == 2027
    story = _news(lg, f"fa-leave:2026:{vet}")
    assert "refused to re-sign" in plain(story[0]["body"])

    # His old team can't win him back next season.
    assert free_agents.refused(lg.db, lg.league.id, lg.mine.id, vet, 2027)
    assert not free_agents.refused(lg.db, lg.league.id, lg.other.id, vet, 2027)
    assert not free_agents.refused(lg.db, lg.league.id, lg.mine.id, vet, 2028)

    # Bidding next season (the draft): his old team's bid is turned away.
    nxt = lg.factory.season(year=2027)
    lg.factory.league_season(lg.league, nxt)
    _set_state(lg, "draft")
    with pytest.raises(OffseasonFAError, match="refused"):
        offseason_fa.place_bid(lg.db, lg.league.id, lg.mine.id, vet, 9_000_000, 2)
    offseason_fa.place_bid(lg.db, lg.league.id, lg.other.id, vet, 9_000_000, 2)


# ── Speed Blitz: no money (Josh, 2026-11-14) ─────────────────────────────────


def _speed_blitz(lg):
    lg.db.execute(
        "UPDATE leagues SET mode = 'speed_blitz' WHERE id = %s", (lg.league.id,)
    )


def test_speed_blitz_re_signs_your_expiring_deals_on_their_own(lg, monkeypatch):
    """No Expiring Deals tab there: every deal of yours re-signs, even a
    veteran who'd go to market, one let go, or one who'd refuse."""
    monkeypatch.setattr(offseason_fa.hp, "refuses_to_resign", lambda *a: "miserable")
    _speed_blitz(lg)
    vet = _expiring(lg, lg.mine, 2021, 6, level=80)
    young = _expiring(lg, lg.mine, 2024, 3)
    cut = _expiring(lg, lg.mine, 2024, 3)
    lg.db.execute(
        """INSERT INTO contract_choices (league_id, player_id, team_id, year, choice)
           VALUES (%s, %s, %s, 2026, 'let_go')""",
        (lg.league.id, cut, lg.mine.id),
    )
    rows = {r["player_id"]: r for r in offseason_fa.expiring(lg.db, lg.league.id, 2026)}
    assert rows[vet]["refuses"] is None

    offseason_fa.close_window(lg.db, lg.league.id)

    for pid in (vet, young, cut):
        assert lg.contracts.active(pid, 2027)["start_year"] == 2027
        assert pid in _on(lg, lg.mine)


def test_speed_blitz_never_opens_bidding(lg):
    from src.db.repositories.league_repo import LeagueRepository

    _speed_blitz(lg)
    LeagueRepository(lg.db).set_state(lg.league.id, "draft")
    assert _league_row(lg)["fa_bidding"] is False
    pid = _free_agent(lg)
    free_agents.sign(lg.db, lg.league.id, lg.mine.id, pid)
    assert lg.status.get_status(pid) != "free_agent"
    assert free_agents.sign_preview(lg.db, lg.league.id, lg.mine.id, _free_agent(lg))[
        "no_money"
    ]
