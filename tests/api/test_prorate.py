# tests/api/test_prorate.py
"""Salaries split by days for players who change teams during the season
(src/league/prorate.py, Josh 2026-11-13)."""

import pytest

from src.api.services import free_agents, trades, waivers
from src.league import prorate
from tests.api.test_free_agents import _signed
from tests.api.test_free_agents import lg as lg  # noqa: F401  (the fixture)


def _season(lg, played, total=10):
    """A schedule of `total` regular-season games, `played` of them done
    (on top of the fixture's one unplayed game)."""
    for i in range(total - 1):
        lg.db.execute(
            """INSERT INTO games (id, game_date, season_id, home_team_id,
                                  away_team_id, completed)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                lg.factory._id(),
                f"2026-04-{3 + i:02d}",
                lg.season.id,
                lg.mine.id,
                lg.theirs.id,
                1 if i < played else 0,
            ),
        )


def test_share_of_the_season_played(lg):
    _season(lg, played=4)
    assert prorate.season_played(lg.db, lg.league.id) == pytest.approx(0.4)
    lg.db.execute(
        "UPDATE leagues SET state = 'preseason' WHERE id = %s", (lg.league.id,)
    )
    assert prorate.season_played(lg.db, lg.league.id) == 0.0


def test_a_mid_season_trade_splits_his_salary(lg):
    pid = _signed(lg, level=70)
    salary = lg.contracts.active(pid, 2026)["salary"]
    mine_before = lg.contracts.payroll(lg.mine.id, 2026)
    theirs_before = lg.contracts.payroll(lg.theirs.id, 2026)
    _season(lg, played=4)  # 40% of the season gone

    trades.execute(
        lg.db, lg.league.id, lg.season.id, {lg.mine.id: [pid], lg.theirs.id: []},
        "2026-04-08",
    )  # fmt: skip

    # I keep 40% of him; they carry the other 60%.
    assert lg.contracts.payroll(lg.mine.id, 2026) == pytest.approx(
        mine_before - salary + 0.4 * salary, abs=1
    )
    assert lg.contracts.payroll(lg.theirs.id, 2026) == pytest.approx(
        theirs_before + 0.6 * salary, abs=1
    )


def test_traded_back_again_splits_three_ways(lg):
    pid = _signed(lg, level=70)
    salary = lg.contracts.active(pid, 2026)["salary"]
    mine_before = lg.contracts.payroll(lg.mine.id, 2026)
    _season(lg, played=2)
    trades.execute(
        lg.db, lg.league.id, lg.season.id, {lg.mine.id: [pid], lg.theirs.id: []},
        "2026-04-05",
    )  # fmt: skip
    lg.db.execute(
        "UPDATE games SET completed = 1 WHERE season_id = %s AND game_date <= '2026-04-09'",
        (lg.season.id,),
    )
    played = prorate.season_played(lg.db, lg.league.id)
    trades.execute(
        lg.db, lg.league.id, lg.season.id, {lg.theirs.id: [pid], lg.mine.id: []},
        "2026-04-10",
    )  # fmt: skip
    # They had him from 20% to `played`; I pay the rest.
    theirs_share = lg.contracts.adjustments(lg.theirs.id, 2026)
    assert theirs_share == pytest.approx((played - 0.2) * salary, abs=2)
    assert lg.contracts.payroll(lg.mine.id, 2026) == pytest.approx(
        mine_before - (played - 0.2) * salary, abs=2
    )


def test_a_preseason_trade_moves_the_whole_salary(lg):
    pid = _signed(lg, level=70)
    salary = lg.contracts.active(pid, 2026)["salary"]
    theirs_before = lg.contracts.payroll(lg.theirs.id, 2026)
    lg.db.execute(
        "UPDATE leagues SET state = 'preseason' WHERE id = %s", (lg.league.id,)
    )
    trades.execute(
        lg.db, lg.league.id, lg.season.id, {lg.mine.id: [pid], lg.theirs.id: []},
        "2026-04-01",
    )  # fmt: skip
    assert lg.contracts.payroll(lg.theirs.id, 2026) == theirs_before + salary
    assert lg.contracts.adjustments(lg.mine.id, 2026) == 0


def test_a_late_free_agent_signing_pays_only_the_rest(lg):
    pid = lg.factory.rated_player(lg.theirs, lg.league, level=62).id
    lg.contracts.sign_unsigned(lg.league.id, 2026)
    lg.contracts.guarantee_teams([lg.theirs.id])
    free_agents.release(lg.db, lg.league.id, lg.theirs.id, pid)
    waivers.clear_all(lg.db, lg.league.id)
    owed = lg.contracts.dead_money(lg.theirs.id, 2026)
    theirs_before = lg.contracts.payroll(lg.theirs.id, 2026)
    mine_before = lg.contracts.payroll(lg.mine.id, 2026)
    _season(lg, played=9)  # 90% gone

    free_agents.sign(lg.db, lg.league.id, lg.mine.id, pid)

    new = lg.contracts.active(pid, 2026)["salary"]
    assert lg.contracts.payroll(lg.mine.id, 2026) == pytest.approx(
        mine_before + 0.1 * new, abs=1
    )
    # His new salary only takes the last 10% off what they still owed.
    offset = min(new, owed)
    assert lg.contracts.payroll(lg.theirs.id, 2026) == pytest.approx(
        theirs_before - 0.1 * offset, abs=1
    )


def test_a_waiver_claim_leaves_the_old_team_its_share(lg):
    pid = _signed(lg, level=65)
    salary = lg.contracts.active(pid, 2026)["salary"]
    _season(lg, played=5)
    free_agents.release(lg.db, lg.league.id, lg.mine.id, pid)
    waivers.claim(lg.db, lg.league.id, lg.theirs.id, pid, 2026)
    waivers.clear_all(lg.db, lg.league.id)

    assert lg.contracts.adjustments(lg.mine.id, 2026) == pytest.approx(
        0.5 * salary, abs=1
    )
    assert lg.contracts.adjustments(lg.theirs.id, 2026) == pytest.approx(
        -0.5 * salary, abs=1
    )
