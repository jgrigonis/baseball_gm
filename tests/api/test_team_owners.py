# tests/api/test_owners.py
"""Every team's owner in a league (src/api/services/owners.py), the Owner
tab, and the admin's owner pages."""

import html
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.services import owners as service
from src.db.repositories.owner_repo import OwnerRepository
from src.league import owners


@pytest.fixture
def lg(db_conn, factory):
    def make(n=4):
        league = factory.league(state="season")
        season = factory.season(year=2026)
        factory.league_season(league, season)
        teams = [factory.team(city=f"City{i}", mascot="Club") for i in range(n)]
        for t in teams:
            factory.league_season_team(league, season, t)
        gm = factory.gm(team=teams[0], league=league, is_ai=False)
        return SimpleNamespace(
            db=db_conn, league=league, season=season, teams=teams, gm=gm
        )

    return make


def test_every_team_gets_its_own_owner(lg):
    x = lg()
    by_team = service.ensure(x.db, x.league.id)
    assert set(by_team) == {t.id for t in x.teams}
    assert len({o["owner_id"] for o in by_team.values()}) == len(x.teams)
    for team_id, o in by_team.items():
        assert o["rival_team_id"] != team_id
        assert o["since_year"] == 2026  # the season hasn't started
    # Stored: asking again draws nothing new.
    assert service.ensure(x.db, x.league.id) == by_team


def test_an_owner_who_arrives_mid_season_judges_from_next_season(lg, factory):
    x = lg()
    factory.game({"id": x.season.id}, {"id": x.teams[0].id}, {"id": x.teams[1].id})
    by_team = service.ensure(x.db, x.league.id)
    assert {o["since_year"] for o in by_team.values()} == {2027}


def test_retired_owners_are_never_drawn(lg):
    x = lg()
    repo = OwnerRepository(x.db)
    keep = repo.create(
        "Only Choice",
        "",
        "The Showman",
        owners.clean_weights({}),
        owners.clean_traits({}),
        50,
    )
    x.db.execute("UPDATE owner_personas SET chance = 0 WHERE id <> %s", (keep,))
    by_team = service.ensure(x.db, x.league.id)
    assert {o["owner_id"] for o in by_team.values()} == {keep}  # repeats allowed


def test_the_card_shows_no_numbers(lg):
    x = lg()
    card = service.card(x.db, x.league.id, x.teams[0].id)
    assert card["name"] and card["archetype"]
    assert card["wants"] == owners.wants(card["archetype"])
    assert set(card) == {"name", "bio", "archetype", "wants", "rival", "since_year"}


def test_a_grudge_holder_names_the_rival(lg):
    x = lg(n=2)
    repo = OwnerRepository(x.db)
    grudge = repo.create(
        "Grudge Test",
        "",
        "The Grudge Holder",
        owners.clean_weights({"rivalry": 95}),
        owners.clean_traits({}),
        50,
    )
    calm = repo.create(
        "Calm Test",
        "",
        "The Absentee",
        owners.clean_weights({"rivalry": 10}),
        owners.clean_traits({}),
        50,
    )
    repo.seat(x.league.id, x.teams[0].id, grudge, x.teams[1].id, 2026)
    repo.seat(x.league.id, x.teams[1].id, calm, x.teams[0].id, 2026)
    assert service.card(x.db, x.league.id, x.teams[0].id)["rival"] == "City1 Club"
    assert service.card(x.db, x.league.id, x.teams[1].id)["rival"] is None


@pytest.fixture
def client_for():
    def make(x):
        app.dependency_overrides[get_db] = lambda: x.db
        app.dependency_overrides[get_current_user] = lambda: {"id": None}
        me = {"id": x.gm.id, "team_id": x.teams[0].id}
        app.dependency_overrides[get_current_gm] = lambda: me
        app.dependency_overrides[get_gm_or_viewer] = lambda: me
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


def test_the_owner_tab(lg, client_for):
    x = lg()
    r = client_for(x).get(f"/leagues/{x.league.id}/owner")
    assert r.status_code == 200
    text = html.unescape(r.text)
    mine = service.card(x.db, x.league.id, x.teams[0].id)
    assert "Your Owner" in text
    assert mine["name"] in text and mine["wants"] in text
    assert "Owners around the league" in text
    assert f'href="/leagues/{x.league.id}/owner"' in text  # in the tab bar
    for o in service.league_table(x.db, x.league.id):
        assert o["name"] in text
    assert "Patience" not in text and "Spending" not in text


