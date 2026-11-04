# tests/player/test_happiness.py
from collections import Counter

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
