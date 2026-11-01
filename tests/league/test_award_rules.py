# tests/league/test_awards.py
"""Who wins each season award (src/league/awards.py), from stat lines."""

from src.league import awards

GAMES = 162


def hitter(pid, scope="Atlantic League", team="t1", pos="rf", ab=550, hits=150,
           hr=20, bb=50, rbi=80, prior_ab=1000, **extra):  # fmt: skip
    c = {
        "player_id": pid, "team_id": team, "scope": scope,
        "position": pos, "pos_starts": 150, "starts": 150,
        "bat_games_played": 155, "bat_ab": ab, "bat_hits": hits,
        "bat_doubles": 30, "bat_triples": 2, "bat_home_runs": hr,
        "bat_walks": bb, "bat_rbi": rbi, "bat_runs": 80,
        "prior_ab": prior_ab, "prior_outs": 0,
    }  # fmt: skip
    c.update(extra)
    return c


def pitcher(pid, scope="Atlantic League", team="t1", gs=32, g=32, outs=600,
            er=70, k=200, bb=50, hr=20, w=14, l=9, sv=0, hld=0,
            prior_outs=2000, **extra):  # fmt: skip
    c = {
        "player_id": pid, "team_id": team, "scope": scope, "position": None,
        "pos_starts": 0, "starts": 0,
        "pitch_games_played": g, "pitch_games_started": gs, "pitch_outs": outs,
        "pitch_earned_runs": er, "pitch_strike_outs": k, "pitch_walks": bb,
        "pitch_home_runs": hr, "pitch_wins": w, "pitch_losses": l,
        "pitch_saves": sv, "pitch_holds": hld, "pitch_hits": outs // 3,
        "prior_ab": 0, "prior_outs": prior_outs,
    }  # fmt: skip
    c.update(extra)
    return c


def field(n=8, scope="Atlantic League"):
    """An ordinary league to measure against."""
    return [hitter(f"h{scope[0]}{i}", scope=scope) for i in range(n)] + [
        pitcher(f"p{scope[0]}{i}", scope=scope) for i in range(n)
    ]


def won(rows, award, scope="Atlantic League"):
    return next(
        (r["player_id"] for r in rows if r["award"] == award and r["scope"] == scope),
        None,
    )


class TestMVP:
    def test_the_best_hitter_wins(self):
        cands = field() + [hitter("star", hits=190, hr=45, rbi=130)]
        rows = awards.regular_awards(cands, GAMES, {})
        assert won(rows, "mvp") == "star"
        assert (
            next(r for r in rows if r["award"] == "mvp")["line"]
            == ".345, 45 HR, 130 RBI"
        )

    def test_one_in_each_league(self):
        cands = field() + field(scope="Pacific League")
        cands += [
            hitter("a", hr=45, hits=190),
            hitter("p", scope="Pacific League", hr=40, hits=185),
        ]
        rows = awards.regular_awards(cands, GAMES, {})
        assert won(rows, "mvp") == "a"
        assert won(rows, "mvp", "Pacific League") == "p"

    def test_a_catchers_bat_counts_for_more_than_a_dhs(self):
        cands = field() + [
            hitter("dh", pos="dh", hits=175, hr=35),
            hitter("c", pos="c", hits=175, hr=35),
        ]
        assert won(awards.regular_awards(cands, GAMES, {}), "mvp") == "c"

    def test_a_winning_team_breaks_a_near_tie(self):
        cands = field() + [
            hitter("loser", team="bad", hits=176, hr=35),
            hitter("winner", team="good", hits=175, hr=35),
        ]
        rows = awards.regular_awards(cands, GAMES, {"good": 0.62, "bad": 0.40})
        assert won(rows, "mvp") == "winner"


class TestPitching:
    def test_cy_young_goes_to_the_best_pitcher(self):
        cands = field() + [pitcher("ace", er=40, k=260, w=20, l=5)]
        rows = awards.regular_awards(cands, GAMES, {})
        assert won(rows, "cy_young") == "ace"
        assert (
            next(r for r in rows if r["award"] == "cy_young")["line"]
            == "20-5, 1.80 ERA, 260 K"
        )

    def test_reliever_of_the_year_is_a_reliever(self):
        cands = field() + [
            pitcher("ace", er=40, k=260, w=20, l=5),
            pitcher("closer", gs=0, g=65, outs=200, er=12, k=95, w=4, l=2, sv=41),
        ]
        rows = awards.regular_awards(cands, GAMES, {})
        assert won(rows, "reliever") == "closer"
        assert next(r for r in rows if r["award"] == "reliever")["line"].startswith(
            "41 SV"
        )

    def test_era_champion_needs_an_inning_a_game(self):
        cands = field() + [
            pitcher("short", outs=300, er=10),  # 100 IP, 0.90 ERA
            pitcher("ace", outs=600, er=40),
        ]
        rows = awards.regular_awards(cands, GAMES, {})
        assert won(rows, "era_champ") == "ace"