def test_admins_see_what_their_owner_thinks(lg, client_for, factory):
    x = lg(n=2)
    a, b = x.teams
    service.ensure(x.db, x.league.id)
    for i in range(3):
        factory.game(
            {"id": x.season.id}, {"id": a.id}, {"id": b.id}, f"2026-04-0{i + 1}"
        )
    for g in x.db.execute(
        "SELECT id FROM games WHERE season_id = %s", (x.season.id,)
    ).fetchall():
        for team, win in ((a.id, 1), (b.id, 0)):
            x.db.execute(
                """INSERT INTO team_game_stats (game_id, team_id, win, loss, runs)
                   VALUES (%s, %s, %s, %s, 5)""",
                (g["id"], team, win, 1 - win),
            )
    client = client_for(x)
    r = client.get(f"/leagues/{x.league.id}/owner")
    assert "Owner happiness" not in r.text  # never for a GM
    app.dependency_overrides[get_current_user] = lambda: {"id": None, "is_admin": True}
    text = html.unescape(client.get(f"/leagues/{x.league.id}/owner").text)
    assert "Owner happiness" in text and "Admin only" in text
    assert "3-0 (1.000) vs target" in text  # what Winning was read from
    assert "Job security" in text and "Hot seat under" in text
    assert "This season so far" in text


# ── The owner's season review (src/api/services/owner_review.py) ─────────────


def test_owners_review_the_season(lg, factory):
    from src.api.services import owner_review

    x = lg(n=2)
    a, b = x.teams
    factory.gm(team=b, league=x.league, is_ai=True)
    service.ensure(x.db, x.league.id)  # seated before the season starts
    for i in range(3):
        factory.game(
            {"id": x.season.id}, {"id": a.id}, {"id": b.id}, f"2026-04-0{i + 1}"
        )
    # The game factory doesn't write team stats: record a 3-0 start for a.
    for g in x.db.execute(
        "SELECT id FROM games WHERE season_id = %s", (x.season.id,)
    ).fetchall():
        for team, win in ((a.id, 1), (b.id, 0)):
            x.db.execute(
                """INSERT INTO team_game_stats (game_id, team_id, win, loss, runs)
                   VALUES (%s, %s, %s, %s, 5)""",
                (g["id"], team, win, 1 - win),
            )
    out = owner_review.review_season(x.db, x.league.id, x.season.id, 2026)
    assert set(out) == {a.id, b.id}
    row = x.db.execute(
        "SELECT * FROM gm_season_evaluations WHERE gm_id = %s", (x.gm.id,)
    ).fetchone()
    assert row["wins"] == 3 and row["losses"] == 0
    assert row["verdict"] in ("retained", "warned")  # firing is off
    assert row["detail"]["scores"]["wins"] == 1.0
    assert 0 <= row["job_security"] <= 100
    assert out[a.id]["score"] > out[b.id]["score"]
    # Shown on the admin scorecard.
    assert (
        owner_review.security_now(x.db, x.league.id)[a.id]["job_security"]
        == (row["job_security"])
    )


def test_tearing_the_roster_down_doesnt_lower_the_bar(lg, factory):
    # Josh, 2026-11-11: a 90-72 team, gutted, was expected to play .428.
    from src.api.services import owner_review
    from src.db.repositories.team_state_repo import TeamStateRepository

    x = lg(n=2)
    a = x.teams[0]
    last = factory.season(year=2025)
    factory.league_season(x.league, last)
    by_team = service.ensure(x.db, x.league.id)
    repo = TeamStateRepository(x.db)

    def state(season, day, rank, gb):
        repo.add(x.league.id, season.id, a.id, day, "contending", 0, "contending",
                 {"rank_now": rank, "games_back": gb})  # fmt: skip

    state(last, "2025-09-01", 0.1, 0.0)  # strong all last season
    state(last, "2025-11-01", 0.9, None)  # torn down in the offseason
    state(x.season, "2026-03-01", 0.9, None)
    season = owner_review.gather(x.db, x.league.id, x.season.id, 2026, by_team)[a.id]
    assert season.rank_before == 0.1
    assert (season.rank_start, season.rank_last_season) == (0.9, 0.1)
    # A roster that got better is judged on where it is now.
    state(x.season, "2026-04-01", 0.05, 0.0)
    x.db.execute("DELETE FROM team_states WHERE as_of = '2026-03-01'")
    season = owner_review.gather(x.db, x.league.id, x.season.id, 2026, by_team)[a.id]
    assert season.rank_before == 0.05


