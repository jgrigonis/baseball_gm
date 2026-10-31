# tests/league/test_backstory.py
"""
League backstory (src/league/backstory/, plans/league-backstory.md).

The generated seasons have to look like seasons the engine plays. The
league-wide checks below fail when they drift, which is the sign to re-run
scripts/calibrate_backstory.py (after an engine change, say).
"""

import random
import statistics
import uuid

import numpy as np
import pytest

from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.series_repo import SeriesRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.league.backstory import careers, season
from src.league.backstory.calibration import PARAMS
from src.league.backstory.rewind import rewind
from src.league.backstory.service import create_backstory
from src.league.league_constants import LEAGUE_START_YEAR
from src.league.schedule import ScheduleGenerator
from src.team.team_factory import TeamFactory

# A new league's first season; its backstory is the years just before.
START = LEAGUE_START_YEAR


def _league_players(n_teams: int, seed: int = 7) -> tuple[list[str], list[dict]]:
    """Rosters made the way a league start makes them, as create_backstory
    loads them."""
    rng = random.Random(seed)
    tf = TeamFactory(rng=rng)
    team_ids, players = [], []
    for i in range(n_teams):
        tid = f"t{i:02d}"
        team_ids.append(tid)
        team = tf.generate_team(city=f"City{i}", mascot="Team", size=26)
        for p in team.players:
            players.append(
                {
                    "id": p.id,
                    "team_id": tid,
                    "first_name": p.first_name,
                    "last_name": p.last_name,
                    "bats": p.bats,
                    "throws": p.throws,
                    "position": p.position,
                    "age": p.skills.age,
                    "skills": {k: float(v) for k, v in p.skills.as_dict().items()},
                    "caps": p.caps,
                    "record": p,
                }
            )
    return team_ids, players


# ── Rewinding ratings ─────────────────────────────────────────────────────────


def test_a_young_player_was_less_developed_a_few_years_ago():
    skills = {"contact": 60.0, "power": 60.0, "eye": 60.0, "speed": 60.0}
    back = rewind(skills, age=25, years=4, rng=random.Random(1))
    assert len(back) == 4
    assert back[-1]["contact"] < skills["contact"] - 3
    assert back[-1]["power"] < skills["power"] - 3


def test_an_old_player_was_better_a_few_years_ago():
    skills = {"speed": 50.0, "power": 50.0}
    back = rewind(skills, age=37, years=4, rng=random.Random(1))
    assert back[-1]["speed"] > skills["speed"] + 3


def test_rewinding_is_repeatable_for_a_seed():
    skills = {"contact": 55.0}
    assert rewind(skills, 28, 3, rng=random.Random(5)) == rewind(
        skills, 28, 3, rng=random.Random(5)
    )


# ── Careers ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def league():
    team_ids, players = _league_players(30)
    rng = random.Random(3)
    cs = careers.current_careers(players, START, 5, team_ids, rng)
    retirees = careers.add_retirees(cs, START, 5, team_ids, rng)
    return team_ids, players, cs, retirees


def test_nobody_played_before_21(league):
    _, _, cs, _ = league
    for c in cs:
        for year in c.team_by_year:
            assert c.age_in(year, START) >= careers.FIRST_MAJORS_AGE


def test_careers_have_no_gaps_going_back(league):
    _, _, cs, _ = league
    for c in cs:
        years = sorted(c.team_by_year)
        assert years == list(range(years[0], years[-1] + 1)) if years else True
        assert set(c.skills_by_year) == set(c.team_by_year)


def test_every_past_team_has_a_full_roster(league):
    team_ids, _, cs, _ = league
    for year in range(START - 5, START):
        for tid in team_ids:
            roster = [c for c in cs if c.team_by_year.get(year) == tid]
            hitters = [c for c in roster if c.position not in ("sp", "rp")]
            pitchers = [c for c in roster if c.position in ("sp", "rp")]
            assert len(hitters) >= careers.HITTERS
            assert len(pitchers) >= careers.PITCHERS
            assert any(c.position == "c" for c in hitters)
            assert sum(c.position == "sp" for c in pitchers) >= careers.MIN_STARTERS


def test_retirees_retire_after_a_past_season_at_a_veterans_age(league):
    _, _, _, retirees = league
    assert retirees
    for r in retirees:
        assert START - 5 <= r.retired_after <= START - 1
        assert careers.RETIRE_AGES[0] <= r.age_now <= careers.RETIRE_AGES[1]
        assert max(r.team_by_year) == r.retired_after


def test_most_players_stayed_with_their_team(league):
    _, players, cs, _ = league
    team_now = {p["id"]: p["team_id"] for p in players}
    last_year = [
        c for c in cs if START - 1 in c.team_by_year and c.player_id in team_now
    ]
    same = sum(c.team_by_year[START - 1] == team_now[c.player_id] for c in last_year)
    assert 0.8 < same / len(last_year) < 0.95


