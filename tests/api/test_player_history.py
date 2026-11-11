# tests/api/test_player_history.py
"""The player panel's History section (src/api/view_models/player_history.py)."""

from types import SimpleNamespace

import pytest

from src.api.view_models.player_history import player_history


@pytest.fixture
def lg(db_conn, factory):
    league = factory.league(state="season")
    s26, s27, s28 = (factory.season(year=y) for y in (2026, 2027, 2028))
    for s in (s26, s27, s28):
        factory.league_season(league, s)
    a = factory.team(city="Madrid", mascot="Conquistadors")
    b = factory.team(city="Boston", mascot="Beacons")
    c = factory.team(city="Tokyo", mascot="Captains")
    for t in (a, b, c):
        factory.league_season_team(league, s26, t)
    gm = factory.gm(team=a, league=league)
    return SimpleNamespace(
        db=db_conn, f=factory, league=league, s26=s26, s27=s27, s28=s28,
        a=a, b=b, c=c, gm=gm,
    )  # fmt: skip


def _deal(lg, pid, team, kind, start, years, salary, at, **kw):
    lg.db.execute(
        """INSERT INTO player_contracts (player_id, league_id, team_id, kind,
               salary, start_year, years, created_at, released_year,
               released_team_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (pid, lg.league.id, team.id, kind, salary, start, years, at,
         kw.get("released_year"), kw.get("released_team_id")),
    )  # fmt: skip


def _trade(lg, pid, season, gave, got, on, at):
    oid = lg.f._id()
    lg.db.execute(
        """INSERT INTO trade_offers (id, league_id, season_id, from_team_id,
               to_team_id, status, created_on, created_at, decided_at)
           VALUES (%s, %s, %s, %s, %s, 'accepted', %s, %s, %s)""",
        (oid, lg.league.id, season.id, gave.id, got.id, on, at, at),
    )
    lg.db.execute(
        "INSERT INTO trade_offer_items (offer_id, player_id, from_team_id)"
        " VALUES (%s, %s, %s)",
        (oid, pid, gave.id),
    )


def _texts(lg, pid):
    return [(h["year"], h["text"]) for h in player_history(lg.db, lg.league.id, pid)]


def test_a_draftee_traded_re_signed_released_and_claimed(lg):
    pid = lg.f.rated_player(lg.c, lg.league).id
    # Someone on an opening roster, so the league's start is its first deal.
    other = lg.f.rated_player(lg.a, lg.league).id
    _deal(lg, other, lg.a, "standard", 2025, 3, 1_000_000, "2026-01-01 00:00+00")

    draft = lg.f.draft(lg.league, lg.s26, state="complete")
    for n in range(1, 13):
        drafted = pid if n == 12 else lg.f.rated_player(lg.b, lg.league).id
        lg.db.execute(
            """INSERT INTO draft_picks (draft_id, pick_number, round, gm_id,
                   team_id, player_id, picked_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (draft.id, n, 1 if n <= 10 else 2, lg.gm.id, lg.a.id, drafted,
             "2026-02-01 00:00+00"),
        )  # fmt: skip
    _deal(lg, pid, lg.a, "rookie", 2026, 2, 800_000, "2026-02-02 00:00+00")
    game = lg.f.game(vars(lg.s26), vars(lg.a), vars(lg.b), game_date="2026-04-10")
    lg.db.execute(
        """INSERT INTO player_game_stats (game_id, player_id, team_id,
               opponent_team_id) VALUES (%s, %s, %s, %s)""",
        (game.id, pid, lg.a.id, lg.b.id),
    )
    _trade(lg, pid, lg.s26, lg.a, lg.b, "2026-07-20", "2026-03-01 00:00+00")
    _deal(
        lg, pid, lg.b, "standard", 2028, 3, 6_100_000, "2026-05-01 00:00+00",
        released_year=2028, released_team_id=lg.b.id,
    )  # fmt: skip
    lg.db.execute(
        """INSERT INTO waivers (league_id, player_id, from_team_id, placed_on,
               status, claimed_by, created_at)
           VALUES (%s, %s, %s, '2028-05-01', 'claimed', %s, %s)""",
        (lg.league.id, pid, lg.b.id, lg.c.id, "2026-06-01 00:00+00"),
    )
    # The claim takes over the deal (contract_repo.claim).
    lg.db.execute(
        """UPDATE player_contracts SET team_id = %s, released_year = NULL,
               released_team_id = NULL WHERE player_id = %s AND kind = 'standard'""",
        (lg.c.id, pid),
    )

    assert _texts(lg, pid) == [
        (2026, "Drafted by the Conquistadors: 2nd round, pick 2 (#12 overall)"),
        (2026, "Big league debut with the Conquistadors (2026-04-10)"),
        (2026, "Traded from the Conquistadors to the Beacons"),
        (2028, "Re-signed with the Beacons: 3 yrs, $6.1M/yr"),
        (2028, "Released by the Beacons"),
        (2028, "Claimed off waivers by the Captains"),
    ]


def test_an_opening_roster_player_who_leaves_in_free_agency(lg):
    pid = lg.f.rated_player(lg.a, lg.league).id
    _deal(lg, pid, lg.a, "standard", 2025, 2, 2_000_000, "2026-01-01 00:00+00")
    _deal(lg, pid, lg.b, "standard", 2027, 1, 3_000_000, "2026-09-01 00:00+00")
    _deal(
        lg, pid, lg.b, "standard", 2028, 2, 3_500_000, "2026-10-01 00:00+00",
        released_year=2028, released_team_id=lg.b.id,
    )  # fmt: skip

    assert _texts(lg, pid) == [
        (2026, "On the opening-day roster of the Conquistadors"),
        (2027, "Signed with the Beacons as a free agent: 1 yr, $3M/yr"),
        (2028, "Re-signed with the Beacons: 2 yrs, $3.5M/yr"),
        (2028, "Released by the Beacons"),
    ]


def test_opening_day_is_the_first_real_season_not_the_backstory(lg):
    # The league's made-up past seasons come before anyone signed.
    old = lg.f.season(year=2017)
    lg.db.execute("UPDATE seasons SET is_backstory = TRUE WHERE id = %s", (old.id,))
    lg.f.league_season(lg.league, old)
    pid = lg.f.rated_player(lg.a, lg.league).id
    _deal(lg, pid, lg.a, "standard", 2026, 1, 2_000_000, "2026-01-01 00:00+00")

    assert _texts(lg, pid) == [
        (2026, "On the opening-day roster of the Conquistadors"),
    ]


def test_nothing_to_show_for_a_new_free_agent(lg):
    pid = lg.f.rated_player(lg.a, lg.league, status="free_agent").id
    assert _texts(lg, pid) == []


def test_the_panel_shows_it_closed(lg):
    from fastapi.testclient import TestClient

    from src.api.database import get_db
    from src.api.dependencies import get_current_user, get_gm_or_viewer
    from src.api.main import app

    pid = lg.f.rated_player(lg.a, lg.league).id
    _deal(lg, pid, lg.a, "standard", 2025, 2, 2_000_000, "2026-01-01 00:00+00")
    _deal(lg, pid, lg.b, "standard", 2027, 1, 3_000_000, "2026-09-01 00:00+00")
    lg.f.game(vars(lg.s28), vars(lg.a), vars(lg.b), game_date="2028-04-10")
    app.dependency_overrides[get_db] = lambda: lg.db
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_gm_or_viewer] = lambda: {"id": None, "team_id": None}
    try:
        html = TestClient(app).get(f"/leagues/{lg.league.id}/players/{pid}/panel").text
    finally:
        app.dependency_overrides.clear()
    assert '<details class="pd-history">' in html
    assert "Signed with the Beacons as a free agent" in html
    import os

    if os.environ.get("HISTORY_HTML"):
        open(os.environ["HISTORY_HTML"], "w").write(html)
