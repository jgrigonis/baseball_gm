# tests/team/test_injured_list.py
"""
Long Form's injured list (Josh, 2026-11-14): 7-day for concussions, 10-day
hitters, 15-day pitchers, 60-day anyone (it frees the 40-man spot), backdated
up to 3 days, no coming off before the days are up or while still hurt. AI
teams place and activate their own.
"""

from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.team.injured_list import InjuredList, ai_kind, kinds_for
from src.team.roster_limits import enforce_roster_limits

TODAY = "2025-05-10"


def _team(factory, human=True):
    league = factory.league(state="season", mode="longform")
    team = factory.team()
    factory.gm(team=team, league=league, is_ai=not human)
    active = [factory.rated_player(team, league, 55, status="26man") for _ in range(13)]
    active += [
        factory.rated_player(team, league, 55, status="26man", pitcher=True)
        for _ in range(13)
    ]
    reserve = [
        factory.rated_player(team, league, 45 + i, status="40man") for i in range(4)
    ]
    reserve += [
        factory.rated_player(team, league, 45 + i, status="40man", pitcher=True)
        for i in range(4)
    ]
    return league, team, active, reserve


def _hurt(
    db_conn, league, team, player, back="2025-06-10", hurt_on="2025-05-08", kind=None
):
    log = db_conn.execute(
        """INSERT INTO player_injury_log
               (player_id, team_id, injury_date, severity, games_missed)
           VALUES (%s, %s, %s, 'moderate', 30) RETURNING id""",
        (player.id, team.id, hurt_on),
    ).fetchone()["id"]
    db_conn.execute(
        """INSERT INTO player_injuries
               (player_id, league_id, return_date, injury_type, log_id)
           VALUES (%s, %s, %s, %s, %s)""",
        (player.id, league.id, back, kind, log),
    )


def test_which_lists_a_player_can_go_on():
    assert kinds_for("ss", None) == [10, 60]
    assert kinds_for("sp", None) == [15, 60]
    assert kinds_for("cf", "concussion") == [7, 10, 60]
    assert ai_kind("rp", None, 80) == 60
    assert ai_kind("rp", None, 12) == 15


def test_placing_backdates_to_the_injury_and_frees_the_active_spot(db_conn, factory):
    league, team, active, _ = _team(factory)
    _hurt(db_conn, league, team, active[0], hurt_on="2025-05-08")
    il = InjuredList(db_conn, league.id)
    assert il.problem_placing(team.id, active[0].id, 10, TODAY) is None
    stint = il.place(team.id, active[0].id, 10, TODAY)
    assert (stint.placed_on, stint.eligible_on) == ("2025-05-08", "2025-05-18")
    assert PlayerStatusRepository(db_conn).get_status(active[0].id) == "40man"
    assert set(il.for_team(team.id)) == {active[0].id}


def test_backdating_stops_at_three_days(db_conn, factory):
    league, team, active, _ = _team(factory)
    _hurt(db_conn, league, team, active[0], hurt_on="2025-04-20")
    stint = InjuredList(db_conn, league.id).place(team.id, active[0].id, 10, TODAY)
    assert stint.placed_on == "2025-05-07"


def test_only_hurt_players_on_the_right_list(db_conn, factory):
    league, team, active, _ = _team(factory)
    il = InjuredList(db_conn, league.id)
    assert "Only injured" in il.problem_placing(team.id, active[0].id, 10, TODAY)
    _hurt(db_conn, league, team, active[0])
    assert "10-day or 60-day" in il.problem_placing(team.id, active[0].id, 15, TODAY)
    # The 7-day list is for concussions.
    assert il.problem_placing(team.id, active[0].id, 7, TODAY) is not None
    _hurt(db_conn, league, team, active[1], kind="concussion")
    assert il.problem_placing(team.id, active[1].id, 7, TODAY) is None


def test_coming_off_needs_the_days_up_and_him_healthy(db_conn, factory):
    league, team, active, _ = _team(factory)
    _hurt(db_conn, league, team, active[0], back="2025-05-12", hurt_on="2025-05-09")
    il = InjuredList(db_conn, league.id)
    il.place(team.id, active[0].id, 10, TODAY)
    assert "until 2025-05-19" in il.problem_activating(
        team.id, active[0].id, "2025-05-15", True
    )
    assert il.problem_activating(team.id, active[0].id, "2025-05-19", True) is None
    il.activate(active[0].id, "2025-05-19")
    assert il.for_team(team.id) == {}


