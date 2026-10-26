# tests/api/test_league_end.py
"""A league runs for its chosen number of seasons. Once the last season's
playoffs are over the league is complete: read-only, with its history and
records still viewable."""

import importlib
import pkgutil

import pytest
from fastapi import HTTPException

from src.api.dependencies import require_active_league
from src.api.services.sim_playoff import end_playoffs
from src.db.repositories.league_repo import LeagueRepository
from src.web.utils import _compute_visible_tabs


def _league(db, factory, num_seasons, seasons_played):
    league = factory.league(state="playoffs")
    db.execute(
        "UPDATE leagues SET num_seasons = %s WHERE id = %s", (num_seasons, league.id)
    )
    season = None
    for i in range(seasons_played):
        season = factory.season(year=2025 + i)
        factory.league_season(league, season)
    return LeagueRepository(db).get_by_id(league.id), season


class TestEndPlayoffs:
    def test_counts_the_leagues_seasons(self, db_conn, factory):
        league, _ = _league(db_conn, factory, num_seasons=10, seasons_played=3)
        assert LeagueRepository(db_conn).count_seasons(league["id"]) == 3

    def test_more_seasons_to_go_means_offseason(self, db_conn, factory):
        league, season = _league(db_conn, factory, num_seasons=3, seasons_played=2)
        end_playoffs(db_conn, league, season.id)
        assert LeagueRepository(db_conn).get_state(league["id"]) == "offseason"

    def test_last_season_completes_the_league(self, db_conn, factory):
        league, season = _league(db_conn, factory, num_seasons=3, seasons_played=3)
        end_playoffs(db_conn, league, season.id)
        assert LeagueRepository(db_conn).get_state(league["id"]) == "complete"

    def test_one_season_league_ends_after_its_first(self, db_conn, factory):
        league, season = _league(db_conn, factory, num_seasons=1, seasons_played=1)
        end_playoffs(db_conn, league, season.id)
        assert LeagueRepository(db_conn).get_state(league["id"]) == "complete"


class TestCompleteLeagueIsReadOnly:
    def test_complete_league_rejects_changes(self, db_conn, factory):
        league = factory.league(state="complete")
        with pytest.raises(HTTPException) as e:
            require_active_league(league.id, db_conn)
        assert e.value.status_code == 409

    @pytest.mark.parametrize("state", ["lobby", "draft", "season", "offseason"])
    def test_other_states_allow_changes(self, db_conn, factory, state):
        league = factory.league(state=state)
        require_active_league(league.id, db_conn)  # no error

    def test_history_tabs_stay_visible(self):
        tabs = _compute_visible_tabs("complete", draft_complete=True)
        for tab in ("standings", "leaders", "stats", "schedule", "playoffs"):
            assert tab in tabs

    def test_every_league_changing_route_checks(self):
        import src.api.routers as routers

        routes = [
            route
            for info in pkgutil.iter_modules(routers.__path__)
            for route in importlib.import_module(
                f"{routers.__name__}.{info.name}"
            ).router.routes
        ]
        # Leaving stays open so GMs can clear a finished league off their
        # list; starting and joining need the lobby anyway.
        exempt = {
            "/leagues/{league_id}/leave",
            "/leagues/{league_id}/start",
            "/leagues/{league_id}/join",
        }

        def calls(dependant):
            for d in dependant.dependencies:
                yield d.call
                yield from calls(d)

        unchecked = [
            route.path
            for route in routes
            if "{league_id}" in route.path
            and route.methods & {"POST", "PUT", "PATCH", "DELETE"}
            and route.path not in exempt
            # Admins can still tidy up a finished league.
            and not route.path.startswith("/admin/")
            and require_active_league not in set(calls(route.dependant))
        ]
        assert len(routes) > 15
        assert unchecked == []
