# tests/db/repositories/test_injury_repo.py
from datetime import date
import json
import random
from types import SimpleNamespace

import pytest

from src.db.migration_files.migration_002_injury_return_date import upgrade
from src.db.repositories.injury_repo import InjuryRepository


@pytest.fixture
def setup(db_conn, factory):
    league = factory.league(state="season")
    season = factory.season()
    factory.league_season(league, season)
    team = factory.team()
    other = factory.team()
    player = factory.player_row()
    db_conn.execute(
        "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)",
        (team.id, player.id),
    )
    return SimpleNamespace(
        conn=db_conn,
        factory=factory,
        league=league,
        season=season,
        team=team,
        other=other,
        player=player,
        repo=InjuryRepository(db_conn, league.id),
    )


def _add_game(s, game_date, completed):
    s.conn.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id, completed)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (s.factory._id(), game_date, s.season.id, s.team.id, s.other.id, completed),
    )


def test_injury_counts_calendar_days(setup):
    """A 5-day injury on Apr 1 keeps the player out Apr 2-6, back Apr 7."""
    s = setup
    s.repo.injure(s.player.id, s.season.id, date(2025, 4, 1), days=5)

    assert s.repo.is_injured(s.player.id, as_of=date(2025, 4, 2))
    assert s.repo.is_injured(s.player.id, as_of=date(2025, 4, 6))
    assert not s.repo.is_injured(s.player.id, as_of=date(2025, 4, 7))
    assert s.repo.get(s.player.id, as_of=date(2025, 4, 2)).days_remaining == 5
    assert s.repo.get(s.player.id, as_of=date(2025, 4, 4)).days_remaining == 3


def test_off_days_count_toward_recovery(setup):
    """No games are needed to heal: the player's team can be idle all week."""
    s = setup
    s.repo.injure(s.player.id, s.season.id, "2025-04-01", days=3)
    ids = s.repo.get_injured_ids([s.player.id], as_of="2025-04-10")
    assert ids == set()


def test_worse_existing_injury_is_kept(setup):
    s = setup
    s.repo.injure(s.player.id, s.season.id, date(2025, 4, 1), days=30)
    s.repo.injure(s.player.id, s.season.id, date(2025, 4, 5), days=2)
    injury = s.repo.get(s.player.id, as_of=date(2025, 4, 6))
    assert injury.return_date == date(2025, 5, 2)


def test_new_injury_after_recovery_replaces_old(setup):
    s = setup
    s.repo.injure(s.player.id, s.season.id, date(2025, 4, 1), days=2)
    s.repo.injure(s.player.id, s.season.id, date(2025, 4, 10), days=4)
    assert s.repo.get(s.player.id, as_of=date(2025, 4, 11)).days_remaining == 4
    assert s.repo.count_player_injuries(s.player.id, s.season.id) == 2
    assert s.repo.get_days_missed_in_season(s.player.id, s.season.id) == 6


def test_current_date_is_day_after_last_completed_game(setup):
    s = setup
    _add_game(s, "2025-04-01", 1)
    _add_game(s, "2025-04-03", 1)
    _add_game(s, "2025-04-05", 0)
    assert s.repo.current_date() == date(2025, 4, 4)


def test_team_views_report_days_remaining(setup):
    s = setup
    _add_game(s, "2025-04-01", 1)  # league "today" is Apr 2
    s.repo.injure(s.player.id, s.season.id, date(2025, 4, 1), days=10)

    assert s.repo.get_team_injuries(s.team.id) == {s.player.id: 10}
    active = s.repo.get_active_for_team(s.team.id)
    assert active[s.player.id]["days"] == 10
    report = s.repo.get_team_injury_report(s.team.id, s.league.id)
    assert report[0]["days_remaining"] == 10

    assert s.repo.get_team_injuries(s.team.id, as_of=date(2025, 4, 12)) == {}


def test_migration_backfills_return_date_from_games_remaining(setup):
    s = setup
    _add_game(s, "2025-04-01", 1)
    s.conn.execute(
        """INSERT INTO player_injuries (player_id, league_id, games_remaining)
           VALUES (%s, %s, %s)""",
        (s.player.id, s.league.id, 7),
    )
    upgrade(s.conn)
    injury = s.repo.get(s.player.id)
    assert injury.return_date == date(2025, 4, 9)
    assert injury.days_remaining == 7


