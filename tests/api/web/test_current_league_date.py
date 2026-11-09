"""_current_league_date between seasons.

In the offseason the newest season is still the one just played. "Today"
must be next spring, not that season's opening day: otherwise a player hurt
in September shows months of IL time left all winter (the panel badge read
"IL · Back spasms · 177d" for a 2-day injury).
"""

import pytest

from src.web import utils


class _FakeSeasons:
    def __init__(self, db):
        self.db = db

    def get_year(self, season_id):
        return {"year": 2027}

    def has_a_completed_game(self, season_id):
        return self.db["played"]


@pytest.fixture
def fake_seasons(monkeypatch):
    monkeypatch.setattr(utils, "SeasonRepository", _FakeSeasons)


@pytest.mark.parametrize("state", ["offseason", "draft"])
def test_after_a_season_today_is_next_spring(fake_seasons, state):
    assert utils._current_league_date({"played": True}, "s1", state) == "2028-03-22"


@pytest.mark.parametrize("state", ["offseason", "draft"])
def test_before_any_games_today_is_this_spring(fake_seasons, state):
    assert utils._current_league_date({"played": False}, "s1", state) == "2027-03-22"