class TestHitting:
    def test_batting_champion_needs_enough_plate_appearances(self):
        cands = field() + [
            hitter("part", ab=200, hits=80, bb=10),  # .400 in 210 PA
            hitter("full", ab=600, hits=200),
        ]
        rows = awards.regular_awards(cands, GAMES, {})
        assert won(rows, "batting_champ") == "full"
        assert next(r for r in rows if r["award"] == "batting_champ")["line"] == ".333"

    def test_hank_aaron_ignores_position(self):
        cands = field() + [
            hitter("ss", pos="ss", hits=170, hr=30),
            hitter("slugger", pos="1b", hits=172, hr=34),
        ]
        assert won(awards.regular_awards(cands, GAMES, {}), "hank_aaron") == "slugger"

    def test_edgar_martinez_is_league_wide_and_for_regular_dhs(self):
        cands = (
            field()
            + field(scope="Pacific League")
            + [
                hitter("dh", pos="dh", hits=170, hr=30),
                hitter("pdh", scope="Pacific League", pos="dh", hits=160, hr=25),
                # Started at DH most, but not half his games.
                hitter("part", pos="dh", pos_starts=60, starts=150, hits=200, hr=40),
            ]
        )
        rows = [
            r
            for r in awards.regular_awards(cands, GAMES, {})
            if r["award"] == "edgar_martinez"
        ]
        assert [(r["player_id"], r["scope"]) for r in rows] == [("dh", "")]

    def test_no_dh_no_edgar_martinez(self):
        rows = awards.regular_awards(field(), GAMES, {})
        assert not any(r["award"] == "edgar_martinez" for r in rows)


class TestRookie:
    def test_only_rookies(self):
        cands = field() + [
            hitter("vet", hits=200, hr=40),
            hitter("kid", hits=160, hr=25, prior_ab=100),
        ]
        rows = awards.regular_awards(cands, GAMES, {})
        assert won(rows, "roy") == "kid"

    def test_not_in_a_leagues_first_season(self):
        cands = field() + [hitter("kid", hits=160, prior_ab=0)]
        rows = awards.regular_awards(cands, GAMES, {}, first_season=True)
        assert not any(r["award"] == "roy" for r in rows)


class TestGMOfTheYear:
    def team(self, tid, w, l, pw=None, pl=None, title=False, scope="Atlantic League"):
        return {
            "team_id": tid, "gm_id": f"gm-{tid}", "scope": scope, "wins": w,
            "losses": l, "prev_wins": pw, "prev_losses": pl, "division_title": title,
        }  # fmt: skip

    def test_the_biggest_turnaround(self):
        rows = awards.gm_of_year(
            [
                self.team("steady", 98, 64, 99, 63, title=True),
                self.team("riser", 92, 70, 65, 97),
            ]
        )
        assert [(r["gm_id"], r["line"]) for r in rows] == [
            ("gm-riser", "92-70, up 27 wins")
        ]

    def test_one_in_each_league(self):
        rows = awards.gm_of_year(
            [self.team("a", 90, 72), self.team("p", 88, 74, scope="Pacific League")]
        )
        assert {r["scope"]: r["gm_id"] for r in rows} == {
            "Atlantic League": "gm-a", "Pacific League": "gm-p",
        }  # fmt: skip


class TestSeriesMVP:
    def test_the_winners_best_player(self):
        lines = [
            {"player_id": "a", "team_id": "t", "bat_ab": 24, "bat_hits": 10,
             "bat_home_runs": 3, "bat_rbi": 8, "bat_runs": 5},
            {"player_id": "b", "team_id": "t", "bat_ab": 20, "bat_hits": 5},
            {"player_id": "p", "team_id": "t", "pitch_outs": 42, "pitch_strike_outs": 14,
             "pitch_earned_runs": 2, "pitch_wins": 2, "pitch_hits": 8},
        ]  # fmt: skip
        mvp = awards.series_mvp(lines)
        assert mvp["player_id"] == "a"
        assert mvp["line"] == "10-for-24, 3 HR, 8 RBI, 5 R"

    def test_a_pitchers_line(self):
        line = awards.series_line(
            {
                "pitch_outs": 42,
                "pitch_strike_outs": 14,
                "pitch_earned_runs": 2,
                "pitch_wins": 2,
            }  # fmt: skip
        )
        assert line == "2-0, 1.29 ERA, 14.0 IP, 14 K"