def test_injury_log_keeps_the_team_and_lists_by_season(setup):
    s = setup
    s.repo.injure(s.player.id, s.season.id, date(2025, 4, 1), days=3, team_id=s.team.id)
    other_player = s.factory.player_row()
    s.repo.injure(
        other_player.id, s.season.id, date(2025, 3, 30), days=8, team_id=s.other.id
    )
    later = s.factory.season(year=2026)
    s.repo.injure(s.player.id, later.id, date(2026, 4, 1), days=1, team_id=s.team.id)

    league = s.repo.get_season_injuries(s.season.id)
    assert [i["player_id"] for i in league] == [other_player.id, s.player.id]
    assert league[1]["team_id"] == s.team.id
    assert league[1]["days_missed"] == 3

    mine = s.repo.get_season_injuries(s.season.id, s.team.id)
    assert [i["player_id"] for i in mine] == [s.player.id]


def test_migration_backfills_injury_log_team(setup):
    from src.db.migration_files.migration_013_injury_log_team import (
        upgrade as add_team,
    )

    s = setup
    game_id = s.factory._id()
    s.conn.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id, completed)
           VALUES (%s, '2025-04-01', %s, %s, %s, 1)""",
        (game_id, s.season.id, s.team.id, s.other.id),
    )
    s.conn.execute(
        """INSERT INTO player_game_stats (game_id, player_id, team_id, opponent_team_id)
           VALUES (%s, %s, %s, %s)""",
        (game_id, s.player.id, s.other.id, s.team.id),
    )
    # Hurt in that game, then again on a day with no box score line
    s.repo.injure(s.player.id, s.season.id, date(2025, 4, 1), days=2)
    s.repo.injure(s.player.id, s.season.id, date(2025, 4, 9), days=2)
    s.conn.execute(
        """INSERT INTO player_season_stats (player_id, season_id, team_id, bat_games_played)
           VALUES (%s, %s, %s, 30)""",
        (s.player.id, s.season.id, s.team.id),
    )

    add_team(s.conn)
    teams = [
        r["team_id"]
        for r in s.conn.execute(
            "SELECT team_id FROM player_injury_log WHERE player_id = %s ORDER BY injury_date",
            (s.player.id,),
        ).fetchall()
    ]
    assert teams == [s.other.id, s.team.id]


def test_injury_type_is_stored_and_listed(setup):
    s = setup
    s.repo.injure(
        s.player.id, s.season.id, "2025-04-01", severity="surgery",
        activity="running", team_id=s.team.id, injury_type="torn_acl",
        rng=random.Random(1),
    )  # fmt: skip
    current = s.repo.get(s.player.id, as_of="2025-04-02")
    assert current.injury_type == "torn_acl"
    assert 270 <= current.days_remaining <= 400
    assert s.repo.get_team_injury_types(s.team.id, as_of="2025-04-02") == {
        s.player.id: "torn_acl"
    }
    assert s.repo.get_injury_log(s.player.id)[0]["injury_type"] == "torn_acl"
    assert s.repo.get_season_injuries(s.season.id)[0]["injury_type"] == "torn_acl"


# ── Rust ──────────────────────────────────────────────────────────────────────


def _rusty(s, rust=None, rust_days=20):
    """Hamstring strain on Apr 1, back Apr 12, with known rust."""
    s.repo.injure(
        s.player.id, s.season.id, "2025-04-01", severity="moderate",
        injury_type="hamstring_strain", days=10, team_id=s.team.id,
        rng=random.Random(1),
    )  # fmt: skip
    s.conn.execute(
        "UPDATE player_injuries SET rust = %s::jsonb, rust_days = %s WHERE player_id = %s",
        (json.dumps(rust or {"speed": 4.0}), rust_days, s.player.id),
    )


def _played(s, *days):
    for day in days:
        gid = s.factory._id()
        s.conn.execute(
            """INSERT INTO games (id, game_date, season_id, home_team_id,
                   away_team_id, completed) VALUES (%s, %s, %s, %s, %s, 1)""",
            (gid, day, s.season.id, s.team.id, s.other.id),
        )
        s.conn.execute(
            """INSERT INTO player_game_stats (game_id, player_id, team_id,
                   opponent_team_id) VALUES (%s, %s, %s, %s)""",
            (gid, s.player.id, s.team.id, s.other.id),
        )


def test_an_injury_with_a_type_rolls_rust(setup):
    s = setup
    s.repo.injure(
        s.player.id, s.season.id, "2025-04-01", severity="moderate",
        injury_type="hamstring_strain", days=10, rng=random.Random(1),
    )  # fmt: skip
    row = s.conn.execute(
        "SELECT rust, rust_days FROM player_injuries WHERE player_id = %s",
        (s.player.id,),
    ).fetchone()
    assert set(row["rust"]) == {"speed", "base_running"}
    assert row["rust_days"] > 0


def test_no_rust_until_the_player_is_back(setup):
    s = setup
    _rusty(s)
    assert s.repo.get_rust([s.player.id], as_of="2025-04-11") == {}
    back = s.repo.get_rust([s.player.id], as_of="2025-04-12")[s.player.id]
    assert back["skills"] == {"speed": 4.0}
    assert back["days_left"] == 18
    assert back["injury_type"] == "hamstring_strain"


def test_rust_fades_with_play_and_twice_as_fast_with_rest(setup):
    s = setup
    _rusty(s)
    days = [f"2025-04-{d}" for d in range(12, 22)]  # Apr 12-21: ten days back
    # Resting all ten days clears a 20-day rust
    assert s.repo.get_rust([s.player.id], as_of="2025-04-22") == {}
    # Playing all ten days clears half of it
    _played(s, *days)
    left = s.repo.get_rust([s.player.id], as_of="2025-04-22")[s.player.id]
    assert left["skills"] == {"speed": 2.0}
    assert left["days_left"] == 8


def test_a_new_injury_replaces_the_old_rust(setup):
    s = setup
    _rusty(s)
    s.repo.injure(s.player.id, s.season.id, "2025-04-14", days=3)
    assert s.repo.get_rust([s.player.id], as_of="2025-04-18") == {}


# ── Lasting effects ──────────────────────────────────────────────────────────


def _skills(s, age=28, level=50, position="of"):
    s.conn.execute(
        "UPDATE players SET position = %s WHERE id = %s", (position, s.player.id)
    )
    s.conn.execute(
        """INSERT INTO player_skills
           (player_id, age, durability, strikes, stamina, recovery, accuracy, clutch,
            speed, power, arm, eye, contact, base_running,
            bunting, catching, infield, outfield, ground_balls)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                   %s, %s, %s, %s, %s)""",
        (s.player.id, age, *([level] * 17)),
    )
    s.conn.execute(
        "INSERT INTO player_talent_caps (player_id, speed, strikes, arm, accuracy)"
        " VALUES (%s, 60, 60, 60, 60)",
        (s.player.id,),
    )


def _skill(s, col, table="player_skills"):
    return s.conn.execute(
        f"SELECT {col} FROM {table} WHERE player_id = %s", (s.player.id,)
    ).fetchone()[col]


class _Rigged(random.Random):
    """random() returns `picks` in turn (the outcome roll, then the cap
    roll), the last one over and over; randint is a normal seeded Random."""

    def __init__(self, *picks):
        super().__init__(1)
        self.picks = list(picks)

    def random(self):
        return self.picks.pop(0) if len(self.picks) > 1 else self.picks[0]


def test_lasting_outcome_waits_for_the_return(setup):
    s = setup
    _skills(s)
    s.repo.injure(
        s.player.id, s.season.id, "2025-04-01", severity="surgery",
        injury_type="torn_acl", days=300, team_id=s.team.id,
    )  # fmt: skip
    assert s.repo.resolve_returns(as_of="2025-12-01") == []
    assert _skill(s, "speed") == 50


def test_a_torn_acl_costs_speed_for_good(setup):
    s = setup
    _skills(s)
    s.repo.injure(
        s.player.id, s.season.id, "2025-04-01", severity="surgery",
        injury_type="torn_acl", days=300, team_id=s.team.id,
    )  # fmt: skip
    # 0.5 lands in "typical"; cap_drop roll of 0.5 is far above 10%
    done = s.repo.resolve_returns(as_of="2026-01-27", rng=_Rigged(0.5))
    assert len(done) == 1
    effects = done[0]["effects"]
    assert done[0]["outcome"] == "typical"
    assert -6 <= effects["speed"] <= -3
    assert _skill(s, "speed") == 50 + effects["speed"]
    assert _skill(s, "speed", "player_talent_caps") == 60  # cap untouched
    log = s.repo.get_injury_log(s.player.id)[0]
    assert log["outcome"] == "typical"
    assert log["effects"] == effects
    assert log["resolved_on"] == "2026-01-27"
    assert log["resolved_season_id"] == s.season.id
    # Only once
    assert s.repo.resolve_returns(as_of="2026-02-10") == []
    assert _skill(s, "speed") == 50 + effects["speed"]


def test_an_unlucky_loss_lowers_the_cap_too(setup):
    s = setup
    _skills(s)
    s.repo.injure(
        s.player.id, s.season.id, "2025-04-01", severity="surgery",
        injury_type="torn_acl", days=300,
    )  # fmt: skip
    # "typical", then a cap roll under 10%
    done = s.repo.resolve_returns(as_of="2026-01-27", rng=_Rigged(0.5, 0.01))
    loss = done[0]["effects"]["speed"]
    assert done[0]["cap_drop"]
    assert _skill(s, "speed") == 50 + loss
    assert _skill(s, "speed", "player_talent_caps") == 60 + loss
    assert s.repo.get_injury_log(s.player.id)[0]["cap_drop"]


def test_a_full_recovery_changes_nothing(setup):
    s = setup
    _skills(s)
    s.repo.injure(
        s.player.id, s.season.id, "2025-04-01", severity="surgery",
        injury_type="torn_acl", days=300,
    )  # fmt: skip
    done = s.repo.resolve_returns(as_of="2026-01-27", rng=_Rigged(0.05))
    assert done[0]["outcome"] == "full"
    assert done[0]["effects"] == {}
    assert _skill(s, "speed") == 50


def test_tommy_john_can_come_back_stronger_and_raise_the_cap(setup):
    s = setup
    _skills(s, position="sp")
    s.repo.injure(
        s.player.id, s.season.id, "2025-04-01", severity="surgery",
        injury_type="tommy_john", days=400,
    )  # fmt: skip
    done = s.repo.resolve_returns(as_of="2026-06-01", rng=_Rigged(0.01))
    gain = done[0]["effects"]["strikes"]
    assert done[0]["outcome"] == "stronger" and gain > 0
    assert _skill(s, "strikes") == 50 + gain
    assert _skill(s, "strikes", "player_talent_caps") == 60 + gain


def test_a_new_injury_settles_the_old_ones_outcome_first(setup):
    s = setup
    _skills(s)
    s.repo.injure(
        s.player.id, s.season.id, "2025-04-01", severity="moderate",
        injury_type="hamstring_strain", days=10,
    )  # fmt: skip
    s.repo.injure(s.player.id, s.season.id, "2025-05-01", days=3, rng=_Rigged(0.95))
    first = s.repo.get_injury_log(s.player.id)[1]
    assert first["outcome"] == "lingering"


def test_injury_without_a_type_has_no_outcome(setup):
    s = setup
    _skills(s)
    s.repo.injure(s.player.id, s.season.id, "2025-04-01", days=3)
    assert s.repo.resolve_returns(as_of="2025-05-01") == []
    row = s.conn.execute(
        "SELECT lasting_done FROM player_injuries WHERE player_id = %s", (s.player.id,)
    ).fetchone()
    assert row["lasting_done"]


def test_migration_63_only_leaves_running_injuries_open(setup):
    from src.db.migration_files.migration_063_injury_lasting import upgrade as m63

    s = setup
    _add_game(s, "2025-05-01", 1)  # league date: May 2
    back = s.player
    out = s.factory.player_row()
    for pid, injured, days in (
        (back.id, "2025-04-01", 10),
        (out.id, "2025-04-20", 300),
    ):
        s.repo.injure(pid, s.season.id, injured, severity="surgery",
                      injury_type="torn_acl", days=days)  # fmt: skip
    # As it was before the migration: no links, nothing done
    s.conn.execute("UPDATE player_injuries SET log_id = NULL, lasting_done = FALSE")
    m63(s.conn)
    rows = {
        r["player_id"]: r
        for r in s.conn.execute(
            "SELECT player_id, log_id, lasting_done FROM player_injuries"
        ).fetchall()
    }
    assert rows[back.id]["lasting_done"]
    assert not rows[out.id]["lasting_done"]
    assert rows[out.id]["log_id"] == s.repo.get_injury_log(out.id)[0]["id"]
