# tests/api/web/test_season_summary.py
"""The season summary shows a past season in full: champion and best record,
leaders, standings, playoff results and that season's draft. The History tab
links straight to each season's draft results and standings."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.view_models.draft import last_season
from src.api.view_models.seasons import season_summary_context


def _id():
    return str(uuid.uuid4())


def _player(db, league, first, last):
    pid = _id()
    db.execute(
        "INSERT INTO players (id, first_name, last_name, bats, throws, position, league_id)"
        " VALUES (%s, %s, %s, 'R', 'R', 'of', %s)",
        (pid, first, last, league.id),
    )
    return pid


def _stats(db, player_id, season, team, **cols):
    cols = {"bat_games_played": 10, **cols}
    names = ", ".join(cols)
    marks = ", ".join(["%s"] * len(cols))
    db.execute(
        f"INSERT INTO player_season_stats (player_id, season_id, team_id, {names})"
        f" VALUES (%s, %s, %s, {marks})",
        (player_id, season.id, team.id, *cols.values()),
    )


def _game(db, season, winner, loser, series_id=None):
    gid = _id()
    db.execute(
        """INSERT INTO games (id, game_date, season_id, series_id, home_team_id,
               away_team_id, home_score, away_score, winner_id, completed)
           VALUES (%s, '2025-06-01', %s, %s, %s, %s, 5, 3, %s, 1)""",
        (gid, season.id, series_id, winner.id, loser.id, winner.id),
    )
    for team, runs, won in ((winner, 5, 1), (loser, 3, 0)):
        db.execute(
            "INSERT INTO team_game_stats (game_id, team_id, runs, win, loss)"
            " VALUES (%s, %s, %s, %s, %s)",
            (gid, team.id, runs, won, 1 - won),
        )
    return gid


@pytest.fixture
def league(db_conn, factory):
    """A league in its 2026 season, with 2025 played out in full."""
    league = factory.league(state="season")
    past = factory.season(year=2025)
    current = factory.season(year=2026)
    factory.league_season(league, past)
    factory.league_season(league, current)

    best = factory.team(city="Boston", mascot="Best")
    champ = factory.team(city="Chicago", mascot="Champs")
    mine = factory.team(city="My", mascot="Team")
    for team in (best, champ, mine):
        factory.league_season_team(league, past, team)
        factory.league_season_team(league, current, team)
    gm = factory.gm(team=mine, league=league, is_ai=False)
    ai_gm = factory.gm(team=best, league=league)

    # Regular season: Best 3-0, Champs 1-2, Mine 1-2
    _game(db_conn, past, best, champ)
    _game(db_conn, past, best, mine)
    _game(db_conn, past, best, mine)
    _game(db_conn, past, champ, mine)
    _game(db_conn, past, mine, champ)

    # Finals: Champs beat Best 4-1
    finals = _id()
    db_conn.execute(
        "INSERT INTO series (id, season_id, name) VALUES (%s, %s, 'Finals')",
        (finals, past.id),
    )
    for _ in range(4):
        _game(db_conn, past, champ, best, finals)
    _game(db_conn, past, best, champ, finals)

    avg = _player(db_conn, league, "Ray", "Hudgins")
    hr = _player(db_conn, league, "Hal", "Homer")
    era = _player(db_conn, league, "Will", "Wilson")
    k = _player(db_conn, league, "Kay", "Kane")
    _stats(db_conn, avg, past, champ, bat_ab=40, bat_hits=16, bat_home_runs=1)
    _stats(db_conn, hr, past, best, bat_ab=40, bat_hits=10, bat_home_runs=9)
    _stats(
        db_conn, era, past, mine,
        pitch_outs=90, pitch_earned_runs=5, pitch_strike_outs=20,
    )  # fmt: skip
    _stats(
        db_conn, k, past, best,
        pitch_outs=90, pitch_earned_runs=20, pitch_strike_outs=60,
    )  # fmt: skip

    # The draft held before the 2025 season
    draft = factory.draft(league=league, season=past, state="complete")
    rookie = _player(db_conn, league, "Rookie", "Pick")
    db_conn.execute(
        """INSERT INTO draft_picks (draft_id, pick_number, round, gm_id, team_id, player_id)
           VALUES (%s, 1, 1, %s, %s, %s)""",
        (draft.id, ai_gm.id, best.id, rookie),
    )

    return {
        "league": league,
        "past": past,
        "current": current,
        "gm": gm,
        "mine": mine,
        "best": best,
        "champ": champ,
        "players": {"avg": avg, "hr": hr, "era": era, "k": k, "rookie": rookie},
    }


@pytest.fixture
def client(db_conn, league):
    app.dependency_overrides[get_db] = lambda: db_conn
    gm = {"id": league["gm"].id, "team_id": league["mine"].id}
    app.dependency_overrides[get_current_gm] = lambda: gm
    app.dependency_overrides[get_gm_or_viewer] = lambda: gm
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def _summary(db, league):
    return season_summary_context(
        db, league["league"].id, league["past"].id, None, league["mine"].id
    )


def test_top_row_has_champion_and_best_record(db_conn, league):
    ctx = _summary(db_conn, league)
    assert ctx["champion"]["team_id"] == league["champ"].id
    best = ctx["best_record"]
    assert best["team_id"] == league["best"].id
    assert (best["wins"], best["losses"]) == (3, 0)


def test_leader_row_is_avg_hr_era_k(db_conn, league):
    ctx = _summary(db_conn, league)
    players = league["players"]
    assert [(lead["label"], lead["player_id"]) for lead in ctx["top_leaders"]] == [
        ("AVG", players["avg"]),
        ("HR", players["hr"]),
        ("ERA", players["era"]),
        ("K", players["k"]),
    ]


def test_summary_shows_standings_playoffs_and_draft(db_conn, league):
    ctx = _summary(db_conn, league)
    assert [t["team_id"] for t in ctx["standings"]][0] == league["best"].id
    finals = ctx["playoff_rounds"][-1]["series"][0]
    assert finals["decided"]
    assert finals["leader"]["team_id"] == league["champ"].id
    assert (finals["leader"]["wins"], finals["trailer"]["wins"]) == (4, 1)
    picks = ctx["draft_round"]["picks"]
    assert picks[0]["player_id"] == league["players"]["rookie"]


def test_summary_page_makes_players_clickable_and_links_out(client, league):
    lid, sid = league["league"].id, league["past"].id
    r = client.get(f"/leagues/{lid}/season-summary?season_id={sid}")
    assert r.status_code == 200
    for pid in league["players"].values():
        assert f"openPlayerPanel('{pid}')" in r.text
    assert f"/leagues/{lid}/playoffs?season_id={sid}" in r.text
    assert f"/leagues/{lid}/standings?season_id={sid}" in r.text
    assert f"/leagues/{lid}/draft/results?season_id={sid}" in r.text
    assert f"/leagues/{lid}/leaders?season={sid}" in r.text
    assert "Best Record" in r.text


def test_summary_ignores_another_leagues_season(db_conn, factory, league):
    other = factory.season(year=1999)
    ctx = season_summary_context(
        db_conn, league["league"].id, other.id, league["current"].id, None
    )
    # Falls back to the last season with playoffs
    assert ctx["season_year"] == 2025


def test_history_links_draft_and_standings(client, league):
    lid, sid = league["league"].id, league["past"].id
    r = client.get(f"/leagues/{lid}/history")
    assert r.status_code == 200
    assert f"/leagues/{lid}/draft/results?season_id={sid}" in r.text
    assert f"/leagues/{lid}/standings?season_id={sid}" in r.text
    # 2026 has no draft yet, so it gets no draft link
    current = league["current"].id
    assert f"/leagues/{lid}/draft/results?season_id={current}" not in r.text


def test_standings_for_a_past_season(client, league):
    lid, sid = league["league"].id, league["past"].id
    r = client.get(f"/leagues/{lid}/standings?season_id={sid}")
    assert r.status_code == 200
    assert "2025 Standings" in r.text
    assert "Boston" in r.text
    assert "Injury Report" not in r.text


def test_draft_results_for_a_past_season(client, league):
    lid, sid = league["league"].id, league["past"].id
    r = client.get(f"/leagues/{lid}/draft/results?season_id={sid}")
    assert r.status_code == 200
    assert "2025 Draft Results" in r.text
    assert "Rookie Pick" in r.text


def test_playoffs_for_a_past_season(client, league):
    lid, sid = league["league"].id, league["past"].id
    r = client.get(f"/leagues/{lid}/playoffs?season_id={sid}")
    assert r.status_code == 200
    assert "2025 Playoffs" in r.text
    assert "Champion: Chicago Champs" in r.text
    assert f"/season-summary?season_id={sid}" in r.text


def _injure(db, league, player_id, season, team, day, days):
    from src.db.repositories.injury_repo import InjuryRepository

    InjuryRepository(db, league.id).injure(
        player_id, season.id, day, severity="moderate", activity="fielding",
        days=days, team_id=team.id,
    )  # fmt: skip


def test_summary_lists_my_teams_injuries(db_conn, league):
    lg, past = league["league"], league["past"]
    players = league["players"]
    _injure(db_conn, lg, players["era"], past, league["mine"], "2025-05-01", 12)
    _injure(db_conn, lg, players["hr"], past, league["best"], "2025-05-02", 30)
    # The same player hurt again the next season belongs to that season
    _injure(
        db_conn, lg, players["era"], league["current"], league["mine"], "2026-05-01", 4
    )

    ctx = _summary(db_conn, league)
    assert [i["player_id"] for i in ctx["injuries"]] == [players["era"]]
    assert ctx["injury_days_total"] == 12
    assert not ctx["injuries_league_wide"]

    # A viewer with no team sees every team's injuries
    ctx = season_summary_context(db_conn, lg.id, past.id, None, None)
    assert ctx["injuries_league_wide"]
    assert [i["player_id"] for i in ctx["injuries"]] == [players["era"], players["hr"]]
    assert ctx["injuries"][1]["team"] == "Boston Best"


def test_summary_page_shows_injuries(client, db_conn, league):
    lg, past = league["league"], league["past"]
    _injure(
        db_conn, lg, league["players"]["era"], past, league["mine"], "2025-05-01", 12
    )
    r = client.get(f"/leagues/{lg.id}/season-summary?season_id={past.id}")
    assert 'id="injuries"' in r.text
    assert "My Team Injuries" in r.text or "Your Team Injuries" in r.text
    assert "Will Wilson" in r.text
    assert "12d" in r.text


def test_summary_page_with_no_injuries_says_so(client, league):
    lg, past = league["league"], league["past"]
    r = client.get(f"/leagues/{lg.id}/season-summary?season_id={past.id}")
    assert "No injuries this season." in r.text


def test_history_links_each_seasons_injuries(client, league):
    lid, sid = league["league"].id, league["past"].id
    r = client.get(f"/leagues/{lid}/history")
    assert f"/leagues/{lid}/season-summary?season_id={sid}#injuries" in r.text


def test_summary_page_shows_no_hitters_and_injuries_together(client, db_conn, league):
    """Both sections render side by side, each closed off before the draft."""
    lg, past, players = league["league"], league["past"], league["players"]
    gid = _game(db_conn, past, league["mine"], league["champ"])
    db_conn.execute(
        """INSERT INTO player_game_stats (player_id, game_id, team_id, opponent_team_id,
               pitch_no_hitter, pitch_strike_outs, pitch_walks)
           VALUES (%s, %s, %s, %s, 1, 11, 2)""",
        (players["era"], gid, league["mine"].id, league["champ"].id),
    )
    _injure(db_conn, lg, players["hr"], past, league["mine"], "2025-05-01", 12)
    r = client.get(f"/leagues/{lg.id}/season-summary?season_id={past.id}")
    assert r.status_code == 200
    text = r.text
    injuries, no_hitters = text.index('id="injuries"'), text.index("No-Hitters")
    draft = text.index("Draft · Round 1")
    assert injuries < no_hitters < draft
    assert "11K 2BB" in text
    assert "Hal Homer" in text[injuries:no_hitters]


def test_injury_table_has_sortable_headers(client, db_conn, league):
    lg, past = league["league"], league["past"]
    _injure(
        db_conn, lg, league["players"]["era"], past, league["mine"], "2025-05-01", 12
    )
    r = client.get(f"/leagues/{lg.id}/season-summary?season_id={past.id}")
    table = r.text[
        r.text.index('id="injury-table"') : r.text.index(
            "</table>", r.text.index('id="injury-table"')
        )
    ]
    for label in ("Date", "Player", "Injury", "Days"):
        assert f">{label}<span" in table
    assert table.count('onclick="sortInjuries(this)"') == 4
    # Each column carries a value to sort by; severity sorts by its longest layoff
    assert 'data-sort="2025-05-01"' in table
    assert 'data-sort="Wilson Will"' in table  # last name first
    assert 'data-sort="50"' in table  # moderate
    assert 'data-sort="12"' in table


def test_the_draft_board_shows_how_each_team_finished(db_conn, factory, league):
    """The next draft's board: last season's record, place and playoff run."""
    draft = factory.draft(league=league["league"], season=league["current"])

    def finish(team):
        return last_season(db_conn, league["league"].id, team.id, draft.season_id)

    assert finish(league["mine"]) == {
        "year": 2025,
        "w": 1,
        "l": 3,
        "place": "3rd",
        "teams": 3,
        "playoffs": "missed the playoffs",
    }
    assert finish(league["champ"])["playoffs"] == "won the championship"
    assert finish(league["best"])["playoffs"] == "lost in the Finals"
    # The league's first draft has no last season.
    assert (
        last_season(db_conn, league["league"].id, league["mine"].id, league["past"].id)
        is None
    )


def test_the_draft_page_shows_last_season(db_conn, factory, league, client):
    factory.draft(league=league["league"], season=league["current"])
    db_conn.execute(
        "UPDATE leagues SET state = 'draft' WHERE id = %s", (league["league"].id,)
    )
    r = client.get(f"/leagues/{league['league'].id}/draft")
    assert r.status_code == 200
    assert "Last season: 1–3, 3rd of 3" in r.text
    assert "missed the playoffs" in r.text
    assert "The front office sees" in r.text


def _award(db, season, award, player_id, team, scope="", position="", line="x"):
    db.execute(
        """INSERT INTO season_awards (season_id, award, scope, position,
               player_id, team_id, line)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (season.id, award, scope, position, player_id, team.id, line),
    )


