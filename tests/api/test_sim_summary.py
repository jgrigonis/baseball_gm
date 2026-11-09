# tests/api/test_sim_summary.py
"""The GM's team on the line under the sim buttons (src/api/services/sim_summary.py)."""

from types import SimpleNamespace

from src.api.services import sim_summary
from src.league.divisions import Conference, Division


def _teams(*records):
    """("a", 10, 5), ... best first."""
    return [{"team_id": t, "wins": w, "losses": lo} for t, w, lo in records]


def _no_divs():
    return []


class TestStanding:
    def test_leader_by_games(self):
        teams = _teams(("a", 10, 5), ("b", 8, 6), ("c", 5, 10))
        confs = [Conference("L", [Division("East", ["a", "b", "c"])])]

        got = sim_summary.standing(teams, "a", confs)

        assert got == {"wins": 10, "losses": 5, "standing": "1st in East by 1.5"}

    def test_behind_in_division(self):
        teams = _teams(("a", 10, 5), ("x", 9, 6), ("b", 8, 7), ("c", 5, 10))
        confs = [
            Conference(
                "L", [Division("East", ["a", "b"]), Division("West", ["x", "c"])]
            )
        ]

        assert (
            sim_summary.standing(teams, "b", confs)["standing"] == "2nd in East, 2 back"
        )

    def test_tied_for_first(self):
        teams = _teams(("a", 10, 5), ("b", 10, 5))

        assert (
            sim_summary.standing(teams, "b", _no_divs())["standing"] == "Tied for 1st"
        )
        assert (
            sim_summary.standing(teams, "a", _no_divs())["standing"] == "Tied for 1st"
        )

    def test_without_divisions(self):
        teams = _teams(("a", 10, 5), ("b", 9, 6), ("c", 8, 7))

        assert sim_summary.standing(teams, "c", _no_divs())["standing"] == "3rd, 2 back"


def _league(n=12):
    """n teams, no divisions, team i has 100 - 4i wins of 150 played."""
    return _teams(*[(f"t{i}", 100 - 4 * i, 50 + 4 * i) for i in range(n)])


class TestPlayoffRace:
    def test_nothing_early(self):
        teams = _league()
        left = {t["team_id"]: 60 for t in teams}

        assert sim_summary.playoff_race(teams, "t3", [], left) is None

    def test_clinched(self):
        teams = _league()
        left = {t["team_id"]: 5 for t in teams}

        assert (
            sim_summary.playoff_race(teams, "t0", [], left) == "Clinched a playoff spot"
        )

    def test_eliminated(self):
        teams = _league()
        left = {t["team_id"]: 5 for t in teams}

        assert sim_summary.playoff_race(teams, "t11", [], left) == "Eliminated"

    def test_in_a_spot_late(self):
        # t7 (8th) leads t8 by 4 with 10 to play: not clinched, in by 4.
        teams = _league()
        left = {t["team_id"]: 10 for t in teams}

        assert (
            sim_summary.playoff_race(teams, "t7", [], left) == "In a playoff spot by 4"
        )

    def test_back_of_a_spot_late(self):
        teams = _league()
        left = {t["team_id"]: 10 for t in teams}

        assert (
            sim_summary.playoff_race(teams, "t8", [], left)
            == "4 back of a playoff spot"
        )

    def test_clinched_the_division(self):
        # Two leagues of two divisions; "a" leads its division by more than
        # the games left.
        ids = [f"t{i}" for i in range(16)]
        teams = _teams(*[(t, 100 - 2 * i, 50 + 2 * i) for i, t in enumerate(ids)])
        confs = [
            Conference(
                "A", [Division("East", ids[0:8:2]), Division("West", ids[1:8:2])]
            ),
            Conference(
                "P", [Division("North", ids[8:16:2]), Division("South", ids[9:16:2])]
            ),
        ]
        left = {t: 2 for t in ids}

        assert sim_summary.playoff_race(teams, "t0", confs, left) == "Clinched the East"

    def test_ties_go_against_the_team_when_clinching(self):
        # t7 leads t8 by 4 with 4 to play: they could finish level.
        teams = _league()
        left = {t["team_id"]: 4 for t in teams}

        assert (
            sim_summary.playoff_race(teams, "t7", [], left) == "In a playoff spot by 4"
        )


class TestMyDay:
    def _setup(self, factory, db_conn):
        league = factory.league(state="season")
        season = factory.season()
        factory.league_season(league, season)
        me, them = factory.team("Mine", "Ones"), factory.team("Other", "Ones")
        for t in (me, them):
            factory.league_season_team(league, season, t)
        game = factory.game_with_teams(
            season=season, home=me, away=them, game_date="2025-04-01"
        )
        for team, runs, win in ((me, 5, 1), (them, 3, 0)):
            db_conn.execute(
                "INSERT INTO team_game_stats (game_id, team_id, runs, win, loss)"
                " VALUES (%s, %s, %s, %s, %s)",
                (game.id, team.id, runs, win, 1 - win),
            )
        return SimpleNamespace(league=league, season=season, me=me, them=them)

    def test_the_days_result_record_and_standing(self, factory, db_conn):
        s = self._setup(factory, db_conn)

        got = sim_summary.my_day(
            db_conn, s.league.id, s.season.id, s.me.id, "2025-04-01"
        )

        assert got["day_wins"] == 1 and got["day_losses"] == 0
        assert (got["wins"], got["losses"]) == (1, 0)
        assert got["standing"] == "1st by 1"
        assert got["games_left"] == 0

    def test_the_days_biggest_story_about_the_team(self, factory, db_conn):
        s = self._setup(factory, db_conn)
        from src.db.repositories.news_repo import NewsRepository

        news = NewsRepository(db_conn)
        news.add(s.league.id, s.season.id, "2025-04-01", "big_game", "k1",
                 "\u27e6p:x|Ruiz\u27e7 gets 5 hits", weight=1, team_ids=[s.me.id, s.them.id])  # fmt: skip
        news.add(s.league.id, s.season.id, "2025-04-01", "no_hitter", "k2",
                 "Lee throws a no-hitter", weight=3, team_ids=[s.them.id, s.me.id])  # fmt: skip

        got = sim_summary.my_day(
            db_conn, s.league.id, s.season.id, s.me.id, "2025-04-01"
        )

        # The no-hitter was thrown against the team, so it isn't its story.
        assert got["story"] == {"headline": "Ruiz gets 5 hits", "weight": 1}

    def test_no_team(self, factory, db_conn):
        s = self._setup(factory, db_conn)

        assert (
            sim_summary.my_day(db_conn, s.league.id, s.season.id, None, "2025-04-01")
            == {}
        )


class TestClinchStatus:
    def test_marks_for_the_standings(self):
        teams = _league()
        left = {t["team_id"]: 5 for t in teams}

        got = {
            t["team_id"]: sim_summary.clinch_status(teams, t["team_id"], [], left)
            for t in teams
        }

        assert got["t0"] == "spot"
        assert got["t11"] == "out"
        assert got["t7"] is None
