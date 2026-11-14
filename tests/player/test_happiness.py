# tests/player/test_happiness.py
from collections import Counter

import pytest

from src.league import team_pool
from src.player import happiness as hp


def test_a_players_personality_is_the_same_every_time():
    assert hp.personality_for("p-1") == hp.personality_for("p-1")


def test_personalities_cover_every_type_and_keep_dials_in_range():
    seen = Counter()
    for i in range(3000):
        p = hp.personality_for(f"p{i}")
        seen[p.type] += 1
        assert set(p.drives) == set(hp.DRIVES)
        assert all(0 <= v <= 100 for v in p.drives.values())
        assert all(0 <= v <= 100 for v in p.traits.values())
        assert p.climate in (None, *team_pool.CLIMATES)
        for d in hp.TYPES[p.type]["drives"]:
            assert p.drives[d] >= 60
    assert set(seen) == set(hp.TYPES)


def test_underpaid_hurts_more_than_overpaid_pleases():
    under, why = hp.money(5_000_000, 10_000_000)
    over, _ = hp.money(15_000_000, 10_000_000)
    assert why == "under" and under < 0 < over
    assert abs(under) > abs(over)


def test_a_rookie_deal_only_bothers_a_star_a_little():
    sat, why = hp.money(800_000, 20_000_000, rookie=True)
    assert why == "rookie" and -0.3 <= sat < 0


def test_winning_leans_on_team_state_early_and_the_record_later():
    early, _ = hp.winning(1, 1, "rebuilding")
    late, _ = hp.winning(90, 40, "rebuilding")
    assert early < 0 < late


def test_a_benched_star_is_unhappy_and_more_so_with_a_big_ego():
    benched = hp.Usage(team_games=20, starts=5, slots=[6] * 5, positions=["ss"] * 5)
    calm, why = hp.impact(False, "ss", 0, 13, benched, ego=10)
    proud, _ = hp.impact(False, "ss", 0, 13, benched, ego=90)
    assert why == "bench"
    assert proud < calm < 0


def test_the_best_hitter_batting_third_every_day_is_happy():
    starter = hp.Usage(team_games=20, starts=20, slots=[3] * 20, positions=["cf"] * 20)
    sat, why = hp.impact(False, "cf", 0, 13, starter, ego=50)
    assert sat > 0 and why == "star"


def test_a_starter_in_the_bullpen_wants_the_rotation():
    u = hp.Usage(team_games=20, bullpen_role="Middle")
    sat, why = hp.impact(True, "sp", 1, 13, u, ego=50)
    assert sat < 0 and why == "rotation"
    pos, pwhy = hp.position(True, "sp", u)
    assert pos < 0 and pwhy == "rotation"


def test_playing_out_of_position_hurts():
    own, _ = hp.position(False, "ss", hp.Usage(positions=["ss"] * 10))
    off, why = hp.position(False, "ss", hp.Usage(positions=["lf"] * 10))
    near, _ = hp.position(False, "ss", hp.Usage(positions=["2b"] * 10))
    assert off < near < own and why == "off"


def test_a_utility_infielder_is_happy_anywhere_in_the_infield():
    sat, _ = hp.position(False, "if", hp.Usage(positions=["2b", "3b", "ss"]))
    assert sat > 0


def test_home_is_best_and_the_far_side_of_the_world_worst():
    regions = set(team_pool.REGIONS)
    home, why = hp.location(
        team_pool.EUROPE, team_pool.EUROPE, "temperate", regions, None
    )
    near, _ = hp.location(team_pool.EUROPE, team_pool.WEST_ASIA, "warm", regions, None)
    far, _ = hp.location(team_pool.EUROPE, team_pool.OCEANIA, "warm", regions, None)
    assert why == "home" and home > near > far


def test_no_team_from_home_means_partial_credit_for_the_nearest_region():
    league = {team_pool.NORTH_AMERICA, team_pool.EUROPE, team_pool.EAST_ASIA}
    sat, why = hp.location(
        team_pool.SOUTH_AMERICA, team_pool.NORTH_AMERICA, "warm", league, None
    )
    assert why == "home" and sat == hp.NEAREST_REGION_CREDIT