def test_my_team_card_has_my_teams_leaders(db_conn, league):
    """Only my team's players: Wilson is my one pitcher, and I have no
    qualified hitter, so the card leaves the hitting stats out."""
    ctx = _summary(db_conn, league)
    era = league["players"]["era"]
    assert [(lead["label"], lead["player_id"]) for lead in ctx["my_leaders"]] == [
        ("W", era),
        ("ERA", era),
        ("K", era),
    ]
    assert ctx["my_leaders"][1]["val"] == "1.50"


def test_my_team_card_lists_my_award_winners(db_conn, league):
    past, players = league["past"], league["players"]
    _award(db_conn, past, "cy_young", players["era"], league["mine"], line="1.50 ERA")
    _award(db_conn, past, "mvp", players["hr"], league["best"])
    _award(
        db_conn, past, "gold_glove", players["era"], league["mine"],
        position="p", line="P, 0 errors",
    )  # fmt: skip
    ctx = _summary(db_conn, league)
    assert [(h["what"], h["player_id"]) for h in ctx["my_highlights"]] == [
        ("Cy Young", players["era"]),
        ("Gold Glove P", players["era"]),
    ]


def test_summary_page_shows_my_team_card(client, db_conn, league):
    _award(
        db_conn, league["past"], "cy_young", league["players"]["era"],
        league["mine"], line="1.50 ERA",
    )  # fmt: skip
    lid, sid = league["league"].id, league["past"].id
    r = client.get(f"/leagues/{lid}/season-summary?season_id={sid}")
    assert "Team leader in ERA: Will Wilson" in r.text
    assert "ss-chip" in r.text and "Cy Young" in r.text