# ── Games ─────────────────────────────────────────────────────────────────────


def test_a_game_always_has_a_winner_and_nine_innings():
    rng = np.random.default_rng(1)
    for _ in range(300):
        away, home = season.play_game(rng, 4.0, 4.0)
        assert sum(away) != sum(home)
        assert len(away) == len(home) >= 9


def test_the_home_team_skips_the_bottom_of_the_ninth_when_ahead():
    rng = np.random.default_rng(2)
    for _ in range(300):
        away, home = season.play_game(rng, 4.0, 4.0)
        if len(home) == 9 and sum(home[:8]) > sum(away):
            assert home[8] == 0


def test_the_playoffs_crown_a_champion_with_four_finals_wins():
    rng = np.random.default_rng(3)
    seeds = [f"t{i}" for i in range(8)]
    s = {t: (1.0, 1.0) for t in seeds}
    import datetime

    series, games = season.play_playoffs(
        rng, s, "S", seeds, datetime.date(START - 1, 10, 1)
    )
    assert [n for _, n in series][-1] == "Finals"
    finals = [g for g in games if g.series_id == "S_Finals"]
    wins = {}
    for g in finals:
        wins[g.winner_id] = wins.get(g.winner_id, 0) + 1
    assert max(wins.values()) == 4


# ── A whole league season looks like the engine's ────────────────────────────


@pytest.fixture(scope="module")
def played(league):
    team_ids, _, cs, _ = league
    rng = np.random.default_rng(11)
    year = START - 1
    teams = []
    for tid in team_ids:
        members = [
            season.Member(
                player_id=c.player_id,
                position=c.position,
                throws=c.throws,
                age=c.age_in(year, START),
                skills=c.skills_by_year[year],
            )
            for c in cs
            if c.team_by_year.get(year) == tid
        ]
        teams.append(season.team_season(rng, tid, members))
    strength = season.strengths(rng, teams)
    schedule = ScheduleGenerator(rng=random.Random(4)).create_schedule(
        season_id="S",
        team_ids=team_ids,
        start_date=__import__("datetime").date(year, 4, 1),
        target_games=162,
    )
    games = season.play_schedule(rng, schedule, strength)
    hits = {t.team_id: sum(ln.stats["bat_hits"] for ln in t.batting) for t in teams}
    season.add_hits_and_errors(rng, games, hits)
    records = season.team_records(games)
    for t in teams:
        season.finish_lines(rng, t, records[t.team_id])
    return teams, games, records


def test_runs_per_game_match_the_engine(played):
    _, games, _ = played
    rpg = statistics.mean(g.home_score + g.away_score for g in games) / 2
    assert abs(rpg - PARAMS["runs_per_game"]) < 0.35


def test_the_spread_of_wins_matches_the_engine(played):
    _, _, records = played
    sd = statistics.pstdev(r["w"] for r in records.values())
    target = PARAMS.get("team_wins_sd", 10.5)
    assert target * 0.6 < sd < target * 1.4


def test_league_batting_average_and_power_look_real(played):
    teams, _, _ = played
    lines = [ln.stats for t in teams for ln in t.batting]
    avg = sum(s["bat_hits"] for s in lines) / sum(s["bat_ab"] for s in lines)
    assert 0.215 < avg < 0.265
    assert 25 <= max(s["bat_home_runs"] for s in lines) <= 65


def test_team_lines_add_up_to_their_games(played):
    teams, games, records = played
    for t in teams:
        r = records[t.team_id]
        assert sum(ln.stats["bat_runs"] for ln in t.batting) == r["rs"]
        assert sum(ln.stats["pitch_runs"] for ln in t.pitching) == r["ra"]
        assert sum(ln.stats["pitch_wins"] for ln in t.pitching) == r["w"]
        assert sum(ln.stats["pitch_losses"] for ln in t.pitching) == r["l"]
        game_hits = sum(
            g.home_hits if g.home_team_id == t.team_id else g.away_hits
            for g in games
            if t.team_id in (g.home_team_id, g.away_team_id)
        )
        assert game_hits == sum(ln.stats["bat_hits"] for ln in t.batting)


def test_each_team_starts_162_games(played):
    teams, _, _ = played
    for t in teams:
        assert sum(ln.stats["pitch_games_started"] for ln in t.pitching) == 162


# ── Saved to the database ─────────────────────────────────────────────────────


