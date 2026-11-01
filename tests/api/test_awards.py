# tests/api/test_awards.py
"""Season awards against the database (src/api/services/awards.py): decided
once the regular season is over, series MVPs as each series is won, and
shown in the news, the season summary, the player panel and GM badges."""

import uuid

import pytest

from src.api.services import awards, badges, news
from src.api.services.news.names import plain
from src.api.view_models.player_detail import player_awards
from src.api.view_models.seasons import history_context, season_awards
from src.db.repositories.news_repo import NewsRepository


def _id():
    return str(uuid.uuid4())


@pytest.fixture
def lg(db_conn, factory):
    """A 2026 league, its second season (2025 before it): Josh runs the
    Captains, an AI GM the Samurai. No divisions, so one of each award."""
    league = factory.league(state="season")
    prev = factory.season(year=2025)
    season = factory.season(year=2026)
    mine = factory.team(city="Amsterdam", mascot="Captains")
    theirs = factory.team(city="Tokyo", mascot="Samurai")
    for s in (prev, season):
        factory.league_season(league, s)
        for t in (mine, theirs):
            factory.league_season_team(league, s, t)
    gm = factory.gm(team=mine, league=league, is_ai=False)
    ai = factory.gm(team=theirs, league=league, is_ai=True)
    db_conn.execute("UPDATE gms SET display_name = 'Josh' WHERE id = %s", (gm.id,))
    news.update_league(db_conn, league.id)
    return {"league": league, "prev": prev, "season": season, "mine": mine,
            "theirs": theirs, "gm": gm, "ai": ai}  # fmt: skip


def _game(db, season, day, winner, loser, series_id=None, completed=1):
    gid = _id()
    db.execute(
        """INSERT INTO games (id, game_date, season_id, series_id, home_team_id,
               away_team_id, home_score, away_score, winner_id, completed)
           VALUES (%s, %s, %s, %s, %s, %s, 5, 3, %s, %s)""",
        (gid, day, season.id, series_id, winner.id, loser.id,
         winner.id if completed else None, completed),
    )  # fmt: skip
    if completed:
        for team, won in ((winner, 1), (loser, 0)):
            db.execute(
                "INSERT INTO team_game_stats (game_id, team_id, runs, win, loss)"
                " VALUES (%s, %s, %s, %s, %s)",
                (gid, team.id, 5 if won else 3, won, 1 - won),
            )
    return gid


def _player(db, lg, team, first, last, position="RF"):
    pid = _id()
    db.execute(
        "INSERT INTO players (id, first_name, last_name, bats, throws, position,"
        " league_id) VALUES (%s, %s, %s, 'R', 'R', %s, %s)",
        (pid, first, last, position, lg["league"].id),
    )
    db.execute(
        "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)", (team.id, pid)
    )
    return pid


def _stats(db, pid, season, team, **stats):
    cols = ", ".join(stats)
    db.execute(
        f"""INSERT INTO player_season_stats (player_id, season_id, team_id,
                is_postseason, {cols})
            VALUES (%s, %s, %s, FALSE, {", ".join(["%s"] * len(stats))})""",
        (pid, season.id, team.id, *stats.values()),
    )


HITTER = dict(bat_games_played=6, bat_games_started=6, bat_ab=24, bat_hits=6,
              bat_home_runs=1, bat_rbi=3, bat_walks=2)  # fmt: skip
STAR = dict(bat_games_played=6, bat_games_started=6, bat_ab=24, bat_hits=12,
            bat_doubles=3, bat_home_runs=4, bat_rbi=10, bat_walks=4)  # fmt: skip
ACE = dict(pitch_games_played=2, pitch_games_started=2, pitch_outs=54,
           pitch_earned_runs=2, pitch_strike_outs=20, pitch_wins=2)  # fmt: skip
ARM = dict(pitch_games_played=2, pitch_games_started=2, pitch_outs=36,
           pitch_earned_runs=10, pitch_strike_outs=6, pitch_losses=2)  # fmt: skip