def test_no_team_no_team_card(db_conn, league):
    ctx = season_summary_context(
        db_conn, league["league"].id, league["past"].id, None, None
    )
    assert ctx["my_leaders"] == [] and ctx["my_highlights"] == []


def _all_star_break(db, league):
    """2025's All-Stars, and its Rookie Game and All-Star Game played: Ray
    Hudgins (Champs) MVP of the All-Star Game, Will Wilson (mine) of the
    Rookie Game."""
    p, past = league["players"], league["past"].id
    champ, best, mine = league["champ"].id, league["best"].id, league["mine"].id
    for pid, team, slot in (
        (p["avg"], champ, "1b"),
        (p["hr"], best, "c"),
        (p["k"], best, "p"),
        (p["era"], mine, "p"),
    ):
        db.execute(
            "INSERT INTO all_stars (season_id, player_id, team_id, slot, points)"
            " VALUES (%s, %s, %s, %s, 1)",
            (past, pid, team, slot),
        )
    db.execute(
        "INSERT INTO rookie_game_players (season_id, player_id, team_id, slot)"
        " VALUES (%s, %s, %s, 'p')",
        (past, p["rookie"], mine),
    )
    for table, stats, mvp, score in (
        ("all_star_games", "all_star_game_stats", p["avg"], (3, 5)),
        ("rookie_games", "rookie_game_stats", p["rookie"], (4, 2)),
    ):
        db.execute(
            f"""INSERT INTO {table} (season_id, captain1_team_id, captain2_team_id,
                   state, score1, score2, innings, mvp_player_id)
               VALUES (%s, %s, %s, 'played', %s, %s, 9, %s)""",
            (past, best, champ, *score, mvp),
        )
        db.execute(
            f"""INSERT INTO {stats} (season_id, player_id, side, batting_order,
                   bat_ab, bat_hits, bat_home_runs, bat_rbi)
               VALUES (%s, %s, 2, 3, 4, 2, 1, 3)""",
            (past, mvp),
        )