def test_a_favorite_climate_counts():
    regions = set(team_pool.REGIONS)
    likes, _ = hp.location(team_pool.EUROPE, team_pool.EUROPE, "warm", regions, "warm")
    hates, _ = hp.location(team_pool.EUROPE, team_pool.EUROPE, "cold", regions, "warm")
    assert likes > hates


def test_fame_wants_a_big_market():
    assert hp.fame(5, False)[0] > hp.fame(3, False)[0] > hp.fame(1, False)[0]


def test_mood_moves_faster_for_a_volatile_player():
    calm = hp.step(0.0, -1.0, temper=0)
    hot = hp.step(0.0, -1.0, temper=100)
    assert hot < calm < 0


def test_mood_words_run_from_thrilled_to_miserable():
    assert hp.mood_word(0.9) == "thrilled"
    assert hp.mood_word(0.0) == "content"
    assert hp.mood_word(-0.9) == "miserable"


def test_whats_on_his_mind_names_his_biggest_gripe():
    pers = hp.Personality(
        "Mercenary",
        {d: (100 if d == "money" else 10) for d in hp.DRIVES},
        {"ego": 50, "temper": 50, "loyalty": 50},
    )
    sats = {d: (0.0, "none") for d in hp.DRIVES}
    sats["money"] = (-0.8, "under")
    lines = hp.on_his_mind(pers, 28, sats, "ss", team_pool.EUROPE)
    assert lines == ["Thinks he's underpaid."]
    assert hp.target(pers, 28, sats) < -0.3


def test_out_of_position_line_names_the_position():
    pers = hp.Personality(
        "Grinder",
        {d: (100 if d == "position" else 10) for d in hp.DRIVES},
        {"ego": 50, "temper": 50, "loyalty": 50},
    )
    sats = {d: (0.0, "none") for d in hp.DRIVES}
    sats["position"] = (-0.9, "off")
    assert hp.on_his_mind(pers, 28, sats, "ss", None) == ["Wants to play shortstop."]


TRAITS = {"ego": 50, "temper": 50, "loyalty": 50}


def test_only_a_player_unhappy_for_weeks_asks_out():
    assert not hp.asks_for_trade(-0.8, 1, TRAITS, 0.0)
    assert not hp.asks_for_trade(0.0, 9, TRAITS, 0.0)
    assert hp.asks_for_trade(-0.8, 3, TRAITS, 0.0)
    assert not hp.asks_for_trade(-0.8, 3, TRAITS, 0.99)


def test_low_value_players_rarely_ask_out_and_minor_leaguers_never():
    assert hp.request_value(0.9, False) == 1.0
    assert hp.request_value(0.1, False) == hp.REQUEST_FLOOR
    assert hp.REQUEST_FLOOR < hp.request_value(0.35, False) < 1.0
    assert hp.request_value(0.9, True) == 0.0
    # A roll that's a yes at full value is a no for a low-value player.
    assert hp.asks_for_trade(-0.8, 3, TRAITS, 0.1)
    assert not hp.asks_for_trade(-0.8, 3, TRAITS, 0.1, hp.request_value(0.1, False))
    assert not hp.asks_for_trade(-0.8, 3, TRAITS, 0.0, 0.0)


def test_a_hothead_asks_out_sooner():
    hot = {**TRAITS, "temper": 90}
    assert hp.asks_for_trade(-0.8, 2, hot, 0.0)
    assert not hp.asks_for_trade(-0.8, 2, TRAITS, 0.0)


def test_only_a_miserable_hothead_ever_refuses_to_play_and_rarely():
    hot = {**TRAITS, "temper": 90}
    assert hp.refuses_to_play(-0.5, hot, 0.0) == 0
    assert hp.refuses_to_play(-0.9, TRAITS, 0.0) == 0
    assert 3 <= hp.refuses_to_play(-0.9, hot, 0.0) <= 5
    assert hp.refuses_to_play(-0.9, hot, 0.2) == 0


def test_resign_terms_run_from_discount_to_one_year_and_out():
    happy = hp.resign_terms(0.6, loyalty=100)
    assert happy == (0.85, None, False)
    assert hp.resign_terms(0.0, 50) == (1.0, None, False)
    assert hp.resign_terms(-0.5, 50) == (1.15, 2, False)
    assert hp.resign_terms(-0.9, 50) == (1.2, 1, True)
    assert hp.resign_terms(None, 50) == (1.0, None, False)


