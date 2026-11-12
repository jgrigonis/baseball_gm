# tests/api/web/test_league_side_order.py
"""While the playoffs are on, the sidebar's Playoffs link sits right above
Schedule; the rest of the year it's last in the League group."""

import re

import pytest

from src.web.utils import templates

TABS = ["headlines", "schedule", "standings", "power", "allstar", "playoffs"]


def _league_links(state):
    html = templates.env.get_template("dashboard/partials/_league_side.html").render(
        visible_tabs=TABS,
        league_id="x",
        league_state=state,
        active_tab="standings",
    )
    return re.findall(r'class="tab-link [^"]*"\s+hx-get="/leagues/x/([\w-]+)"', html)


def test_playoffs_above_schedule_during_playoffs():
    assert _league_links("playoffs") == [
        "headlines",
        "playoffs",
        "schedule",
        "standings",
        "power",
        "allstar",
    ]


@pytest.mark.parametrize("state", ["season", "offseason"])
def test_playoffs_last_otherwise(state):
    assert _league_links(state) == TABS