def test_a_new_gm_starts_fresh(lg):
    from src.api.services import owner_review
    from src.league import owner_scoring as sc

    x = lg(n=2)
    owner = service.ensure(x.db, x.league.id)[x.teams[0].id]
    grace = sc.grace(owners.clean_traits(owner["traits"])["patience"])
    before, tenure = owner_review._tenure(x.db, x.gm.id, "someone", owner, 2027)
    assert before == grace and tenure.seasons == 0


# ── The owner's office (src/api/services/owner_office.py) ─────────────────────


def test_the_owner_writes_a_preseason_memo_once(lg, client_for):
    from src.api.services import owner_office

    x = lg(n=2)
    x.db.execute("UPDATE leagues SET state = 'preseason' WHERE id = %s", (x.league.id,))
    assert (
        owner_office.catch_up(x.db, x.league.id) == 1
    )  # our team; the other has no GM
    assert owner_office.catch_up(x.db, x.league.id) == 0
    assert owner_office.unseen(x.db, x.gm.id) == 1
    r = client_for(x).get(f"/leagues/{x.league.id}/owner")
    assert "Preseason memo" in r.text and "From the owner" in r.text
    assert owner_office.unseen(x.db, x.gm.id) == 0
    # Opened as a tab (htmx), the page clears the badge in the tab bar.
    tab = client_for(x).get(
        f"/leagues/{x.league.id}/owner", headers={"HX-Request": "true"}
    )
    assert "setOwnerBadge(0)" in tab.text


def test_the_first_memo_to_a_gm_welcomes_them(lg):
    import random

    from src.api.services import owner_office
    from src.league import owner_messages as om

    x = lg(n=2)
    x.db.execute("UPDATE leagues SET state = 'preseason' WHERE id = %s", (x.league.id,))
    owner_office.catch_up(x.db, x.league.id)
    body = x.db.execute(
        "SELECT body FROM owner_messages WHERE gm_id = %s", (x.gm.id,)
    ).fetchone()["body"]
    # Each welcome opener up to its first field.
    welcomes = [o.split("{")[0] for o in om.PRESEASON_WELCOME]
    assert any(body.startswith(w) for w in welcomes)
    # Later memos to the same GM open as usual.
    fields = {"gm": "Pat", "team": "City0 Club", "rival": None, "budget": None}
    for seed in range(10):
        later = om.preseason({}, fields, random.Random(seed))
        assert not any(later.startswith(w) for w in welcomes)
    assert owner_office.preseason_memo(
        x.db, x.league.id, x.teams[0].id, x.gm.id, x.season.id
    ) == {"body": body, "mood": "content"}


def test_the_season_review_message(lg, factory):
    from src.api.services import owner_office, owner_review

    x = lg(n=2)
    service.ensure(x.db, x.league.id)
    owner_review.review_season(x.db, x.league.id, x.season.id, 2026)
    assert owner_office.review(x.db, x.league.id, x.season.id) == 1
    office = owner_office.office(x.db, x.league.id, x.teams[0].id, x.gm.id)
    assert office["messages"][0]["kind"] == "review"
    assert office["mood"] in [w for _, w in owner_office.om.MOODS]