@pytest.fixture
def played(db_conn, lg):
    """A six-game regular season the Captains won 5-1, with a slugger and
    an ace on the Captains and ordinary players on the Samurai. The ace is
    a rookie; everyone else played in 2025."""
    db, s, mine, theirs = db_conn, lg["season"], lg["mine"], lg["theirs"]
    for day in range(1, 6):
        _game(db, s, f"2026-04-0{day}", mine, theirs)
    _game(db, s, "2026-04-06", theirs, mine)
    star = _player(db, lg, mine, "Ruben", "Ruiz")
    ace = _player(db, lg, mine, "Kenji", "Kato", position="P")
    _stats(db, star, s, mine, **STAR)
    _stats(db, ace, s, mine, **ACE)
    others = []
    for i, team in enumerate((mine, theirs, theirs)):
        pid = _player(db, lg, team, "Joe", f"Hitter{i}")
        _stats(db, pid, s, team, **HITTER)
        others.append(pid)
    arm = _player(db, lg, theirs, "Sam", "Arm", position="P")
    _stats(db, arm, s, theirs, **ARM)
    for pid, team in ((star, mine), (arm, theirs), *((p, theirs) for p in others)):
        _stats(db, pid, lg["prev"], team, bat_ab=400, pitch_outs=400)
    return {"star": star, "ace": ace, "arm": arm}


def _awards(db, season):
    return {
        r["award"]: r
        for r in db.execute(
            "SELECT * FROM season_awards WHERE season_id = %s", (season.id,)
        ).fetchall()
    }


class TestDeciding:
    def test_nothing_until_the_regular_season_is_over(self, db_conn, lg, played):
        _game(
            db_conn, lg["season"], "2026-04-07", lg["mine"], lg["theirs"], completed=0
        )
        awards.decide_league(db_conn, lg["league"].id)
        assert _awards(db_conn, lg["season"]) == {}

    def test_regular_season_awards(self, db_conn, lg, played):
        awards.decide_league(db_conn, lg["league"].id)
        won = _awards(db_conn, lg["season"])
        assert won["mvp"]["player_id"] == played["star"]
        assert won["mvp"]["scope"] == ""
        assert won["mvp"]["line"] == ".500, 4 HR, 10 RBI"
        assert won["mvp"]["decided_on"] == "2026-04-06"
        assert won["cy_young"]["player_id"] == played["ace"]
        assert won["roy"]["player_id"] == played["ace"]
        assert won["hank_aaron"]["player_id"] == played["star"]
        assert won["batting_champ"]["player_id"] == played["star"]
        assert won["pitching_champ"]["player_id"] == played["ace"]
        assert won["gm_of_year"]["gm_id"] == lg["gm"].id
        assert won["gm_of_year"]["line"] == "5-1"

    def test_decided_once(self, db_conn, lg, played):
        awards.decide_league(db_conn, lg["league"].id)
        db_conn.execute(
            "UPDATE player_season_stats SET bat_hits = 0 WHERE player_id = %s",
            (played["star"],),
        )
        awards.decide_league(db_conn, lg["league"].id)
        assert _awards(db_conn, lg["season"])["mvp"]["player_id"] == played["star"]

    def test_a_past_season_gets_awards_but_no_gm_of_the_year(self, db_conn, lg, played):
        _game(db_conn, lg["prev"], "2025-04-01", lg["theirs"], lg["mine"])
        awards.decide_league(db_conn, lg["league"].id)
        past = _awards(db_conn, lg["prev"])
        assert "mvp" in past
        assert "gm_of_year" not in past
        # The league's first season: everyone's a rookie, so no Rookie of the Year.
        assert "roy" not in past
        done = db_conn.execute(
            "SELECT awards_done FROM league_seasons WHERE season_id = %s",
            (lg["prev"].id,),
        ).fetchone()
        assert done["awards_done"]

    def test_finals_mvp(self, db_conn, lg, played):
        sid = _id()
        db_conn.execute(
            "INSERT INTO series (id, season_id, name) VALUES (%s, %s, 'Finals')",
            (sid, lg["season"].id),
        )
        gids = [
            _game(db_conn, lg["season"], f"2026-10-0{d}", lg["mine"], lg["theirs"], sid)
            for d in range(1, 4)
        ]
        awards.decide_league(db_conn, lg["league"].id)
        assert "finals_mvp" not in _awards(db_conn, lg["season"])  # 3-0, not over

        gids.append(
            _game(db_conn, lg["season"], "2026-10-05", lg["mine"], lg["theirs"], sid)
        )
        for gid in gids:
            db_conn.execute(
                """INSERT INTO player_game_stats (game_id, player_id, team_id,
                       opponent_team_id, bat_ab, bat_hits, bat_home_runs, bat_rbi)
                   VALUES (%s, %s, %s, %s, 4, 2, 1, 2)""",
                (gid, played["star"], lg["mine"].id, lg["theirs"].id),
            )
        awards.decide_league(db_conn, lg["league"].id)
        mvp = _awards(db_conn, lg["season"])["finals_mvp"]
        assert mvp["player_id"] == played["star"]
        assert mvp["line"] == "8-for-16, 4 HR, 8 RBI"
        assert mvp["decided_on"] == "2026-10-05"


