# tests/api/web/test_playoffs_round_order.py
"""On phones the bracket shows a round only once its games exist (Round 1
always), stacked newest on top. Rounds that haven't started carry the
not-started class the phone CSS hides."""

import re

import jinja2

ENV = jinja2.Environment(loader=jinja2.FileSystemLoader("src/web/templates"))


def _team(i, pending=False):
    return {
        "team_id": str(i),
        "name": f"T{i}",
        "wins": 0,
        "is_mine": False,
        "is_human": False,
        "pending": pending,
    }


def _series(name, best_of, teams):
    return {
        "name": name,
        "label": None,
        "best_of": best_of,
        "wins_needed": {5: 3, 7: 4}[best_of],
        "teams": teams,
        "completed_games": [],
        "decided": False,
        "winner_id": None,
    }


def _render(semi_teams, final_teams):
    r1 = [_series(n, 5, [_team(1), _team(2)]) for n in ("1v8", "4v5", "2v7", "3v6")]
    bracket = [
        {"name": "Round 1", "series": r1},
        {
            "name": "Semifinals",
            "series": [
                _series("[1,8]v[4,5]", 7, semi_teams),
                _series("[2,7]v[3,6]", 7, []),
            ],
        },
        {"name": "Finals", "series": [_series("Finals", 7, final_teams)]},
    ]
    html = ENV.get_template("dashboard/partials/playoffs.html").render(
        bracket=bracket,
        champion=None,
        league_id="x",
        my_team_id="1",
        past_season=None,
        multiplayer=False,
        is_viewer=False,
    )
    return re.findall(r'class="po-round( not-started)?"', html)


def test_only_round_one_before_semis_start():
    assert _render([], []) == ["", " not-started", " not-started"]


def test_semi_with_known_winner_but_no_games_is_not_started():
    assert _render([_team(1, pending=True)], []) == ["", " not-started", " not-started"]


def test_rounds_appear_once_games_exist():
    assert _render([_team(1), _team(3)], []) == ["", "", " not-started"]
    assert _render([_team(1), _team(3)], [_team(1), _team(5)]) == ["", "", ""]
