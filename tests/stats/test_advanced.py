from src.stats import advanced

LEAGUE = {
    "bat_ab": 5500, "bat_hits": 1350, "bat_doubles": 270, "bat_triples": 25,
    "bat_home_runs": 170, "bat_walks": 500, "bat_hbp": 60, "bat_sac_flys": 40,
    "bat_runs": 730,
    "pitch_outs": 4374, "pitch_earned_runs": 670, "pitch_home_runs": 170,
    "pitch_walks": 500, "pitch_hit_batters": 60, "pitch_strike_outs": 1400,
}  # fmt: skip


def test_league_average_hitter_is_100():
    lg = advanced.LeagueRates.of(LEAGUE)
    bat = advanced.batting({**LEAGUE, "bat_strike_outs": 1200}, lg)
    assert bat["wRC_PLUS"] == 100
    assert bat["OPS_PLUS"] == 100
    assert bat["wOBA"] == round(lg.woba, 3)


def test_league_average_pitcher_has_fip_equal_to_era():
    lg = advanced.LeagueRates.of(LEAGUE)
    pit = advanced.pitching({**LEAGUE, "pitch_hits": 1350}, lg)
    assert pit["ERA_PLUS"] == 100
    assert pit["FIP"] == round(lg.era, 2)


def test_better_hitter_scores_above_100():
    lg = advanced.LeagueRates.of(LEAGUE)
    star = {
        "bat_ab": 550, "bat_hits": 170, "bat_doubles": 35, "bat_triples": 3,
        "bat_home_runs": 35, "bat_walks": 80, "bat_hbp": 5, "bat_sac_flys": 5,
        "bat_strike_outs": 110,
    }  # fmt: skip
    bat = advanced.batting(star, lg)
    assert bat["wRC_PLUS"] > 140
    assert bat["OPS_PLUS"] > 140
    assert bat["ISO"] == round((170 + 35 + 6 + 105) / 550 - 170 / 550, 3)
    assert bat["K_PCT"] == round(100 * 110 / 640, 1)


def test_zero_era_has_no_era_plus():
    lg = advanced.LeagueRates.of(LEAGUE)
    pit = advanced.pitching({"pitch_outs": 6, "pitch_strike_outs": 2}, lg)
    assert pit["ERA_PLUS"] is None
    assert pit["FIP"] is not None


def test_no_league_rates_leaves_plus_stats_empty():
    assert advanced.LeagueRates.of({}) is None
    bat = advanced.batting({"bat_ab": 4, "bat_hits": 1}, None)
    assert bat["wRC_PLUS"] is None and bat["OPS_PLUS"] is None
    assert bat["wOBA"] is not None
    assert advanced.pitching({"pitch_outs": 3}, None)["FIP"] is None