def _seed_league(db_conn, factory, n_teams=10, seed=7):
    league = factory.league(state="lobby", backstory_years=3)
    s = factory.season(year=START)
    factory.league_season(league, s)
    team_ids, players = _league_players(n_teams, seed)
    real_ids = {}
    for tid in team_ids:
        t = factory.team(city=f"City {tid}", mascot="Team")
        factory.league_season_team(league, s, t)
        real_ids[tid] = t.id
    repo, status = PlayerRepository(db_conn), PlayerStatusRepository(db_conn)
    for p in players:
        rec = p["record"]
        # Fresh ids: the same seed makes the same players in every test
        pid = uuid.uuid4().hex
        repo.insert(
            pid,
            rec.first_name,
            rec.last_name,
            rec.bats,
            rec.throws,
            rec.position,
            rec.skills,
            league.id,
        )
        status.set_status(pid, "26man")
        db_conn.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)",
            (real_ids[p["team_id"]], pid),
        )
    return league, s, list(real_ids.values())


def test_past_seasons_are_saved_with_standings_and_a_champion(db_conn, factory):
    league, s, team_ids = _seed_league(db_conn, factory)
    bs = create_backstory(db_conn, league.id, s.id, 3, random.Random(1))

    seasons = SeasonRepository(db_conn).get_seasons_for_league(league.id)
    assert [x["year"] for x in seasons] == [START, START - 1, START - 2, START - 3]
    assert [x["is_backstory"] for x in seasons] == [False, True, True, True]
    assert SeasonRepository(db_conn).get_current_id_for_league(league.id) == s.id
    assert LeagueRepository(db_conn).count_seasons(league.id) == 1

    for sid in bs.season_ids:
        wl = TeamGameRepository(db_conn).get_wl_for_league(league.id, sid)
        assert len(wl) == len(team_ids)
        assert all(r["wins"] + r["losses"] == 162 for r in wl)
        assert SeriesRepository(db_conn).get_champion(sid) is not None
    assert bs.last_season_id == bs.season_ids[-1]


def test_veterans_have_career_lines_and_all_stars(db_conn, factory):
    league, s, _ = _seed_league(db_conn, factory)
    bs = create_backstory(db_conn, league.id, s.id, 3, random.Random(2))
    lines = db_conn.execute(
        "SELECT COUNT(*) AS n FROM player_season_stats WHERE season_id = ANY(%s)",
        (bs.season_ids,),
    ).fetchone()["n"]
    assert lines > 200
    stars = db_conn.execute(
        "SELECT season_id, COUNT(*) AS n FROM all_stars WHERE season_id = ANY(%s)"
        " GROUP BY season_id",
        (bs.season_ids,),
    ).fetchall()
    assert len(stars) == 3 and all(r["n"] > 0 for r in stars)
    history = db_conn.execute(
        "SELECT COUNT(*) AS n FROM player_skills_history WHERE season_id = ANY(%s)",
        (bs.season_ids,),
    ).fetchone()["n"]
    assert history == lines


def test_retired_veterans_are_saved_as_retired(db_conn, factory):
    league, s, _ = _seed_league(db_conn, factory)
    bs = create_backstory(db_conn, league.id, s.id, 3, random.Random(3))
    assert bs.retirees > 0
    rows = db_conn.execute(
        """SELECT pr.season_id, ps.status FROM player_retirements pr
           JOIN player_status ps ON ps.player_id = pr.player_id
           WHERE pr.league_id = %s""",
        (league.id,),
    ).fetchall()
    assert len(rows) == bs.retirees
    assert {r["status"] for r in rows} == {"retired"}
    assert {r["season_id"] for r in rows} <= set(bs.season_ids)


def test_no_years_means_no_backstory(db_conn, factory):
    league, s, _ = _seed_league(db_conn, factory, n_teams=8)
    bs = create_backstory(db_conn, league.id, s.id, 0, random.Random(4))
    assert bs.last_season_id is None
    assert len(SeasonRepository(db_conn).get_seasons_for_league(league.id)) == 1


def test_history_and_the_welcome_screen_show_the_past(db_conn, factory):
    from src.api.view_models.seasons import history_context
    from src.api.view_models.welcome import history

    league, s, team_ids = _seed_league(db_conn, factory)
    bs = create_backstory(db_conn, league.id, s.id, 3, random.Random(5))
    mine = team_ids[0]

    rows = history_context(db_conn, league.id, mine)["history_rows"]
    assert [r["is_backstory"] for r in rows] == [False, True, True, True]
    assert all(r["champion"] for r in rows[1:])
    assert all(r["my_w"] + r["my_l"] == 162 for r in rows[1:])

    h = history(db_conn, league.id, mine, s.id)
    assert h["last"]["year"] == START - 1
    assert h["last"]["w"] + h["last"]["l"] == 162
    champ = SeriesRepository(db_conn).get_champion(bs.last_season_id)
    assert h["champion"]["team_id"] == champ["team_id"]
    assert h["seasons"] == 3
    assert 0 <= h["titles"] <= h["playoffs"] <= 3


def test_a_league_without_a_past_has_no_history_card(db_conn, factory):
    from src.api.view_models.welcome import history

    league, s, team_ids = _seed_league(db_conn, factory, n_teams=8)
    assert history(db_conn, league.id, team_ids[0], s.id) is None
