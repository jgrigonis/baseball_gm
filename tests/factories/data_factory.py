# tests/factories/data_factory.py

import uuid
from types import SimpleNamespace

from src.league.league_modes import get_mode


class TestDataFactory:
    def __init__(self, db):
        self.db = db
        self._league = None  # last created league, for gm() default

    def _id(self):
        return str(uuid.uuid4())

    def league(self, state="draft", mode="blitz", injuries_enabled=None):
        league_id = self._id()
        if injuries_enabled is None:
            injuries_enabled = get_mode(mode).injuries_default
        self.db.execute(
            "INSERT INTO leagues (id, name, state, mode, injuries_enabled)"
            " VALUES (%s, %s, %s, %s, %s)",
            (league_id, "Test League", state, mode, injuries_enabled),
        )
        obj = SimpleNamespace(id=league_id)
        self._league = obj
        return obj

    def season(self, year=2025):
        season_id = self._id()
        self.db.execute(
            "INSERT INTO seasons (id, year, name) VALUES (%s, %s, %s)",
            (season_id, year, f"Season {year}"),
        )
        return SimpleNamespace(id=season_id, year=year)

    def league_season(self, league, season):
        self.db.execute(
            "INSERT INTO league_seasons (league_id, season_id) VALUES (%s, %s)"
            " ON CONFLICT DO NOTHING",
            (league.id, season.id),
        )

    def draft(self, league=None, season=None, **kwargs):
        league = league or self.league()
        season = season or self.season()
        self.league_season(league, season)
        draft_id = self._id()
        fmt = kwargs.get("fmt", "preference")
        state = kwargs.get("state", "pending")
        self.db.execute(
            "INSERT INTO drafts (id, league_id, season_id, format, state)"
            " VALUES (%s, %s, %s, %s, %s)",
            (draft_id, league.id, season.id, fmt, state),
        )
        return SimpleNamespace(
            id=draft_id,
            league_id=league.id,
            season_id=season.id,
        )

    def team(self, city="City", mascot="Team"):
        team_id = self._id()
        self.db.execute(
            "INSERT INTO teams (id, city, mascot) VALUES (%s, %s, %s)"
            " ON CONFLICT DO NOTHING",
            (team_id, city, mascot),
        )
        return SimpleNamespace(id=team_id)

    def league_season_team(self, league, season, team):
        self.db.execute(
            "INSERT INTO league_season_teams (league_id, season_id, team_id) VALUES (%s, %s, %s)",
            (league.id, season.id, team.id),
        )

    def gm(self, team=None, league=None, **kwargs):
        gm_id = self._id()
        team = team or self.team()
        league = league or self._league or self.league()
        is_ai = kwargs.get("is_ai", True)
        self.db.execute(
            "INSERT INTO gms (id, league_id, team_id, display_name, is_ai)"
            " VALUES (%s, %s, %s, %s, %s)",
            (gm_id, league.id, team.id, "GM", is_ai),
        )
        self.db.execute("INSERT INTO gm_profiles (gm_id) VALUES (%s)", (gm_id,))
        return SimpleNamespace(id=gm_id)

    def draft_order(self, draft, teams):
        """Assign pick positions to a list of team objects for a given draft."""
        for i, team in enumerate(teams, 1):
            self.db.execute(
                "INSERT INTO draft_order (draft_id, team_id, pick_position)"
                " VALUES (%s, %s, %s)",
                (draft.id, team.id, i),
            )

    def prospect(self, league_id, player_id=None, stamina=50, strikes=50):
        """Insert a full prospect (player + skills + status)."""
        player_id = player_id or self._id()
        self.db.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws, position, league_id)"
            " VALUES (%s, 'Test', 'Player', 'R', 'R', 'of', %s)"
            " ON CONFLICT DO NOTHING",
            (player_id, league_id),
        )
        self.db.execute(
            """INSERT INTO player_skills
               (player_id, age, durability, strikes, stamina, recovery, accuracy, clutch,
                speed, power, arm, eye, contact, base_running,
                bunting, catching, infield, outfield, ground_balls)
               VALUES (%s,20,80,%s,%s,50,50,50,50,50,50,50,50,50,50,50,50,50,50)
               ON CONFLICT DO NOTHING""",
            (player_id, strikes, stamina),
        )
        self.db.execute(
            "INSERT INTO player_status (player_id, status, since)"
            " VALUES (%s, 'prospect', '2025-01-01')"
            " ON CONFLICT DO NOTHING",
            (player_id,),
        )
        return SimpleNamespace(id=player_id)

    def rated_player(
        self,
        team,
        league,
        level=50,
        status="40man",
        pitcher=False,
        age=27,
        name="Player",
    ):
        """A player on a team with every skill at `level`, so each of his
        ratings comes out at about `level`."""
        player_id = self._id()
        self.db.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws, position, league_id)"
            " VALUES (%s, 'Test', %s, 'R', 'R', %s, %s)",
            (player_id, name, "sp" if pitcher else "1b", league.id),
        )
        self.db.execute(
            """INSERT INTO player_skills
               (player_id, age, durability, strikes, stamina, recovery, accuracy, clutch,
                speed, power, arm, eye, contact, base_running,
                bunting, catching, infield, outfield, ground_balls)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s)""",
            (player_id, age, *([level] * 17)),
        )
        self.db.execute(
            "INSERT INTO player_status (player_id, status, since)"
            " VALUES (%s, %s, '2025-01-01')",
            (player_id, status),
        )
        self.db.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)",
            (team.id, player_id),
        )
        return SimpleNamespace(id=player_id)

    def player_row(self, player_id=None):
        """Insert a bare player row (no skills/status) for FK satisfaction."""
        player_id = player_id or self._id()
        self.db.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws, position)"
            " VALUES (%s, 'Test', 'Player', 'R', 'R', 'of')"
            " ON CONFLICT DO NOTHING",
            (player_id,),
        )
        return SimpleNamespace(id=player_id)

    def game(self, season, home_team, away_team, game_date="2025-04-01"):
        game_id = self._id()

        self.db.execute(
            """INSERT INTO games
            (id, game_date, season_id, home_team_id, away_team_id,
                home_score, away_score, winner_id, innings_played, completed)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                game_id,
                game_date,
                season["id"],
                home_team["id"],
                away_team["id"],
                5,
                3,
                home_team["id"],
                9,
                1,
            ),
        )
        return SimpleNamespace(
            id=game_id,
        )
        # return {"id": game_id}

    def game_with_teams(
        self,
        *,
        season=None,
        home=None,
        away=None,
        game_date="2025-04-01",
    ):
        season = season or self.season()
        home = home or self.team(city="H", mascot="H")
        away = away or self.team(city="A", mascot="A")

        game_id = self._id()

        self.db.execute(
            """INSERT INTO games
            (id, game_date, season_id, home_team_id, away_team_id,
                home_score, away_score, winner_id, innings_played, completed)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                game_id,
                game_date,
                season.id,
                home.id,
                away.id,
                5,
                3,
                home.id,
                9,
                1,
            ),
        )
        return SimpleNamespace(
            id=game_id,
            season=season,
            home=home,
            away=away,
        )
        # return {
        #     "id": game_id,
        #     "season": season,
        #     "home": home,
        #     "away": away,
        # }