class TestWinsChampion:
    def test_most_wins_ties_to_the_better_era(self):
        cands = field() + [
            pitcher("a", w=21, l=8, er=80),
            pitcher("b", w=21, l=6, er=60),
        ]
        rows = awards.regular_awards(cands, GAMES, {})
        assert won(rows, "wins_champ") == "b"
        line = next(r for r in rows if r["award"] == "wins_champ")["line"]
        assert line == "21-6, 2.70 ERA"


def glover(pid, pos, rating, po=300, a=100, e=8, scope="Atlantic League", **extra):
    return hitter(
        pid, scope=scope, pos=pos, ratings={pos: rating},
        field_putouts=po, field_assists=a, field_errors=e, **extra,
    )  # fmt: skip


class TestGoldGloves:
    def test_the_best_glove_at_each_position(self):
        cands = [
            glover("ss1", "ss", 60), glover("ss2", "ss", 85), glover("ss3", "ss", 70),
            glover("cf1", "cf", 80), glover("cf2", "cf", 50),
        ]  # fmt: skip
        rows = awards.gold_gloves(cands, GAMES)
        gg = {r["position"]: r["player_id"] for r in rows if r["award"] == "gold_glove"}
        assert gg == {"ss": "ss2", "cf": "cf1"}

    def test_needs_a_third_of_the_starts(self):
        cands = [
            glover("part", "ss", 99, pos_starts=40),
            glover("a", "ss", 60), glover("b", "ss", 65),
        ]  # fmt: skip
        rows = awards.gold_gloves(cands, GAMES)
        assert won(rows, "gold_glove") == "b"

    def test_errors_count_against(self):
        cands = [glover("hands", "1b", 70, e=2), glover("stone", "1b", 70, e=20)]
        assert won(awards.gold_gloves(cands, GAMES), "gold_glove") == "hands"

    def test_platinum_glove_is_the_standout_winner(self):
        cands = [
            # A close race at short, a runaway in center.
            glover("ss1", "ss", 80), glover("ss2", "ss", 79),
            glover("cf1", "cf", 95), glover("cf2", "cf", 50), glover("cf3", "cf", 52),
        ]  # fmt: skip
        rows = awards.gold_gloves(cands, GAMES)
        plat = [r for r in rows if r["award"] == "platinum_glove"]
        assert [(r["player_id"], r["line"]) for r in plat] == [
            ("cf1", "Gold Glove at CF")
        ]


class TestSilverSluggers:
    def voters(self, n, scope="Atlantic League", **dials):
        return [
            {"team_id": f"t{i}", "scope": scope, "dials": dials or None}
            for i in range(n)
        ]

    def test_the_best_bat_at_each_position(self):
        cands = [
            hitter("c1", pos="c", hits=120, hr=10), hitter("c2", pos="c", hits=170, hr=30),
            hitter("dh1", pos="dh", hits=180, hr=40), hitter("dh2", pos="dh", hits=130),
        ]  # fmt: skip
        rows = awards.silver_sluggers(cands, GAMES, self.voters(6))
        ss = {r["position"]: r for r in rows}
        assert ss["c"]["player_id"] == "c2"
        assert ss["dh"]["player_id"] == "dh1"
        assert ss["c"]["line"] == "C, .309, 30 HR, 80 RBI · 6 of 6 first-place votes"
        assert ss["c"]["value"] == 30  # 6 votes at 5 points

    def test_old_school_and_analytics_gms_can_disagree(self):
        # Lots of RBI and average, versus walks and power.
        trad = hitter("trad", pos="rf", hits=185, hr=22, rbi=125, bb=20)
        modern = hitter("modern", pos="rf", hits=150, hr=30, rbi=80, bb=110)
        cands = [trad, modern, hitter("x", pos="rf", hits=120, hr=8)]
        old = awards.silver_sluggers(cands, GAMES, self.voters(5, analytics=0))
        new = awards.silver_sluggers(cands, GAMES, self.voters(5, analytics=100))
        assert old[0]["player_id"] == "trad"
        assert new[0]["player_id"] == "modern"

    def test_voters_vote_in_their_own_league(self):
        cands = [
            hitter("a", pos="1b"),
            hitter("p", scope="Pacific League", pos="1b"),
        ]
        voters = self.voters(3) + self.voters(2, scope="Pacific League")
        rows = awards.silver_sluggers(cands, GAMES, voters)
        lines = {r["scope"]: r["line"] for r in rows}
        assert lines["Atlantic League"].endswith("3 of 3 first-place votes")
        assert lines["Pacific League"].endswith("2 of 2 first-place votes")