def test_summary_lists_all_stars_and_game_mvps(db_conn, league):
    _all_star_break(db_conn, league)
    p = league["players"]
    ctx = _summary(db_conn, league)
    # A row per position, in the ballot's order: C, 1B, then the pitchers.
    assert [r["position"] for r in ctx["all_stars"]] == ["C", "1B", "P"]
    assert [x["player_id"] for x in ctx["all_stars"][2]["players"]] == [
        p["k"],
        p["era"],
    ]
    assert ctx["all_star_mine"] == 1
    rookie, asg = ctx["all_star_games"]
    assert rookie["name"] == "Rookie Game" and asg["name"] == "All-Star Game"
    assert asg["mvp"]["player_id"] == p["avg"]
    assert asg["mvp"]["team"] == "Chicago Champs" and not asg["mvp"]["is_mine"]
    assert asg["mvp"]["line"] == "2-4, HR, 3 RBI"
    assert asg["final"] == "Team Chicago 5, Team Boston 3"
    assert (
        rookie["mvp"]["is_mine"] and rookie["final"] == "Team Boston 4, Team Chicago 2"
    )
    # My team's MVP gets a highlight chip.
    assert any(h["what"] == "Rookie Game MVP" for h in ctx["my_highlights"])


def test_summary_page_shows_all_stars(client, db_conn, league):
    _all_star_break(db_conn, league)
    lid, sid = league["league"].id, league["past"].id
    r = client.get(f"/leagues/{lid}/season-summary?season_id={sid}")
    assert r.status_code == 200
    assert 'id="all-stars"' in r.text
    assert "All-Star Game MVP" in r.text and "Rookie Game MVP" in r.text
    assert "2025 All-Stars" in r.text


