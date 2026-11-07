# tests/league/test_hall_of_fame_rules.py
"""Hall of Fame rules (src/league/hall_of_fame.py): what the writers see in
a career, who's eligible, the screening committee, and the vote."""

import random

import pytest

from src.league import hall_of_fame as hof


def _career(
    pid="p",
    years=15,
    war=5.0,
    backstory=0,
    hitter=True,
    honors=(),
    hits=180,
    hr=30,
):
    """A career of `years` seasons from 2000, the first `backstory` of them
    made up before the league started."""
    seasons = [
        hof.Season(
            year=2000 + i,
            backstory=i < backstory,
            war=war,
            hitter=hitter,
            games=150 if hitter else 33,
            starts=0 if hitter else 33,
            hits=hits if hitter else 0,
            hr=hr if hitter else 0,
            wins=0 if hitter else 15,
            k=0 if hitter else 200,
            team_id="t1",
        )
        for i in range(years)
    ]
    return hof.Career(
        pid, seasons, [hof.Honor(k, y, y < 2000 + backstory) for k, y in honors]
    )


def _name(rng):
    return f"Writer {rng.randint(0, 10**6)}"


def _writers(n_teams=30):
    return hof.writers("lg", [(f"t{i}", f"City{i}") for i in range(n_teams)], _name)


# ── What a career counts for ─────────────────────────────────────────────────


def test_backstory_seasons_count_nine_tenths():
    played = _career(years=10, war=4.0)
    made_up = _career(years=10, war=4.0, backstory=10)
    assert played.war == 40.0
    assert made_up.war == pytest.approx(36.0)
    assert made_up.raw_war == 40.0
    assert made_up.total("hits") == pytest.approx(played.total("hits") * 0.9)


def test_backstory_honors_count_nine_tenths():
    c = _career(backstory=5, honors=[("mvp", 2001), ("mvp", 2010)])
    assert c.honors_count("mvp") == pytest.approx(1.9)
    assert c.honors_count("mvp", weighted=False) == 2


def test_peak_is_his_best_seven_years():
    c = _career(years=12, war=1.0)
    for s in c.seasons[:7]:
        s.war = 8.0
    assert c.peak == 56.0
    assert c.jaws == (c.war + 56.0) / 2


def test_a_traded_season_is_one_year_for_the_peak():
    c = _career(years=1, war=3.0)
    c.seasons.append(hof.Season(2000, False, war=3.0, games=60, team_id="t2"))
    assert c.num_seasons == 1
    assert c.peak == 6.0


def test_his_main_team_is_where_he_gave_the_most():
    c = _career(years=10, war=1.0)
    for s in c.seasons[:4]:
        s.team_id, s.war = "t2", 6.0
    assert c.main_team() == "t2"


def test_a_reliever_is_measured_against_relievers():
    c = _career(hitter=False, war=1.5)
    for s in c.seasons:
        s.games, s.starts = 65, 0
    assert c.reliever
    assert c.value_score() > _career(hitter=False, war=1.5).value_score()


# ── Eligibility and the screening committee ─────────────────────────────────


def test_ten_seasons_and_five_years_retired():
    c = _career(years=10)
    assert hof.eligible(c, retired_year=2020, election_year=2025)
    assert not hof.eligible(c, retired_year=2020, election_year=2024)
    assert not hof.eligible(_career(years=9), retired_year=2020, election_year=2025)


def test_backstory_seasons_count_toward_the_ten():
    assert _career(years=10, backstory=8).num_seasons == 10


def test_screening_lets_on_real_careers_only():
    assert hof.passes_screening(_career(years=12, war=3.0))  # 36 WAR
    scrub = _career(years=12, war=0.5, hits=90, hr=5)
    assert not hof.passes_screening(scrub)
    scrub.honors.append(hof.Honor("mvp", 2003, False))
    assert hof.passes_screening(scrub)


# ── The vote ────────────────────────────────────────────────────────────────