def test_still_hurt_stays_on(db_conn, factory):
    league, team, active, _ = _team(factory)
    _hurt(db_conn, league, team, active[0], back="2025-07-01", hurt_on="2025-05-09")
    il = InjuredList(db_conn, league.id)
    il.place(team.id, active[0].id, 10, TODAY)
    assert "still hurt" in il.problem_activating(
        team.id, active[0].id, "2025-05-25", True
    )


def test_sixty_day_frees_the_40_man_spot(db_conn, factory):
    league, team, active, reserve = _team(factory)
    for i in range(6):  # 26 + 8 + 6 = 40
        factory.rated_player(team, league, 40, status="40man")
    minor = factory.rated_player(team, league, 70, status="minors")
    _hurt(db_conn, league, team, active[0])
    InjuredList(db_conn, league.id).place(team.id, active[0].id, 60, TODAY)
    db_conn.execute(
        "UPDATE player_status SET status = '40man' WHERE player_id = %s", (minor.id,)
    )
    # 41 on the 40-man, but the 60-day doesn't count: nothing goes down.
    moves = enforce_roster_limits(db_conn, league.id, team.id, "longform", TODAY)
    assert not [m for m in moves if m["to"] == "minors"]


def test_a_trade_or_send_down_ends_the_stint(db_conn, factory):
    league, team, active, _ = _team(factory)
    _hurt(db_conn, league, team, active[0])
    il = InjuredList(db_conn, league.id)
    il.place(team.id, active[0].id, 10, TODAY)
    PlayerStatusRepository(db_conn).set_status(active[0].id, "minors")
    assert il.for_team(team.id) == {}


def test_reminders_for_people(db_conn, factory):
    league, team, active, _ = _team(factory)
    _hurt(db_conn, league, team, active[0])
    _hurt(db_conn, league, team, active[1], back="2025-05-11")  # a day: no nag
    due = InjuredList(db_conn, league.id).reminders(team.id, TODAY, 3)
    assert due == {"place": [active[0].id], "activate": []}


def test_ai_places_its_long_injuries_on_the_list(db_conn, factory):
    league, team, active, reserve = _team(factory, human=False)
    _hurt(db_conn, league, team, active[-1])  # a pitcher, out a month
    enforce_roster_limits(db_conn, league.id, team.id, "longform", TODAY)
    stint = InjuredList(db_conn, league.id).for_team(team.id)[active[-1].id]
    assert stint.kind == 15
    status = PlayerStatusRepository(db_conn)
    assert status.get_status(active[-1].id) == "40man"
    assert status.get_status(reserve[-1].id) == "26man"  # best reserve pitcher


def test_ai_takes_healed_players_off_the_list(db_conn, factory):
    league, team, active, _ = _team(factory, human=False)
    star = factory.rated_player(team, league, 75, status="26man")
    _hurt(db_conn, league, team, star, back="2025-05-14", hurt_on="2025-05-08")
    enforce_roster_limits(db_conn, league.id, team.id, "longform", TODAY)
    il = InjuredList(db_conn, league.id)
    assert star.id in il.for_team(team.id)
    enforce_roster_limits(db_conn, league.id, team.id, "longform", "2025-05-18")
    assert il.for_team(team.id) == {}
    assert PlayerStatusRepository(db_conn).get_status(star.id) == "26man"


def test_people_are_not_placed_for_them(db_conn, factory):
    league, team, active, _ = _team(factory)
    _hurt(db_conn, league, team, active[0])
    enforce_roster_limits(db_conn, league.id, team.id, "longform", TODAY)
    assert InjuredList(db_conn, league.id).for_team(team.id) == {}


def test_the_list_clears_at_season_end(db_conn, factory):
    league, team, active, _ = _team(factory)
    _hurt(db_conn, league, team, active[0])
    il = InjuredList(db_conn, league.id)
    il.place(team.id, active[0].id, 60, TODAY)
    il.clear_all("2025-10-30")
    assert il.for_team(team.id) == {}
