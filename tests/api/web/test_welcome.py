# tests/api/web/test_welcome.py
"""
The welcome screen: once per GM when a league starts, before the draft, it
shows their new team (plans/welcome-screen.md).
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.view_models import welcome as wv
from src.db.repositories.gm_repo import GMRepository


@pytest.fixture
def league(db_conn, factory):
    """A new league waiting on its first draft: a human GM's Denver Beans,
    an AI GM's Chicago Wind, and opening day in Chicago."""
    league = factory.league(state="draft")
    season = factory.season(year=2025)
    draft = factory.draft(league=league, season=season)
    boston = factory.team(city="Denver", mascot="Beans")
    chicago = factory.team(city="Chicago", mascot="Wind")
    factory.draft_order(draft, [chicago, boston])
    human = factory.gm(team=boston, league=league, is_ai=False)
    factory.gm(team=chicago, league=league)
    for team, level in ((boston, 70), (chicago, 50)):
        for i in range(9):
            factory.rated_player(
                team, league, level=level, age=22 + 2 * i, name=f"H{i}"
            )
        for i in range(5):
            factory.rated_player(team, league, level=level, pitcher=True, name=f"P{i}")
    factory.game({"id": season.id}, {"id": chicago.id}, {"id": boston.id})
    return league, human, boston


@pytest.fixture
def client(db_conn, league):
    _, gm, team = league
    me = {"id": gm.id, "team_id": team.id}
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: me
    app.dependency_overrides[get_gm_or_viewer] = lambda: me
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def test_a_new_league_opens_on_the_welcome_screen_once(client, league):
    lg, _, _ = league

    first = client.get(f"/leagues/{lg.id}/")
    assert first.headers["location"] == f"/leagues/{lg.id}/welcome"

    page = client.get(f"/leagues/{lg.id}/welcome")
    assert page.status_code == 200
    assert "Welcome to the Denver Beans" in page.text
    assert "season preview" not in page.text
    assert f'href="/leagues/{lg.id}/draft"' in page.text

    again = client.get(f"/leagues/{lg.id}/")
    assert again.headers["location"] == f"/leagues/{lg.id}/draft"


def test_welcome_page_shows_the_team(client, league):
    lg, _, _ = league

    html = client.get(f"/leagues/{lg.id}/welcome").text

    assert "Your stars" in html and "Your colors" not in html
    assert html.count('class="wl-star-name"') == 5
    assert "1st of 2" in html  # Denver's 70s beat Chicago's 50s everywhere
    assert "at the <b>Chicago Wind</b>" in html
    assert "2025-04-01" in html
    assert "2<span" in html and "of 2" in html  # picks second
    assert "Tied for youngest of 2 teams" in html  # same ages on both teams
    assert "Chicago Wind" in html.split("Teams to beat")[1]


def test_later_seasons_open_on_the_season_preview_once(
    client, db_conn, factory, league
):
    lg, gm, team = league
    GMRepository(db_conn).mark_welcomed(gm.id)  # saw the first season's
    season = factory.season(year=2026)
    factory.league_season(lg, season)
    factory.draft(league=lg, season=season)

    first = client.get(f"/leagues/{lg.id}/")
    assert first.headers["location"] == f"/leagues/{lg.id}/welcome"

    html = client.get(f"/leagues/{lg.id}/welcome").text
    assert "2026 season preview" in html
    assert "The 2026 Denver Beans" in html
    assert "Welcome to the" not in html
    # On to the draft: the top bar's next move.
    assert f'<a class="btn nm-main" href="/leagues/{lg.id}/draft">' in html
    assert "Go to the draft →" in html

    again = client.get(f"/leagues/{lg.id}/")
    assert again.headers["location"] == f"/leagues/{lg.id}/draft"