def test_the_mood_carries_into_next_season_until_its_first_week(lg, factory):
    """Josh saw no owner mood at the start of a season: moods are kept per
    season and the new one has none until a week of games is in."""
    from src.api.services import owner_office

    x = lg(n=2)
    service.ensure(x.db, x.league.id)
    team = x.teams[0].id
    x.db.execute(
        """INSERT INTO owner_moods (league_id, team_id, season_id, mood, as_of)
           VALUES (%s, %s, %s, -0.5, NULL)""",
        (x.league.id, team, x.season.id),
    )
    nxt = factory.season(year=2027)
    factory.league_season(x.league, nxt)
    x.db.execute("UPDATE leagues SET state = 'preseason' WHERE id = %s", (x.league.id,))
    office = owner_office.office(x.db, x.league.id, team, x.gm.id)
    assert office["mood"] == "frustrated"  # last season's, not blank
    assert owner_office.latest_moods(x.db, x.league.id, 2027) == {team: -0.5}


def test_an_owner_with_no_mood_yet_is_content(lg):
    from src.api.services import owner_office

    x = lg(n=2)
    service.ensure(x.db, x.league.id)
    office = owner_office.office(x.db, x.league.id, x.teams[0].id, x.gm.id)
    assert office["mood"] == "content"


def test_older_owner_messages_go_behind_the_button():
    """Josh: the owner's office list grew every season. Up front: this
    season's messages and last season's review (until this season has one),
    plus anything unread. The rest go under "Older messages"."""
    from src.api.services.owner_office import _split_recent

    def m(i, year, kind, seen=True):
        return {"id": i, "year": year, "kind": kind, "seen_at": "x" if seen else None}

    rows = [
        m(9, 2042, "preseason", seen=False),
        m(8, 2041, "review"),
        m(7, 2041, "checkin"),
        m(6, 2041, "preseason"),
        m(5, 2040, "review"),
        m(4, 2040, "checkin", seen=False),
    ]
    recent, older = _split_recent(rows)
    assert [r["id"] for r in recent] == [9, 8, 4]
    assert [r["id"] for r in older] == [7, 6, 5]

    # Once this season's review is in, last season's goes behind the button.
    recent, older = _split_recent(
        [m(10, 2041, "review"), m(9, 2041, "checkin"), m(8, 2040, "review")]
    )
    assert [r["id"] for r in recent] == [10, 9]
    assert [r["id"] for r in older] == [8]
    assert _split_recent([]) == ([], [])


# ── Reactions to releases and streaks ─────────────────────────────────────────


def _make_owner(x, weights=None, **traits):
    """Our team's owner, with these weights and traits (the rest 50)."""
    import json

    service.ensure(x.db, x.league.id)
    owner_id = OwnerRepository(x.db).in_league(x.league.id)[x.teams[0].id]["owner_id"]
    x.db.execute(
        "UPDATE owner_personas SET weights = %s, traits = %s WHERE id = %s",
        (json.dumps(weights or {}), json.dumps(traits), owner_id),
    )