def test_no_all_star_break_no_card(client, league):
    lid, sid = league["league"].id, league["past"].id
    r = client.get(f"/leagues/{lid}/season-summary?season_id={sid}")
    assert 'id="all-stars"' not in r.text


def test_my_team_card_has_every_honor(db_conn, league):
    """My team's chips include its All-Stars, the HR Derby champ and a Hall
    of Famer in its cap, not only the awards."""
    _all_star_break(db_conn, league)
    p, past = league["players"], league["past"].id
    mine, champ = league["mine"].id, league["champ"].id
    # The derby: my Will Wilson beats Ray Hudgins in the final.
    for pid, team, homers, won in (
        (p["era"], mine, 9, True),
        (p["avg"], champ, 7, False),
    ):
        db_conn.execute(
            """INSERT INTO hr_derby_results (season_id, round, match, player_id,
                   team_id, seed, homers, longest, won)
               VALUES (%s, 1, 1, %s, %s, 1, %s, 455, %s)""",
            (past, pid, team, homers, won),
        )
    # Hal Homer goes into the Hall in my cap.
    db_conn.execute(
        "INSERT INTO hall_elections (season_id, league_id, year, ballots)"
        " VALUES (%s, %s, 2025, 10)",
        (past, league["league"].id),
    )
    db_conn.execute(
        """INSERT INTO hall_ballot (season_id, player_id, league_id, votes, share,
               outcome, team_id)
           VALUES (%s, %s, %s, 9, 0.9, 'elected', %s)""",
        (past, p["hr"], league["league"].id, mine),
    )
    ctx = _summary(db_conn, league)
    chips = {(h["what"], h["player_id"]) for h in ctx["my_highlights"]}
    assert ("All-Star", p["era"]) in chips
    assert ("HR Derby champ", p["era"]) in chips
    assert ("Hall of Fame", p["hr"]) in chips
    # Other teams' All-Stars get no chip.
    assert ("All-Star", p["avg"]) not in chips
    assert ctx["derby_champion"]["line"] == "9 HR, longest 455 ft"


def test_summary_page_shows_the_derby_champion(client, db_conn, league):
    db_conn.execute(
        """INSERT INTO hr_derby_results (season_id, round, match, player_id,
               team_id, seed, homers, longest, won)
           VALUES (%s, 1, 1, %s, %s, 1, 5, 430, TRUE)""",
        (league["past"].id, league["players"]["hr"], league["best"].id),
    )
    lid, sid = league["league"].id, league["past"].id
    r = client.get(f"/leagues/{lid}/season-summary?season_id={sid}")
    assert "Home Run Derby Champion" in r.text and 'id="all-stars"' in r.text