def test_two_writers_per_team_the_same_every_time():
    a, b = _writers(), _writers()
    assert len(a) == 60
    assert [(w.name, w.lean, w.bar) for w in a] == [(w.name, w.lean, w.bar) for w in b]


def test_an_inner_circle_great_gets_in_and_a_journeyman_drops_off():
    great = _career("great", years=18, war=7.0, hits=190, hr=35,
                    honors=[("mvp", 2003), ("mvp", 2005), *[("all_star", 2000 + i) for i in range(12)]])  # fmt: skip
    journeyman = _career("journey", years=12, war=1.8, hits=120, hr=12)
    cast, res = hof.elect(
        [hof.Candidate(great, 1), hof.Candidate(journeyman, 1)],
        _writers(),
        random.Random(1),
    )
    by = {r.player_id: r for r in res}
    assert cast == 60
    assert by["great"].outcome == "elected"
    assert by["great"].share >= 0.9
    assert by["journey"].outcome == "dropped"


def test_the_same_great_made_up_before_the_league_falls_short():
    honors = [
        ("mvp", 2003),
        ("mvp", 2005),
        *[("all_star", 2000 + i) for i in range(12)],
    ]
    played = _career("a", years=18, war=5.0, honors=honors)
    made_up = _career("b", years=18, war=5.0, backstory=18, honors=honors)
    _, res = hof.elect(
        [hof.Candidate(played, 1), hof.Candidate(made_up, 1)],
        _writers(),
        random.Random(2),
    )
    by = {r.player_id: r for r in res}
    assert by["a"].share > by["b"].share + 0.1
    assert by["b"].outcome != "elected"


def test_a_strong_career_made_up_before_the_league_still_draws_votes():
    """A league's first ballots are all mostly-backstory careers. The best of
    them get real votes (not 0%), and a borderline one gets some but not all."""
    made_up = _career("great", years=16, war=5.5, backstory=14,
                      honors=[*[("all_star", 2000 + i) for i in range(7)]])  # fmt: skip
    played = _career("border", years=15, war=5.0)
    _, res = hof.elect(
        [hof.Candidate(made_up, 1), hof.Candidate(played, 1)],
        _writers(),
        random.Random(3),
    )
    by = {r.player_id: r for r in res}
    assert 0.1 <= by["great"].share < 0.75
    assert 0.1 <= by["border"].share < 0.9


def test_ten_votes_at_most():
    cands = [hof.Candidate(_career(f"p{i}", years=20, war=7.0), 1) for i in range(14)]
    w = _writers()[0]
    assert len(w.ballot(cands, random.Random(3))) == hof.MAX_VOTES


def test_seventy_five_percent_elects_and_the_tenth_year_is_the_last():
    class Fixed(hof.Writer):
        def ballot(self, cands, rng):
            return [
                c.career.player_id for c in cands if c.career.player_id in self.outlet
            ]

    voters = [
        Fixed(
            f"w{i}",
            "in last" if i < 75 else ("in" if i < 76 else "x"),
            "t",
            "value",
            1.0,
        )
        for i in range(100)
    ]
    # "in" is on 76 ballots, "last" on 75, "tiny" on none.
    cands = [
        hof.Candidate(_career("in"), 3, 0.6),
        hof.Candidate(_career("last"), 10, 0.7),
        hof.Candidate(_career("tiny"), 2, 0.1),
    ]
    _, res = hof.elect(cands, voters, random.Random(0))
    by = {r.player_id: r for r in res}
    assert by["in"].outcome == "elected"
    assert by["last"].outcome == "elected"  # exactly 75% gets in
    assert by["tiny"].outcome == "dropped"


def test_out_of_years_without_getting_in():
    class Half(hof.Writer):  # every other writer votes for him
        def ballot(self, cands, rng):
            return [c.career.player_id for c in cands] if self.bar < 1 else []

    voters = [Half(f"w{i}", "", "t", "value", i % 2) for i in range(100)]
    _, res = hof.elect(
        [hof.Candidate(_career("old"), 10, 0.6)], voters, random.Random(0)
    )
    assert res[0].outcome == "final"
    assert res[0].share == 0.5