def test_the_season_preview_shows_who_changed_over_the_winter(
    client, db_conn, factory, league
):
    lg, gm, team = league
    old = db_conn.execute(
        """SELECT ls.season_id FROM league_seasons ls WHERE ls.league_id = %s""",
        (lg.id,),
    ).fetchone()["season_id"]
    # Last season's skills: one player much worse then, one much better.
    db_conn.execute(
        """INSERT INTO player_skills_history
           SELECT ps.player_id, %s, ps.age, ps.durability, ps.clutch, ps.speed,
                  ps.power, ps.eye, ps.contact, ps.base_running, ps.bunting,
                  ps.catching, ps.infield, ps.outfield, ps.arm, ps.accuracy,
                  ps.stamina, ps.recovery, ps.ground_balls, ps.strikes, NOW()
           FROM player_skills ps JOIN team_players tp ON tp.player_id = ps.player_id
           WHERE tp.team_id = %s""",
        (old, team.id),
    )
    hitters = db_conn.execute(
        """SELECT p.id, p.first_name, p.last_name FROM players p
           JOIN team_players tp ON tp.player_id = p.id
           WHERE tp.team_id = %s AND p.position <> 'p' ORDER BY p.last_name""",
        (team.id,),
    ).fetchall()
    riser, faller = hitters[0], hitters[1]
    for pid, delta in ((riser["id"], -15), (faller["id"], 15)):
        db_conn.execute(
            """UPDATE player_skills_history SET contact = contact + %s,
                   power = power + %s, eye = eye + %s
               WHERE player_id = %s""",
            (delta, delta, delta, pid),
        )
    # The old season was played, so it's last season.
    db_conn.execute("UPDATE games SET completed = 1 WHERE season_id = %s", (old,))
    season = factory.season(year=2026)
    factory.draft_order(factory.draft(league=lg, season=season), [team])

    html = client.get(f"/leagues/{lg.id}/welcome").text

    winter = html.split("Over the winter")[1].split("Scouting report")[0]
    assert f"{riser['first_name']} {riser['last_name']}" in winter.split("Slipped")[0]
    assert f"{faller['first_name']} {faller['last_name']}" in winter.split("Slipped")[1]


def test_the_roster_links_back_to_it(client, db_conn, league):
    lg, gm, _ = league
    GMRepository(db_conn).mark_welcomed(gm.id)

    assert client.get(f"/leagues/{lg.id}/").headers["location"].endswith("/draft")
    assert client.get(f"/leagues/{lg.id}/welcome").status_code == 200


# ── View model pieces ─────────────────────────────────────────────────────────


def test_scouting_report_ranks_and_verdict():
    scores = {
        "me": {"lineup": 70, "rotation": 40, "bullpen": 55, "defense": 60},
        "b": {"lineup": 60, "rotation": 60, "bullpen": 60, "defense": 60},
        "c": {"lineup": 50, "rotation": 70, "bullpen": 50, "defense": 50},
    }
    # Power and speed are ranked too, but say how the lineup plays, so the
    # verdict ignores them even when they are the team's best or worst.
    for tid, (power, speed) in {"me": (40, 75), "b": (60, 50), "c": (50, 60)}.items():
        scores[tid].update(power=power, speed=speed)

    report = wv.scouting_report("me", scores)

    ranks = {a["key"]: a["rank"] for a in report["areas"]}
    assert ranks == {
        "lineup": 1,
        "rotation": 3,
        "bullpen": 2,
        "defense": 1,
        "power": 3,
        "speed": 1,
    }
    style = {a["key"] for a in report["areas"] if a["style"]}
    assert style == {"power", "speed"}
    assert report["verdict"] == (
        "Built around its lineup (1st of 3), but the rotation (3rd of 3) needs help."
    )


def test_age_rank_counts_from_the_nearer_end():
    class P:
        def __init__(self, age):
            self.age = age

    rosters = {t: [P(a)] for t, a in zip("abcdef", (24, 26, 27, 28, 30, 33))}

    assert wv.age_rank("a", rosters)["label"] == "Youngest of 6 teams"
    assert wv.age_rank("b", rosters)["label"] == "2nd youngest of 6 teams"
    assert wv.age_rank("c", rosters)["label"] == "3rd youngest of 6 teams"
    assert wv.age_rank("d", rosters)["label"] == "3rd oldest of 6 teams"
    assert wv.age_rank("f", rosters)["label"] == "Oldest of 6 teams"
    assert wv.age_rank("a", rosters)["league_average"] == 28.0

    third = {t: wv.age_rank(t, rosters)["outlook"] for t in rosters}
    assert [third[t] for t in "abcdef"] == [
        wv.AGE_OUTLOOKS[k] for k in ("young", "young", "middle", "middle", "old", "old")
    ]

    rosters["g"] = [P(26)]
    assert wv.age_rank("b", rosters)["label"] == "Tied for 2nd youngest of 7 teams"
    # Tied teams share a third.
    assert wv.age_rank("g", rosters)["outlook"] == wv.age_rank("b", rosters)["outlook"]
    assert wv.age_rank("a", {"a": rosters["a"]}) is None


