# tests/api/test_draft_class.py
"""Class grade vs now grade (src/api/services/draft_class.py, Josh
2026-11-17): a pick keeps the class grade he had on draft day, his Roster
row carries it through his first season, and his player panel says
"Drafted ... class X"."""

from types import SimpleNamespace

import pytest

from src.api.services import draft_class
from src.api.services.live_draft import LiveDraft
from src.api.view_models.player_cards import class_grade, now_grade, prospect_card


@pytest.fixture
def lg(db_conn, factory):
    league = factory.league(state="season")
    s26, s27 = factory.season(year=2026), factory.season(year=2027)
    for s in (s26, s27):
        factory.league_season(league, s)
    team = factory.team()
    gm = factory.gm(team=team, league=league)
    return SimpleNamespace(
        db=db_conn, f=factory, league=league, s26=s26, s27=s27, team=team, gm=gm
    )


def _pick(lg, draft, n, pid):
    lg.db.execute(
        """INSERT INTO draft_picks (draft_id, pick_number, round, gm_id,
               team_id, player_id, picked_at)
           VALUES (%s, %s, %s, %s, %s, %s, '2026-02-01')""",
        (draft.id, n, 1 if n <= 2 else 2, lg.gm.id, lg.team.id, pid),
    )
    draft_class.record(lg.db, draft.id, pid)


def test_record_keeps_the_class_grade_from_draft_day(lg):
    pid = lg.f.rated_player(lg.team, lg.league, level=60).id
    draft = lg.f.draft(lg.league, lg.s26, state="complete")
    _pick(lg, draft, 1, pid)
    kept = lg.db.execute(
        "SELECT class_grade FROM draft_picks WHERE player_id = %s", (pid,)
    ).fetchone()["class_grade"]
    skills = lg.db.execute(
        "SELECT * FROM player_skills WHERE player_id = %s", (pid,)
    ).fetchone()
    assert kept and kept == class_grade(dict(skills), "R")


def test_attach_tags_only_this_seasons_draftees(lg):
    old = lg.f.rated_player(lg.team, lg.league).id
    new = lg.f.rated_player(lg.team, lg.league).id
    vet = lg.f.rated_player(lg.team, lg.league).id
    _pick(lg, lg.f.draft(lg.league, lg.s26, state="complete"), 1, old)
    _pick(lg, lg.f.draft(lg.league, lg.s27, state="complete"), 1, new)
    cards = [{"player_id": p} for p in (old, new, vet)]
    draft_class.attach(lg.db, lg.league.id, lg.s27.id, cards)
    assert [bool(c.get("class_grade")) for c in cards] == [False, True, False]


def test_drafted_line_for_the_panel(lg):
    pid = lg.f.rated_player(lg.team, lg.league).id
    draft = lg.f.draft(lg.league, lg.s27, state="complete")
    _pick(lg, draft, 1, lg.f.rated_player(lg.team, lg.league).id)
    _pick(lg, draft, 2, lg.f.rated_player(lg.team, lg.league).id)
    _pick(lg, draft, 3, pid)
    d = draft_class.drafted(lg.db, lg.league.id, pid)
    assert (d["year"], d["round"], d["in_round"]) == (2027, 2, 1)
    assert d["class_grade"]
    # Picks from before class grades were kept get no line.
    lg.db.execute(
        "UPDATE draft_picks SET class_grade = NULL WHERE player_id = %s", (pid,)
    )
    assert draft_class.drafted(lg.db, lg.league.id, pid) is None


def test_prospect_card_has_class_and_now_grades():
    skills = {k: 55 for k in (
        "durability", "clutch", "speed", "power", "eye", "contact", "base_running",
        "bunting", "catching", "infield", "outfield", "arm", "accuracy", "stamina",
        "recovery", "ground_balls", "strikes")}  # fmt: skip
    row = {"id": "x", "first_name": "A", "last_name": "B", "position": "ss",
           "bats": "R", "throws": "R", "age": 21, "status": "prospect"}  # fmt: skip
    card = prospect_card(row, {**skills, "age": 21})
    assert card["overall"] == class_grade(skills, "R")
    assert card["now_grade"] and card["now_grade"] != "?"
    assert now_grade("hitter", {}) is None


def test_live_draft_pick_keeps_the_class_grade(db_conn, factory):
    league = factory.league(state="draft", mode="longform")
    season = factory.season()
    factory.league_season(league, season)
    draft = factory.draft(league=league, season=season, fmt="interactive")
    ai = factory.team()
    factory.gm(team=ai, league=league, is_ai=True)
    factory.draft_order(draft, [ai])
    for _ in range(3):
        factory.prospect(league_id=league.id)
    LiveDraft(db_conn, draft.id, lock=True).start()
    rows = db_conn.execute(
        "SELECT class_grade FROM draft_picks WHERE draft_id = %s", (draft.id,)
    ).fetchall()
    assert rows and all(r["class_grade"] for r in rows)