class TestShown:
    def test_news(self, db_conn, lg, played):
        awards.decide_league(db_conn, lg["league"].id)
        news.update_league(db_conn, lg["league"].id)
        stories = {
            plain(r["headline"]): plain(r["body"])
            for r in NewsRepository(db_conn).feed(lg["league"].id, limit=100)
            if r["kind"] == "season_award"
        }
        assert stories["Ruben Ruiz is the 2026 MVP"] == (
            "Ruben Ruiz of the Amsterdam Captains wins the MVP (.500, 4 HR, 10 RBI)."
        )
        assert "Kenji Kato is the 2026 Cy Young" in stories
        assert "GM Josh is the 2026 GM of the Year" in stories
        assert "Batting Champion: Ruben Ruiz" in stories["The rest of the 2026 awards"]

    def test_season_summary_and_history(self, db_conn, lg, played):
        awards.decide_league(db_conn, lg["league"].id)
        shown = season_awards(db_conn, lg["season"].id, lg["mine"].id)
        assert [a["name"] for a in shown][:3] == [
            "MVP",
            "Cy Young",
            "Rookie of the Year",
        ]
        mvp = shown[0]["winners"][0]
        assert mvp["name"] == "Ruben Ruiz"
        assert mvp["team"] == "Amsterdam Captains"
        assert mvp["is_mine"]
        gm = next(a for a in shown if a["key"] == "gm_of_year")["winners"][0]
        assert gm["name"] == "GM Josh"
        rows = history_context(db_conn, lg["league"].id, lg["mine"].id)["history_rows"]
        row = next(r for r in rows if r["season_id"] == lg["season"].id)
        assert row["has_awards"]
        assert [m["name"] for m in row["mvps"]] == ["Ruben Ruiz"]

    def test_player_panel(self, db_conn, lg, played):
        awards.decide_league(db_conn, lg["league"].id)
        mine = player_awards(db_conn, played["ace"])
        assert [(a["name"], a["years"]) for a in mine] == [
            ("Cy Young", [2026]), ("Rookie of the Year", [2026]),
            ("Pitching Champion", [2026]),
        ]  # fmt: skip

    def test_gm_of_the_year_badge(self, db_conn, lg, played):
        uid = _id()
        db_conn.execute(
            "INSERT INTO users (id, session_token, display_name, username)"
            " VALUES (%s, %s, 'Josh', %s)",
            (uid, uid, f"josh-{uid[:8]}"),
        )
        db_conn.execute("UPDATE gms SET user_id = %s WHERE id = %s", (uid, lg["gm"].id))
        assert not badges.check_all(db_conn, uid)["gm_of_year"].earned
        awards.decide_league(db_conn, lg["league"].id)
        check = badges.check_all(db_conn, uid)["gm_of_year"]
        assert check.earned
        assert check.detail == "Test League · 2026"