def test_ordinals():
    assert [wv.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)] == [
        "1st",
        "2nd",
        "3rd",
        "4th",
        "11th",
        "12th",
        "13th",
        "21st",
        "22nd",
    ]


# ── The getting-started bar ───────────────────────────────────────────────────


def test_setup_bar_stays_until_the_roster_is_saved(client, db_conn, league):
    lg, _, team = league
    assert 'id="setup-bar"' in client.get(f"/leagues/{lg.id}/league").text

    ids = [
        r["player_id"]
        for r in db_conn.execute(
            "SELECT player_id FROM team_players WHERE team_id = %s", (team.id,)
        ).fetchall()
    ]
    r = client.put(f"/leagues/{lg.id}/roster/save", json={"forty_man": ids})
    assert r.status_code == 200

    assert 'id="setup-bar"' not in client.get(f"/leagues/{lg.id}/league").text


def test_running_the_draft_ends_the_setup_bar(client, db_conn, league):
    lg, _, _ = league
    db_conn.execute(
        "UPDATE drafts SET state = 'complete' WHERE league_id = %s", (lg.id,)
    )

    html = client.get(f"/leagues/{lg.id}/league").text

    assert 'id="setup-bar"' not in html


def test_persona_cards_link_back_to_where_they_came_from(client, db_conn, league):
    lg, _, _ = league
    persona = db_conn.execute("SELECT id FROM gm_personas LIMIT 1").fetchone()
    if not persona:
        pytest.skip("no personas in the library")
    url = f"/leagues/{lg.id}/personas/{persona['id']}"

    assert f'href="/leagues/{lg.id}/welcome"' in client.get(url + "?back=welcome").text
    assert "Back to the League page" in client.get(url).text
    assert "Back to the League page" in client.get(url + "?back=evil").text


def test_uniform_slugs():
    assert wv.uniform_slug("São Paulo") == "sao-paulo"
    assert wv.uniform_slug("Hong Kong") == "hong-kong"
    assert wv.uniform_slug("Tokyo") == "tokyo"


def test_every_pool_team_has_its_uniforms():
    from src.league.team_pool import TEAM_POOL

    for city in [t.city for t in TEAM_POOL]:
        u = wv.uniforms(city)
        assert u, city
        assert [p["label"] for p in u["jerseys"]] == ["Home", "Away", "Alternate"]
        assert [p["label"] for p in u["caps"]] == ["Cap", "Alternate cap"]
        for path in [p["path"] for p in u["jerseys"] + u["caps"]] + [u["patch"]]:
            assert (wv.UNIFORMS_DIR.parent.parent / path).exists(), path


def test_a_team_without_a_set_has_no_uniforms():
    assert wv.uniforms("Denver") is None


def test_welcome_page_shows_the_uniforms(client, league, monkeypatch):
    lg, _, _ = league
    html = client.get(f"/leagues/{lg.id}/welcome").text
    assert "Your uniforms" not in html  # Denver has no set

    tokyo = wv.uniforms("Tokyo")
    monkeypatch.setattr(wv, "uniforms", lambda city: tokyo)
    html = client.get(f"/leagues/{lg.id}/welcome").text
    assert "Your uniforms" in html
    for name in (
        "jersey-home",
        "jersey-away",
        "jersey-alternate",
        "cap",
        "cap-alternate",
        "patch",
    ):
        assert f"/static/img/uniforms/tokyo/{name}.svg" in html


@pytest.mark.parametrize(
    "mascot, verb",
    [
        ("Titans", "are"),
        ("Bear", "is"),
        ("Rain", "is"),
        ("Weird", "is"),
        ("Phoenix", "is"),
    ],
)
def test_taglines_agree_with_a_singular_or_plural_name(mascot, verb):
    assert wv.verbs(mascot)["are"] == verb
    for tagline in wv.TAGLINES:
        line = tagline.format(city="City", mascot=mascot, **wv.verbs(mascot))
        if verb == "is":
            assert "are yours" not in line and "Are the" not in line
            assert "Neither do " not in line


def test_area_grades_spread_across_simulated_teams():
    import random

    from src.league.offseason.draft_strategy import ratings
    from src.team.team_factory import TeamFactory

    factory = TeamFactory(rng=random.Random(11))
    scores = {}
    for i in range(24):
        team = factory.generate_team(city=f"City{i}", mascot="Sims", size=26)
        scores[str(i)] = wv.area_scores([(p, ratings(p)) for p in team.players])

    for key in ("lineup", "rotation", "power", "speed"):
        grades = {
            next(
                a["grade"]
                for a in wv.scouting_report(t, scores)["areas"]
                if a["key"] == key
            )
            for t in scores
        }
        assert len(grades) >= 5, (key, grades)