def _release(x, factory, level, played=True, name="Star"):
    """Sign a player on our team at `level` and release him (guaranteed
    once he's played, so his deal is owed)."""
    from src.api.services import free_agents
    from src.db.repositories.contract_repo import ContractRepository

    x.db.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id,
                              away_team_id, completed)
           VALUES (%s, '2026-04-02', %s, %s, %s, 0) ON CONFLICT DO NOTHING""",
        (f"g-{x.season.id}", x.season.id, x.teams[0].id, x.teams[1].id),
    )
    pid = factory.rated_player(x.teams[0], x.league, level=level, name=name).id
    contracts = ContractRepository(x.db)
    contracts.sign_unsigned(x.league.id, 2026)
    if played:
        contracts.guarantee_teams([x.teams[0].id])
    return free_agents.release(x.db, x.league.id, x.teams[0].id, pid)


def _said(x, kind):
    return [
        r["body"]
        for r in x.db.execute(
            "SELECT body FROM owner_messages WHERE gm_id = %s AND kind = %s",
            (x.gm.id, kind),
        ).fetchall()
    ]


def test_a_meddler_has_a_word_on_releasing_a_good_player(lg, factory):
    """Josh released his best players and his Meddler said nothing. (A
    meddler now refuses those releases; these were made before he arrived
    at the desk, so he finds out after.)"""
    from src.api.services import owner_office

    x = lg(n=2)
    _make_owner(x, meddling=10)
    _release(x, factory, level=85, played=False)
    _make_owner(x, meddling=95)
    assert owner_office.reactions(x.db, x.league.id) == 1
    said = _said(x, "release")
    assert len(said) == 1 and "Test Star" in said[0]
    # Once only.
    assert owner_office.reactions(x.db, x.league.id) == 0
    # A second release later gets its own word, naming only him.
    _make_owner(x, meddling=10)
    _release(x, factory, level=85, played=False, name="Again")
    _make_owner(x, meddling=95)
    owner_office.reactions(x.db, x.league.id)
    said = _said(x, "release")
    assert len(said) == 2 and any("Test Again" in s and "Star" not in s for s in said)


def test_a_meddler_counts_the_dead_money(lg, factory):
    from src.api.services import owner_office

    x = lg(n=2)
    _make_owner(x, meddling=10)
    out = _release(x, factory, level=85)
    _make_owner(x, meddling=95)
    owner_office.reactions(x.db, x.league.id)
    (said,) = _said(x, "release")
    # Everything still owed him, every season left.
    assert out["total_text"] in said


def test_a_profit_minded_owner_minds_dead_money_right_away(lg, factory):
    x = lg(n=2)
    _make_owner(x, {"profit": 90}, meddling=10)
    out = _release(x, factory, level=85)
    (said,) = _said(x, "release")
    assert out["total_text"] in said


def test_a_meddler_wont_let_you_release_a_good_player(lg, factory, client_for):
    """Josh, 2026-11-11: vetoes in this PR."""
    from src.api.services import free_agents

    x = lg(n=2)
    _make_owner(x, meddling=95)
    pid = factory.rated_player(x.teams[0], x.league, level=85, name="Star").id
    with pytest.raises(free_agents.OwnerVeto) as e:
        free_agents.release(x.db, x.league.id, x.teams[0].id, pid)
    refusal = str(e.value)
    assert "Test Star" in refusal
    # Still ours, and the Release button hears why before it asks anything.
    r = client_for(x).get(f"/leagues/{x.league.id}/players/{pid}/release")
    assert r.json().get("vetoed") == refusal, r.text
    r = client_for(x).post(f"/leagues/{x.league.id}/players/{pid}/release")
    assert r.status_code == 409 and r.json()["vetoed"]
    # Kept in the owner's office, once.
    client_for(x).get(f"/leagues/{x.league.id}/players/{pid}/release")
    assert _said(x, "veto") == [refusal]
    assert _said(x, "release") == []


def test_a_meddler_lets_a_scrub_go(lg, factory):
    from src.api.services import owner_office

    x = lg(n=2)
    _make_owner(x, meddling=95)
    _release(x, factory, level=20, played=False)
    pid = factory.rated_player(x.teams[0], x.league, level=20).id
    assert owner_office.release_veto(x.db, x.league.id, x.teams[0].id, pid) is None


def test_a_hands_off_owner_never_vetoes(lg, factory):
    from src.api.services import owner_office

    x = lg(n=2)
    _make_owner(x, meddling=40)
    pid = factory.rated_player(x.teams[0], x.league, level=90).id
    assert owner_office.release_veto(x.db, x.league.id, x.teams[0].id, pid) is None


def test_a_hands_off_owner_lets_a_release_go(lg, factory):
    x = lg(n=2)
    _make_owner(x, meddling=10)
    _release(x, factory, level=85)
    assert _said(x, "release") == []


def test_nobody_minds_releasing_a_scrub(lg, factory):
    x = lg(n=2)
    _make_owner(x, meddling=95)
    _release(x, factory, level=20, played=False)
    assert _said(x, "release") == []


def test_who_minds_which_release():
    from src.api.services.owner_office import release_reason

    def owner(weights=None, **traits):
        return {"weights": weights or {}, "traits": traits}

    money = 5_000_000
    assert release_reason(owner(meddling=95), False, True, False, 0) == "meddling"
    assert (
        release_reason(owner(meddling=95), False, True, False, money)
        == "meddling_money"
    )
    assert release_reason(owner(meddling=95), True, True, True, 0) == "icons"
    assert (
        release_reason(owner({"profit": 80}), False, False, False, money)
        == "dead_money"
    )
    assert release_reason(owner({"profit": 80}), False, True, False, 0) is None
    assert release_reason(owner({"stars": 80}), False, True, True, 0) == "stars"
    assert (
        release_reason(owner({"stability": 80}), False, True, False, 0) == "stability"
    )
    assert release_reason(owner({"icons": 80}), True, True, False, 0) == "icons"
    assert release_reason(owner(), True, True, True, money) is None


def test_a_meddler_has_an_opinion_on_every_trade(lg, factory):
    from src.api.services import owner_office

    x = lg(n=2)
    _make_owner(x, meddling=95)
    x.db.execute(
        """INSERT INTO trade_offers (id, league_id, season_id, from_team_id,
               to_team_id, status, created_on, decided_at)
           VALUES ('t1', %s, %s, %s, %s, 'accepted', '2026-04-10', NOW())""",
        (x.league.id, x.season.id, x.teams[0].id, x.teams[1].id),
    )
    assert owner_office.reactions(x.db, x.league.id) == 1
    (said,) = _said(x, "trade")
    wordings = owner_office.om.TRADE_REACTIONS["meddling"]
    assert any(said.startswith(w.split("{")[0]) for w in wordings)


def _streak(x, length, won=False, start="2026-04-03"):
    from src.db.repositories.news_repo import NewsRepository

    team = x.teams[0].id
    headline = f"Club win {length} straight" if won else f"Club drop {length} in a row"
    NewsRepository(x.db).add(
        x.league.id, x.season.id, "2026-04-20", "streak",
        f"streak:{team}:{start}:{length}", headline, "",
        team_ids=[team], gm_ids=[x.gm.id],
    )  # fmt: skip


def test_a_hot_tempered_owner_reacts_to_a_losing_streak(lg):
    """Josh's Rain dropped 12 in a row and the owner said nothing."""
    from src.api.services import owner_office

    x = lg(n=2)
    _make_owner(x, temper=85)
    x.db.execute(
        """INSERT INTO owner_moods (league_id, team_id, season_id, mood, as_of)
           VALUES (%s, %s, %s, 0, '2026-04-15')""",
        (x.league.id, x.teams[0].id, x.season.id),
    )
    _streak(x, 8)
    _streak(x, 12)
    assert owner_office.reactions(x.db, x.league.id) == 1  # the longest mark
    (said,) = _said(x, "streak")
    assert said.startswith("Twelve")
    mood = owner_office.moods(x.db, x.league.id, x.season.id)[x.teams[0].id]
    assert mood["mood"] < 0 and mood["as_of"] == "2026-04-15"
    # The same streak running on to 16 gets another word.
    _streak(x, 16)
    assert owner_office.reactions(x.db, x.league.id) == 1
    assert owner_office.reactions(x.db, x.league.id) == 0
    # A short winning streak doesn't; a long one does.
    _streak(x, 7, won=True, start="2026-05-01")
    assert owner_office.reactions(x.db, x.league.id) == 0
    _streak(x, 10, won=True, start="2026-05-01")
    assert owner_office.reactions(x.db, x.league.id) == 1


def test_a_steady_owner_lets_a_streak_pass(lg):
    from src.api.services import owner_office

    x = lg(n=2)
    _make_owner(x, temper=20, meddling=20)
    _streak(x, 12)
    assert owner_office.reactions(x.db, x.league.id) == 0


def test_releasing_good_players_is_turnover():
    from src.league import owner_scoring as sc

    calm = sc.score_dimensions(sc.TeamSeason(80, 82), {}, False)["stability"]
    churn = sc.score_dimensions(sc.TeamSeason(80, 82, releases=3), {}, False)[
        "stability"
    ]
    assert churn < calm


def test_the_admin_card_says_what_attendance_was_read_from():
    from src.api.services import owner_debug
    from src.league import owner_scoring as sc

    s = sc.TeamSeason(
        wins=30, losses=40, crowd_score=-0.37, crowd_avg=34_000,
        crowd_expected=39_000, crowd_seats=42_000,
    )  # fmt: skip
    why = owner_debug._why("attendance", s, owners.clean_traits({}), "season")
    assert "Avg crowd 34,000 vs 39,000 expected (-13%" in why
    assert "park 81% full of 42,000" in why