def test_the_hometown_discount_grows_with_seasons_in_the_league():
    assert hp.resign_terms(0.6, 100, seasons=0)[0] == 0.85
    assert hp.resign_terms(0.6, 100, seasons=6)[0] == 0.7
    assert hp.resign_terms(0.6, 100, seasons=12)[0] == 0.7
    assert hp.resign_terms(0.6, 50, seasons=6)[0] == 0.85
    # Only happy players give one.
    assert hp.resign_terms(0.0, 100, seasons=6)[0] == 1.0


def test_mood_moves_clutch_most_and_the_rest_only_at_the_extremes():
    assert hp.game_effects(0.0) == {"clutch": 0.0}
    content = hp.game_effects(0.1)
    assert set(content) == {"clutch"}
    miserable = hp.game_effects(-0.9)
    assert miserable["clutch"] == -9.0 and miserable["contact"] == -2.0
    thrilled = hp.game_effects(0.8)
    assert thrilled["clutch"] == 8.0 and thrilled["power"] == 1.5


def test_a_type_says_what_it_cares_most_about():
    assert hp.type_cares("Ring Chaser") == "winning"
    assert hp.type_cares("Franchise Star") == (
        "playing time and a big role, money and fame and a big market"
    )
    assert hp.type_cares("Easygoing") == ""


def test_morale_ruiners_are_rare_and_seeded_by_id():
    ids = [f"p{i}" for i in range(4000)]
    share = sum(hp.personality_for(pid).ruiner for pid in ids) / len(ids)
    assert 0.03 < share < 0.09
    assert hp.personality_for("p7").ruiner == hp.personality_for("p7").ruiner
    row = {**hp.personality_for("p7").as_row(), "player_id": "p7"}
    assert hp.Personality.from_row(row).ruiner == hp.personality_for("p7").ruiner


def test_only_an_unhappy_ruiner_drags_the_clubhouse():
    assert hp.clubhouse_drag([0.2, -0.3]) == 0
    one = hp.clubhouse_drag([-0.5])
    worse = hp.clubhouse_drag([-1.0])
    assert 0 < one < worse
    assert hp.clubhouse_drag([-1.0, -1.0, -1.0]) == hp.CLUBHOUSE_CAP


def test_calm_players_shrug_off_the_clubhouse():
    calm = hp.Personality("Easygoing", {}, {"ego": 50, "temper": 20, "loyalty": 50})
    hot = hp.Personality("Mercenary", {}, {"ego": 50, "temper": 90, "loyalty": 50})
    assert hp.susceptibility(calm) == 0
    assert hp.susceptibility(hot) == 1


def test_coaching_lifts_young_players_most_and_standard_does_nothing():
    assert hp.coaching_lift(None, 22) == 0
    assert hp.coaching_lift(2, 22) == 0  # Standard
    assert hp.coaching_lift(4, 22) == pytest.approx(0.1)
    assert hp.coaching_lift(0, 22) == pytest.approx(-0.1)
    # Fades with age, but a veteran still feels some of it.
    assert 0 < hp.coaching_lift(4, 31) < hp.coaching_lift(4, 26) < 0.1
    assert hp.coaching_lift(4, 35) == pytest.approx(0.1 * hp.COACHING_VET_SHARE)
    # Only a big lift (or drag) comes up, and never by its level's name.
    assert hp.coaching_line(hp.coaching_lift(4, 22)) == hp.COACHING_GOOD_TEXT
    assert hp.coaching_line(hp.coaching_lift(0, 22)) == hp.COACHING_BAD_TEXT
    assert hp.coaching_line(hp.coaching_lift(3, 22)) is None
    assert hp.coaching_line(hp.coaching_lift(4, 33)) is None


def test_a_loyal_player_takes_back_his_request_a_week_sooner():
    loyal = {"ego": 50, "temper": 50, "loyalty": 80}
    other = {"ego": 50, "temper": 50, "loyalty": 40}
    assert not hp.withdraws_request(hp.WITHDRAW_WEEKS - 2, loyal)
    assert hp.withdraws_request(hp.WITHDRAW_WEEKS - 1, loyal)
    assert not hp.withdraws_request(hp.WITHDRAW_WEEKS - 1, other)
    assert hp.withdraws_request(hp.WITHDRAW_WEEKS, other)