def test_the_draft_page_links_to_it(client, db_conn, league):
    lg, gm, _ = league
    GMRepository(db_conn).mark_welcomed(gm.id)

    html = client.get(f"/leagues/{lg.id}/draft").text

    assert (
        f'href="/leagues/{lg.id}/welcome" class="btn btn-secondary draft-team-btn"'
        in html
    )
    assert ">Meet your team</a>" in html


def test_every_team_link_goes_to_the_power_rankings(client, league):
    lg, _, _ = league
    html = client.get(f"/leagues/{lg.id}/welcome").text
    assert f'href="/leagues/{lg.id}/power" class="wl-meta wl-link"' in html


def test_power_rankings_lean_on_paper_early(client, db_conn, factory, league):
    lg, _, mine = league
    season_id = db_conn.execute(
        "SELECT season_id FROM drafts WHERE league_id = %s", (lg.id,)
    ).fetchone()["season_id"]
    teams = db_conn.execute(
        "SELECT team_id FROM gms WHERE league_id = %s", (lg.id,)
    ).fetchall()
    for t in teams:
        factory.league_season_team(
            lg, SimpleNamespace(id=season_id), SimpleNamespace(id=t["team_id"])
        )
    html = client.get(f"/leagues/{lg.id}/power").text
    assert "Power Rankings" in html and "After 1 game" in html
    # One game in, the rosters still decide: Denver's 70s beat Chicago's 50s
    assert "Ranked 97% on roster strength" in html
    assert html.index("Beans") < html.index("Wind")
    assert "Run diff" in html
    # Run diff, the three areas, L10 and the rank sort on click
    assert html.count('onclick="prSort(this)"') >= 6


def test_the_sidebar_links_to_it_until_the_draft_is_done(client, db_conn, league):
    lg, _, _ = league
    # The top bar's team chip links there with an href too.
    link = f'hx-get="/leagues/{lg.id}/welcome"'

    html = client.get(f"/leagues/{lg.id}/league").text
    assert link in html and '<span class="tab-label">Meet your team</span>' in html

    db_conn.execute(
        "UPDATE drafts SET state = 'complete' WHERE league_id = %s", (lg.id,)
    )
    assert link not in client.get(f"/leagues/{lg.id}/league").text


def test_welcome_page_shows_the_budget(client, db_conn, factory, league):
    from src.db.repositories.budget_repo import BudgetRepository
    from src.db.repositories.contract_repo import ContractRepository

    lg, _, team = league
    season_id = db_conn.execute(
        "SELECT season_id FROM drafts WHERE league_id = %s", (lg.id,)
    ).fetchone()["season_id"]
    db_conn.execute("UPDATE leagues SET mode = 'blitz' WHERE id = %s", (lg.id,))
    season = SimpleNamespace(id=season_id)
    factory.league_season(lg, season)
    for row in db_conn.execute(
        "SELECT DISTINCT team_id FROM gms WHERE league_id = %s", (lg.id,)
    ).fetchall():
        factory.league_season_team(lg, season, SimpleNamespace(id=row["team_id"]))
    contracts = ContractRepository(db_conn)
    contracts.sign_unsigned(lg.id, 2025)
    ids = [
        r["player_id"]
        for r in db_conn.execute(
            "SELECT player_id FROM team_players WHERE team_id = %s", (team.id,)
        ).fetchall()
    ]
    contracts.guarantee(ids)
    budgets = BudgetRepository(db_conn)
    assert budgets.for_league(lg.id, 2025)

    html = client.get(f"/leagues/{lg.id}/welcome").text

    assert "Your budget" in html
    assert "Payroll and the league cap" in html
    assert "Spending and your owner" in html
    assert "payroll of 2 teams" in html
    assert "Biggest contracts" in html and html.count("through 20") >= 3
    assert "Coaching <b" in html and "Standard" in html
    assert f'href="/leagues/{lg.id}/budget"' in html


def test_no_budget_card_without_budgets(client, league):
    lg, _, _ = league
    assert "Your budget" not in client.get(f"/leagues/{lg.id}/welcome").text
