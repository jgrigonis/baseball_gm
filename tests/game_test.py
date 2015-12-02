# pylint: disable=C0302
# pylint complains about the number of lines in the method.
"""Unit Tests for the Game class."""
import unittest

from game.game import Game
import game.game_exceptions as game_exceptions
from player.player import Player

# pylint: disable=R0904
# pylint complains about the number of public methods.
# pylint: disable=R0902
# pylint complains about the number of instance attributes.
# pylint: disable=R0915
# pylint complains about the number of statements.


class TestInitAnd26Balls(unittest.TestCase):
    """Fairly boring, just testing the init."""
    def setUp(self):
        self.my_game = Game()
        self.pla0 = Player("Sandy", "Koufax")
        self.pla1 = Player("Willie", "Mays")
        self.pla2 = Player("Jackie", "Robinson")
        self.pla3 = Player("Ted", "Williams")
        self.pla4 = Player("Lou", "Gehrig")
        self.pla5 = Player("Honus", "Wagner")
        self.pla6 = Player("Hank", "Aaron")
        self.pla7 = Player("Mike", "Schmidt")
        self.pla8 = Player("Babe", "Ruth")
        self.pla9 = Player("Johnny", "Bench")
        self.pla10 = Player("Jeff", "Kent")

        self.plb0 = Player("Nolan", "Ryan")
        self.plb1 = Player("Ricky", "Henderson")
        self.plb2 = Player("Ryne", "Sandberg")
        self.plb3 = Player("Joe", "DiMaggio")
        self.plb4 = Player("Jimmie", "Foxx")
        self.plb5 = Player("Robin", "Yount")
        self.plb6 = Player("Roberto", "Clemente")
        self.plb7 = Player("George", "Brett")
        self.plb8 = Player("Frank", "Robinson")
        self.plb9 = Player("Yogi", "Berra")
        self.plb10 = Player("Mickey", "Mantle")

    def test_count(self):
        """Count should be empty."""
        self.assertEqual(self.my_game.count.balls, 0)
        self.assertEqual(self.my_game.count.strikes, 0)

    def test_score(self):
        """Score should be nil nil."""
        self.assertEqual(self.my_game.score.home, 0)
        self.assertEqual(self.my_game.score.away, 0)

    def test_inning(self):
        """Start in the top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases["first"], 0)
        self.assertEqual(self.my_game.bases["second"], 0)
        self.assertEqual(self.my_game.bases["third"], 0)

    def test_winner_game_over(self):
        """No one has won, and the game is not over."""
        self.assertEqual(self.my_game.winner, None)
        self.assertEqual(self.my_game.game_over, False)

    def test_outs(self):
        """No outs yet."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_bases_loaded(self):
        """Make sure bases are loaded.

        Use NotEqual rather than Equal 1, because eventually
        bases may hold actual baserunners instead of digits.

        """
        # pylint: disable=C0103
        # pylint: disable=W0612
        for x in range(26):
            self.my_game.ball()
        self.assertNotEqual(self.my_game.bases["first"], 0)
        self.assertNotEqual(self.my_game.bases["second"], 0)
        self.assertNotEqual(self.my_game.bases["third"], 0)

    def test_score_three(self):
        """6 walks should have been issued, leading to 3 scores."""
        # pylint: disable=C0103
        # pylint: disable=W0612
        for x in range(26):
            self.my_game.ball()
        self.assertEqual(self.my_game.score.away, 3)

    def test_count_0_2(self):
        """There were 6 walks, plus 2 more balls."""
        # pylint: disable=C0103
        # pylint: disable=W0612
        for x in range(26):
            self.my_game.ball()
        self.assertEqual(self.my_game.count.balls, 2)

    def test_outs_none(self):
        """No outs yet."""
        # pylint: disable=C0103
        # pylint: disable=W0612
        for x in range(26):
            self.my_game.ball()
        self.assertEqual(self.my_game.inning.outs, 0)

#
# class TestTeamCycles(unittest.TestCase):
#     """Test what happens if the team leads off with a single, double,
#     triple and home run in order.
#
#     """
#     def setUp(self):
#         """Setup instance of Game and have 4 hits in a row."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.hit(1)
#         self.my_game.hit(2)
#         self.my_game.hit(3)
#         self.my_game.hit(4)
#
#     def test_score(self):
#         """First four batters have all scored."""
#         self.assertEqual(self.my_game.away.score, 4)
#
#     def test_batting_order(self):
#         """Home team hasn't batted yet, should still be on 1.
#         Away team shold be on 5th batter.
#
#         """
#         self.assertEqual(self.my_game.home.batter, 1)
#         self.assertEqual(self.my_game.away.batter, 5)
#
#     def test_outs(self):
#         """No outs yet."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_pitcher_stats(self):
#         """Test Stats for pitching."""
#         self.assertEqual(self.my_game.current_pitcher.stats['h'], 4)
#         self.assertNotEqual(self.my_game.current_pitcher.era(), "0.00")
#         self.assertEqual(self.my_game.current_pitcher.stats['r'], 4)
#         self.assertEqual(self.my_game.current_pitcher.stats['er'], 4)
#         self.assertEqual(self.my_game.pitch_team_stats.stats['bb'], 0)
#         self.assertNotEqual(self.my_game.pitch_team_stats.era(), "0.00")
#         self.assertEqual(self.my_game.pitch_team_stats.stats['r'], 4)
#         self.assertEqual(self.my_game.pitch_team_stats.stats['er'], 4)
#
#     def test_batting_stats(self):
#         """Test Batting Stats."""
#         self.assertEqual(self.my_game.bat_team_stats.stats['bb'], 0)
#         self.assertEqual(self.my_game.bat_team_stats.stats['r'], 4)
#         self.assertEqual(self.my_game.bat_team_stats.batting_average(),
#                          "1.000")
#         self.assertEqual(self.my_game.bat_team_stats.obp(), "1.000")
#         self.assertEqual(
#             self.my_game.bat_team.player(1).stats.batting.stats['h'], 1)
#         self.assertEqual(
#             self.my_game.bat_team.player(2).stats.batting.stats['h'], 1)
#         self.assertEqual(
#             self.my_game.bat_team.player(2).stats.batting.stats['doubles'], 1)
#         self.assertEqual(
#             self.my_game.bat_team.player(3).stats.batting.stats['h'], 1)
#         self.assertEqual(
#             self.my_game.bat_team.player(3).stats.batting.stats['triples'], 1)
#         self.assertEqual(
#             self.my_game.bat_team.player(3).stats.batting.stats['rbi'], 2)
#         self.assertEqual(
#             self.my_game.bat_team.player(4).stats.batting.stats['h'], 1)
#         self.assertEqual(
#             self.my_game.bat_team.player(4).stats.batting.stats['rbi'], 2)
#         self.assertEqual(
#             self.my_game.bat_team.player(4).stats.batting.stats['hr'], 1)
#         self.assertEqual(
#             self.my_game.bat_team.player(5).stats.batting.stats['h'], 0)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestSingleDoublePlayHitByPitch(unittest.TestCase):
#     """Test what happens if the team leads off with a single, followed
#     by a double play, and then a hit batter.
#
#     """
#     def setUp(self):
#         """Setup instance of Game and have 4 hits in a row."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.hit(1)
#         self.my_game.double_play("second", "first")
#         self.my_game.hit_by_pitch()
#
#     def test_score(self):
#         """No score."""
#         self.assertEqual(self.my_game.away.score, 0)
#
#     def test_batting_order(self):
#         """Home team hasn't batted yet, should still be on 1.
#         Away team shold be on 4th batter.
#
#         """
#         self.assertEqual(self.my_game.home.batter, 1)
#         self.assertEqual(self.my_game.away.batter, 4)
#
#     def test_outs(self):
#         """Two outs."""
#         self.assertEqual(self.my_game.inning.outs, 2)
#
#     def test_bases(self):
#         """Hit batter on first."""
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_pitcher_stats(self):
#         """Test Stats for pitching."""
#         self.assertEqual(self.my_game.current_pitcher.stats['h'], 1)
#         self.assertEqual(self.my_game.current_pitcher.era(), "0.00")
#         self.assertEqual(self.my_game.current_pitcher.stats['r'], 0)
#         self.assertEqual(self.my_game.current_pitcher.stats['er'], 0)
#         self.assertEqual(self.my_game.pitch_team_stats.stats['bb'], 0)
#         self.assertEqual(self.my_game.pitch_team_stats.stats['hb'], 1)
#         self.assertEqual(self.my_game.pitch_team_stats.stats['h'], 1)
#         self.assertEqual(self.my_game.pitch_team_stats.era(), "0.00")
#         self.assertEqual(self.my_game.pitch_team_stats.stats['r'], 0)
#         self.assertEqual(self.my_game.pitch_team_stats.stats['er'], 0)
#
#     def test_batting_stats(self):
#         """Test Batting Stats."""
#         self.assertEqual(self.my_game.bat_team_stats.stats['bb'], 0)
#         self.assertEqual(self.my_game.bat_team_stats.stats['r'], 0)
#         self.assertEqual(self.my_game.bat_team_stats.batting_average(),
#                          ".500")
#         self.assertEqual(self.my_game.bat_team_stats.obp(), ".667")
#         self.assertEqual(
#             self.my_game.bat_team.player(1).stats.batting.stats['h'], 1)
#         self.assertEqual(
#             self.my_game.bat_team.player(2).stats.batting.stats['h'], 0)
#         self.assertEqual(
#             self.my_game.bat_team.player(2).stats.batting.stats['gdp'], 1)
#         self.assertEqual(
#             self.my_game.bat_team.player(3).stats.batting.stats['hbp'], 1)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestMiraclePitching(unittest.TestCase):
#     """Test what happens if the pitchers combine to throw 162
#     straight strikes.  2 perfect games should leave us in the
#     top of the 10th.
#
#     """
#     def setUp(self):
#         """Setup instance of Game and have 4 hits in a row."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         # pylint: disable=C0103
#         # pylint: disable=W0612
#         for x in range(162):
#             self.my_game.strike()
#
#     def test_score(self):
#         """No score."""
#         self.assertEqual(self.my_game.away.score, 0)
#         self.assertEqual(self.my_game.home.score, 0)
#
#     def test_batting_order(self):
#         """Both teams should have gone through the lineups 3 times
#         and be back at lead off hitters.
#
#         """
#         self.assertEqual(self.my_game.home.batter, 1)
#         self.assertEqual(self.my_game.away.batter, 1)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_bases(self):
#         """Bases empty."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_inning(self):
#         """Start of the top of the tenth."""
#         self.assertEqual(self.my_game.inning.number, 10)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_pitcher_stats(self):
#         """Test Stats for pitching."""
#         self.assertEqual(self.my_game.home.stats.pitching.stats['h'], 0)
#         self.assertEqual(self.my_game.home.stats.pitching.era(), "0.00")
#         self.assertEqual(self.my_game.home.stats.pitching.ip(), 9.0)
#         self.assertEqual(self.my_game.home.stats.pitching.stats['r'], 0)
#         self.assertEqual(self.my_game.home.stats.pitching.stats['er'], 0)
#         self.assertEqual(self.my_game.home.stats.pitching.stats['k'], 27)
#         self.assertEqual(self.my_game.away.stats.pitching.stats['h'], 0)
#         self.assertEqual(self.my_game.away.stats.pitching.era(), "0.00")
#         self.assertEqual(self.my_game.away.stats.pitching.ip(), 9.0)
#         self.assertEqual(self.my_game.away.stats.pitching.stats['r'], 0)
#         self.assertEqual(self.my_game.away.stats.pitching.stats['er'], 0)
#         self.assertEqual(self.my_game.away.stats.pitching.stats['k'], 27)
#         self.assertEqual(self.my_game.pitch_team_stats.stats['bb'], 0)
#         self.assertEqual(self.my_game.pitch_team_stats.stats['hb'], 0)
#         self.assertEqual(self.my_game.pitch_team_stats.stats['h'], 0)
#         self.assertEqual(self.my_game.pitch_team_stats.era(), "0.00")
#         self.assertEqual(self.my_game.pitch_team_stats.ip(), 9.0)
#         self.assertEqual(self.my_game.pitch_team_stats.stats['r'], 0)
#         self.assertEqual(self.my_game.pitch_team_stats.stats['er'], 0)
#         self.assertEqual(self.my_game.pitch_team_stats.stats['k'], 27)
#
#     def test_batting_stats(self):
#         """Test Batting Stats."""
#         self.assertEqual(self.my_game.bat_team_stats.stats['bb'], 0)
#         self.assertEqual(self.my_game.bat_team_stats.stats['r'], 0)
#         self.assertEqual(self.my_game.bat_team_stats.stats['so'], 27)
#         self.assertEqual(self.my_game.bat_team_stats.batting_average(),
#                          ".000")
#         self.assertEqual(self.my_game.bat_team_stats.obp(), ".000")
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestAway3Up3DownHomeHomerStrikeOutGroundOut(unittest.TestCase):
#     """Test what happens if the away team goes three up, three down.
#     Then the home team hits homer, then strikes out, then grounds out.
#
#     """
#     def setUp(self):
#         """Setup the described scenario."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.fly_out()
#         self.my_game.ground_out()
#         self.my_game.hit(4)
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.ground_out()
#
#     def test_score(self):
#         """1-0 Home."""
#         self.assertEqual(self.my_game.away.score, 0)
#         self.assertEqual(self.my_game.home.score, 1)
#
#     def test_batting_order(self):
#         """Away team should be on the cleanup hitter.  Home
#         team should also.
#
#         """
#         self.assertEqual(self.my_game.home.batter, 4)
#         self.assertEqual(self.my_game.away.batter, 4)
#
#     def test_outs(self):
#         """2 outs."""
#         self.assertEqual(self.my_game.inning.outs, 2)
#
#     def test_bases(self):
#         """Bases empty."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_inning(self):
#         """Bottom of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, False)
#
#     def test_game_over(self):
#         """Test that the game is not over, and the winner is
#         still None.
#
#         """
#         self.assertEqual(self.my_game.winner, None)
#         self.assertEqual(self.my_game.game_over, False)
#
#     def test_pitcher_stats(self):
#         """Test Stats for pitching."""
#         self.assertEqual(self.my_game.home.stats.pitching.stats['h'], 0)
#         self.assertEqual(self.my_game.home.stats.pitching.era(), "0.00")
#         self.assertEqual(self.my_game.home.stats.pitching.ip(), 1.0)
#         self.assertEqual(self.my_game.home.stats.pitching.stats['r'], 0)
#         self.assertEqual(self.my_game.home.stats.pitching.stats['er'], 0)
#         self.assertEqual(self.my_game.home.stats.pitching.stats['k'], 1)
#         self.assertEqual(self.my_game.away.stats.pitching.stats['h'], 1)
#         self.assertEqual(self.my_game.away.stats.pitching.stats['hr'], 1)
#         self.assertEqual(self.my_game.away.stats.pitching.era(), "13.50")
#         self.assertAlmostEqual(self.my_game.away.stats.pitching.ip(),
#                                .666666666666)
#         self.assertEqual(self.my_game.away.stats.pitching.stats['r'], 1)
#         self.assertEqual(self.my_game.away.stats.pitching.stats['er'], 1)
#         self.assertEqual(self.my_game.away.stats.pitching.stats['k'], 1)
#
#     def test_batting_stats(self):
#         """Test Batting Stats."""
#         self.assertEqual(self.my_game.away.stats.batting.stats['so'], 1)
#         self.assertEqual(self.my_game.away.stats.batting.stats['h'], 0)
#         self.assertEqual(self.my_game.away.stats.batting.stats['r'], 0)
#         self.assertEqual(self.my_game.away.stats.batting.batting_average(),
#                          ".000")
#         self.assertEqual(self.my_game.away.stats.batting.obp(), ".000")
#         self.assertEqual(self.my_game.home.stats.batting.stats['so'], 1)
#         self.assertEqual(self.my_game.home.stats.batting.stats['h'], 1)
#         self.assertEqual(self.my_game.home.stats.batting.stats['r'], 1)
#         self.assertEqual(self.my_game.home.stats.batting.batting_average(),
#                          ".333")
#         self.assertEqual(self.my_game.home.stats.batting.obp(), ".333")
#         self.assertEqual(
#             self.my_game.bat_team.player(1).stats.batting.stats['h'], 1)
#         self.assertEqual(
#             self.my_game.bat_team.player(1).stats.batting.stats['hr'], 1)
#         self.assertEqual(
#             self.my_game.bat_team.player(1).stats.batting.stats['rbi'], 1)
#         self.assertEqual(
#             self.my_game.bat_team.player(1).stats.batting.slugging(), "4.000")
#         self.assertEqual(
#             self.my_game.bat_team.player(2).stats.batting.stats['h'], 0)
#         self.assertEqual(
#             self.my_game.bat_team.player(2).stats.batting.stats['gdp'], 0)
#         self.assertEqual(
#             self.my_game.bat_team.player(3).stats.batting.stats['hbp'], 0)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestBottom9thHomeWin(unittest.TestCase):
#     """Test what happens if the bottom of the 9th comes and the
#     home team is already winning.
#
#     """
#     def setUp(self):
#         """Setup instance of Game and have 4 hits in a row."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#
#         # 7 1/2 innning scoreless
#         # pylint: disable=C0103
#         # pylint: disable=W0612
#         for x in range(135):
#             self.my_game.strike()
#         # bottom 8th lead off homer
#         self.my_game.hit(4)
#         # bottom 8th and top 9th scoreless
#         # pylint: disable=C0103
#         # pylint: disable=W0612
#         for x in range(18):
#             self.my_game.strike()
#
#     def test_score(self):
#         """1-0 Home."""
#         self.assertEqual(self.my_game.away.score, 0)
#         self.assertEqual(self.my_game.home.score, 1)
#
#     def test_batting_order(self):
#         """Away team should have gone through the lineups 3 times
#         and be back at lead off hitters.
#
#         """
#         self.assertEqual(self.my_game.home.batter, 8)
#         self.assertEqual(self.my_game.away.batter, 1)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_bases(self):
#         """Bases empty."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_inning(self):
#         """Top of the ninth, as we don't go into the bottom."""
#         self.assertEqual(self.my_game.inning.number, 9)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_game_over(self):
#         """Test that the game is over, and that home team won."""
#         self.assertEqual(self.my_game.winner, "home")
#         self.assertEqual(self.my_game.game_over, True)
#
#     def test_pitcher_stats(self):
#         """Test Stats for pitching."""
#         self.assertEqual(self.my_game.home.season_stats.pitching.stats['h'], 0)
#         self.assertEqual(self.my_game.home.season_stats.pitching.era(), "0.00")
#         self.assertEqual(self.my_game.home.season_stats.pitching.ip(), 9.0)
#         self.assertEqual(self.my_game.home.season_stats.pitching.stats['r'], 0)
#         self.assertEqual(self.my_game.home.season_stats.pitching.stats['er'], 0)
#         self.assertEqual(self.my_game.home.season_stats.pitching.stats['k'], 27)
#         self.assertEqual(self.my_game.away.season_stats.pitching.stats['h'], 1)
#         self.assertEqual(self.my_game.away.season_stats.pitching.stats['hr'], 1)
#         self.assertEqual(self.my_game.away.season_stats.pitching.era(False),
#                          1.125)
#         self.assertAlmostEqual(self.my_game.away.season_stats.pitching.ip(),
#                                8.0)
#         self.assertEqual(self.my_game.away.season_stats.pitching.stats['r'], 1)
#         self.assertEqual(self.my_game.away.season_stats.pitching.stats['er'], 1)
#         self.assertEqual(self.my_game.away.season_stats.pitching.stats['k'], 24)
#
#     def test_batting_stats(self):
#         """Test Batting Stats."""
#         self.assertEqual(self.my_game.away.season_stats.batting.stats['so'],
#                          27)
#         self.assertEqual(self.my_game.away.season_stats.batting.stats['h'], 0)
#         self.assertEqual(self.my_game.away.season_stats.batting.stats['r'], 0)
#         self.assertEqual(
#             self.my_game.away.season_stats.batting.batting_average(), ".000")
#         self.assertEqual(self.my_game.away.season_stats.batting.obp(), ".000")
#         self.assertEqual(self.my_game.home.season_stats.batting.stats['so'],
#                          24)
#         self.assertEqual(self.my_game.home.season_stats.batting.stats['h'], 1)
#         self.assertEqual(self.my_game.home.season_stats.batting.stats['r'], 1)
#         self.assertEqual(
#             self.my_game.home.season_stats.batting.batting_average(), ".040")
#         self.assertEqual(self.my_game.home.season_stats.batting.obp(), ".040")
#         self.assertEqual(
#             self.my_game.away.player(1).season_stats.batting.stats['h'], 0)
#         self.assertEqual(
#             self.my_game.away.player(1).season_stats.batting.stats['so'], 3)
#         self.assertEqual(
#             self.my_game.away.player(1).season_stats.batting.stats['hr'], 0)
#         self.assertEqual(
#             self.my_game.away.player(1).season_stats.batting.stats['rbi'], 0)
#         self.assertEqual(
#             self.my_game.away.player(1).season_stats.batting.slugging(), ".000")
#         self.assertEqual(
#             self.my_game.away.player(2).season_stats.batting.stats['h'], 0)
#         self.assertEqual(
#             self.my_game.away.player(2).season_stats.batting.stats['gdp'], 0)
#         self.assertEqual(
#             self.my_game.away.player(3).season_stats.batting.stats['hbp'], 0)
#         self.assertEqual(
#             self.my_game.home.player(4).season_stats.batting.stats['h'], 1)
#         self.assertEqual(
#             self.my_game.home.player(4).season_stats.batting.stats['hr'], 1)
#         self.assertEqual(
#             self.my_game.home.player(4).season_stats.batting.stats['rbi'], 1)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestLeadOffHomer(unittest.TestCase):
#     """Test what happens if the lead off hitter hits a homer.
#
#     """
#     def setUp(self):
#         """Setup Game with leadoff homer with the count of 1-1."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.strike()
#         self.my_game.ball()
#         self.my_game.hit(4)
#
#     def test_score(self):
#         """1-0 Away."""
#         self.assertEqual(self.my_game.away.score, 1)
#         self.assertEqual(self.my_game.home.score, 0)
#
#     def test_batting_order(self):
#         """Away team should be on second hitter, Home on first."""
#         self.assertEqual(self.my_game.home.batter, 1)
#         self.assertEqual(self.my_game.away.batter, 2)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_bases(self):
#         """Bases empty."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_game_over(self):
#         """Test that the game is not over, and the winner is
#         still None.
#
#         """
#         self.assertEqual(self.my_game.winner, None)
#         self.assertEqual(self.my_game.game_over, False)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestLeadOffHomerHomeTeam(unittest.TestCase):
#     """Test what happens if the lead off hitter hits a homer
#     for the home team.
#
#     """
#     def setUp(self):
#         """Setup Game with leadoff homer with the count of 1-1."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         # Away Team 3 up 3 down
#         self.my_game.fly_out()
#         self.my_game.fly_out()
#         self.my_game.fly_out()
#         # get the count to 1-1
#         self.my_game.strike()
#         self.my_game.ball()
#         # hit a homer
#         self.my_game.hit(4)
#
#     def test_score(self):
#         """1-0 Away."""
#         self.assertEqual(self.my_game.away.score, 0)
#         self.assertEqual(self.my_game.home.score, 1)
#
#     def test_batting_order(self):
#         """Away team should be on cleanup hitter, Home on second."""
#         self.assertEqual(self.my_game.home.batter, 2)
#         self.assertEqual(self.my_game.away.batter, 4)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_bases(self):
#         """Bases empty."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_inning(self):
#         """Bottom of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, False)
#
#     def test_game_over(self):
#         """Test that the game is not over, and the winner is
#         still None.
#
#         """
#         self.assertEqual(self.my_game.winner, None)
#         self.assertEqual(self.my_game.game_over, False)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestFoulBalls(unittest.TestCase):
#     """Test what happens when hitter start fouling balls off."""
#     def setUp(self):
#         """Setup Game with strikes and foul balls and balls."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.strike()  # 0-1
#         self.my_game.foul_ball()  # 0-2
#         self.my_game.foul_ball()  # 0-2 still
#         self.my_game.ball()  # 1-2
#         self.my_game.foul_ball()  # 1-2 still
#         self.my_game.ball()  # 2-2
#         self.my_game.ball()  # 3-2
#
#     def test_count(self):
#         """Count should be full."""
#         self.assertEqual(self.my_game.count.balls, 3)
#         self.assertEqual(self.my_game.count.strikes, 2)
#
#     def test_batting_order(self):
#         """Both teams should still be on leadoff hitter."""
#         self.assertEqual(self.my_game.home.batter, 1)
#         self.assertEqual(self.my_game.away.batter, 1)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_bases(self):
#         """Bases empty."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestStealingBases(unittest.TestCase):
#     """Test what happens when runners start stealing."""
#     def setUp(self):
#         """Setup Game with strikes and foul balls and balls.
#
#         I put some asserts in this one, for fun.
#
#         """
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.steal("second")
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertNotEqual(self.my_game.bases["second"], 0)
#         self.my_game.strike()
#         self.my_game.steal("third")
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#         self.my_game.strike()
#         self.my_game.steal("home")
#         self.my_game.ball()
#
#     def test_count(self):
#         """Count should be 1-2."""
#         self.assertEqual(self.my_game.count.balls, 1)
#         self.assertEqual(self.my_game.count.strikes, 2)
#
#     def test_batting_order(self):
#         """Home team should still be on leadoff hitter. Away team
#         should be on second batter"""
#         self.assertEqual(self.my_game.home.batter, 1)
#         self.assertEqual(self.my_game.away.batter, 2)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_bases(self):
#         """Bases empty."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_score(self):
#         """Test score."""
#         self.assertEqual(self.my_game.home.score, 0)
#         self.assertEqual(self.my_game.away.score, 1)
#
#     def test_invalid_steal(self):
#         """Test invalid steal."""
#         self.assertRaises(game_exceptions.InvalidSteal, self.my_game.steal, 1)
#
#     def test_steal_stats(self):
#         """Test that the right person gets credit for the steal."""
#         self.assertEqual(self.my_game.away.lineup[1].stats.batting.stats["sb"],
#                          3)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestCaughtStealingBases(unittest.TestCase):
#     """Test what happens when runners get caught stealing."""
#     def setUp(self):
#         """Runner hits for single, steals second, caught at third."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.strike()
#         self.my_game.ball()
#         self.my_game.foul_ball()
#         self.my_game.ball()
#         self.my_game.hit(1)
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.my_game.steal("second")
#         self.assertNotEqual(self.my_game.bases["second"], 0)
#         self.my_game.strike()
#         self.assertEqual(self.my_game.inning.outs, 0)
#         self.my_game.caught_stealing("third")
#         self.my_game.strike()
#
#     def test_count(self):
#         """Count should be 0-2."""
#         self.assertEqual(self.my_game.count.balls, 0)
#         self.assertEqual(self.my_game.count.strikes, 2)
#
#     def test_outs(self):
#         """One out."""
#         self.assertEqual(self.my_game.inning.outs, 1)
#
#     def test_batting_order(self):
#         """Home team should still be on leadoff hitter. Away team
#         should be on second batter.
#
#         """
#         self.assertEqual(self.my_game.home.batter, 1)
#         self.assertEqual(self.my_game.away.batter, 2)
#
#     def test_bases(self):
#         """Bases empty."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_invalid_cs(self):
#         """Test an invalid caught stealing."""
#         self.assertRaises(game_exceptions.InvalidSteal,
#                           self.my_game.caught_stealing, "home")
#
#     def test_another_invalid(self):
#         """Test another invalid stealing."""
#         self.assertRaises(game_exceptions.InvalidSteal,
#                           self.my_game.caught_stealing, "second")
#
#     def test_invalid_base(self):
#         """Test another invalid stealing."""
#         self.assertRaises(game_exceptions.InvalidSteal,
#                           self.my_game.caught_stealing, 4)
#
#     def test_cs_stats(self):
#         """Test that the right person gets the stats."""
#         self.assertEqual(self.my_game.away.lineup[1].stats.batting.stats["cs"],
#                          1)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestCaughtStealingSecondAndHome(unittest.TestCase):
#     """Test what happens when runners get caught stealing."""
#     def setUp(self):
#         """Runner hits for single, caught stealing second, next batter
#         triples, but caught stealing home.
#
#         """
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.strike()
#         self.my_game.ball()
#         self.my_game.foul_ball()
#         self.my_game.ball()
#         self.my_game.hit(1)
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.my_game.caught_stealing("second")
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.my_game.strike()
#         self.assertEqual(self.my_game.inning.outs, 1)
#         self.my_game.ball()
#         self.my_game.hit(3)
#         self.my_game.caught_stealing("home")
#         self.my_game.strike()
#
#     def test_count(self):
#         """Count should be 0-1."""
#         self.assertEqual(self.my_game.count.balls, 0)
#         self.assertEqual(self.my_game.count.strikes, 1)
#
#     def test_outs(self):
#         """Two outs."""
#         self.assertEqual(self.my_game.inning.outs, 2)
#
#     def test_batting_order(self):
#         """Home team should still be on leadoff hitter. Away team
#         should be on third batter.
#
#         """
#         self.assertEqual(self.my_game.home.batter, 1)
#         self.assertEqual(self.my_game.away.batter, 3)
#
#     def test_bases(self):
#         """Bases empty."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestBalks(unittest.TestCase):
#     """Test what happens when runners gets balked around the bases."""
#     def setUp(self):
#         """Runner hits for single, then pitcher balks 3 straight times."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.hit(1)
#         self.my_game.balk()
#         self.my_game.balk()
#         self.my_game.balk()
#
#     def test_count(self):
#         """Count should be empty."""
#         self.assertEqual(self.my_game.count.balls, 0)
#         self.assertEqual(self.my_game.count.strikes, 0)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_batting_order(self):
#         """Home team should still be on leadoff hitter. Away team
#         should be on second batter.
#
#         """
#         self.assertEqual(self.my_game.home.batter, 1)
#         self.assertEqual(self.my_game.away.batter, 2)
#
#     def test_bases(self):
#         """Bases empty."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_score(self):
#         """1-0 Away."""
#         self.assertEqual(self.my_game.away.score, 1)
#         self.assertEqual(self.my_game.home.score, 0)
#
#     def test_bases_empty(self):
#         """Test a balk with bases empty."""
#         self.my_game.balk()
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestFieldersChoiceRetiresSide(unittest.TestCase):
#     """Test what happens when runner gets forced out for third out."""
#     def setUp(self):
#         """Runner hits for single, then pitcher balks 3 straight times."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.hit(1)
#         self.my_game.fly_out()
#         self.my_game.fly_out()
#         self.my_game.fielders_choice("second")
#
#     def test_count(self):
#         """Count should be empty."""
#         self.assertEqual(self.my_game.count.balls, 0)
#         self.assertEqual(self.my_game.count.strikes, 0)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_batting_order(self):
#         """Home team should still be on leadoff hitter. Away team
#         should be on fifth batter.
#
#         """
#         self.assertEqual(self.my_game.home.batter, 1)
#         self.assertEqual(self.my_game.away.batter, 5)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestDoublePlayToEndInning(unittest.TestCase):
#     """Test what happens when batter hits into double play with one out."""
#     def setUp(self):
#         """Runner hits for single, next batter strikes out, then DP."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.hit(1)
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.double_play()
#
#     def test_count(self):
#         """Count should be empty."""
#         self.assertEqual(self.my_game.count.balls, 0)
#         self.assertEqual(self.my_game.count.strikes, 0)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_batting_order(self):
#         """Home team should still be on leadoff hitter. Away team
#         should be on cleanup hitter.
#
#         """
#         self.assertEqual(self.my_game.home.batter, 1)
#         self.assertEqual(self.my_game.away.batter, 4)
#
#     def test_bases(self):
#         """Bases empty."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_inning(self):
#         """Bottom of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, False)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestFieldersChoiceNoOuts(unittest.TestCase):
#     """Test what happens when batter hits into fielder's choice with no outs."""
#     def setUp(self):
#         """Runner hits for single, next batter hits into fielder's choice."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.hit(1)
#         self.my_game.fielders_choice("second")
#
#     def test_count(self):
#         """Count should be empty."""
#         self.assertEqual(self.my_game.count.balls, 0)
#         self.assertEqual(self.my_game.count.strikes, 0)
#
#     def test_outs(self):
#         """One out."""
#         self.assertEqual(self.my_game.inning.outs, 1)
#
#     def test_batting_order(self):
#         """Home team should still be on leadoff hitter. Away team
#         should be on third hitter.
#
#         """
#         self.assertEqual(self.my_game.home.batter, 1)
#         self.assertEqual(self.my_game.away.batter, 3)
#
#     def test_bases(self):
#         """Man on first."""
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestAwayTeamWins(unittest.TestCase):
#     """Test what happens when away team wins."""
#     def setUp(self):
#         """Away team wins with grand slam home run in second inning."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         # top of first
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         # bottom of first
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, False)
#         self.my_game.hit(1)
#         self.my_game.fielders_choice("second")
#         self.my_game.double_play()
#         # top of second
#         self.assertEqual(self.my_game.inning.number, 2)
#         self.assertEqual(self.my_game.inning.top, True)
#         self.my_game.strike()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.my_game.hit(1)
#         self.assertNotEqual(self.my_game.bases["second"], 0)
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.ball()
#         self.my_game.ball()
#         # grand slam
#         self.my_game.hit(4)
#         self.assertEqual(self.my_game.away.score, 4)
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         self.my_game.ground_out()
#         # bottom of second
#         self.assertEqual(self.my_game.inning.number, 2)
#         self.assertEqual(self.my_game.inning.top, False)
#         self.my_game.fly_out()
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         # top of third
#         self.assertEqual(self.my_game.inning.number, 3)
#         self.assertEqual(self.my_game.inning.top, True)
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         # bottom of third
#         self.assertEqual(self.my_game.inning.number, 3)
#         self.assertEqual(self.my_game.inning.top, False)
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         # top of fourth
#         self.assertEqual(self.my_game.inning.number, 4)
#         self.assertEqual(self.my_game.inning.top, True)
#         self.my_game.hit(1)
#         self.my_game.hit(1)
#         self.my_game.triple_play()
#         # bottom of fourth
#         self.assertEqual(self.my_game.inning.number, 4)
#         self.assertEqual(self.my_game.inning.top, False)
#         self.my_game.hit(1)
#         self.my_game.double_play()
#         self.my_game.hit(1)
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         # top of fifth
#         self.assertEqual(self.my_game.inning.number, 5)
#         self.assertEqual(self.my_game.inning.top, True)
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         # bottom of fifth
#         self.assertEqual(self.my_game.inning.number, 5)
#         self.assertEqual(self.my_game.inning.top, False)
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         self.my_game.ground_out()
#         # top of sixth
#         self.my_game.fly_out()
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         # bottom of sixth
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         self.my_game.ground_out()
#         # top of seventh
#         self.my_game.fly_out()
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         # bottom of seventh
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         self.my_game.ground_out()
#         # top of eighth
#         self.my_game.fly_out()
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         # bottom of eighth
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         self.my_game.ground_out()
#         # top of ninth
#         self.my_game.fly_out()
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         # bottom of ninth
#         self.assertEqual(self.my_game.inning.number, 9)
#         self.assertEqual(self.my_game.inning.top, False)
#         self.assertEqual(self.my_game.winner, None)
#         self.assertEqual(self.my_game.game_over, False)
#         self.my_game.fly_out()
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         self.assertEqual(self.my_game.winner, "away")
#         self.assertEqual(self.my_game.game_over, True)
#
#     def test_score(self):
#         """Score should be four nil."""
#         self.assertEqual(self.my_game.home.score, 0)
#         self.assertEqual(self.my_game.away.score, 4)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestTriplePlay(unittest.TestCase):
#     """Test what happens when batter hits into triple play."""
#     def setUp(self):
#         """Setup for a triple play."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.triple_play()
#
#     def test_score(self):
#         """Score should be nil nil."""
#         self.assertEqual(self.my_game.home.score, 0)
#         self.assertEqual(self.my_game.away.score, 0)
#
#     def test_inning(self):
#         """Bottom of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, False)
#
#     def test_batting_order(self):
#         """Home team should still be on leadoff hitter. Away team
#         should be on cleanup hitter.
#
#         """
#         self.assertEqual(self.my_game.home.batter, 1)
#         self.assertEqual(self.my_game.away.batter, 4)
#
#     def test_too_many_outs(self):
#         """Test triple play called with too many outs."""
#         self.my_game.ground_out()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.assertRaises(game_exceptions.TooManyOuts,
#                           self.my_game.triple_play)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestCaughtStealingToEndInning(unittest.TestCase):
#     """Test what happens when runner caught stealing to end inning."""
#     def setUp(self):
#         """Get caught stealing to end inning."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.fielders_choice()
#         self.my_game.fly_out()
#         self.my_game.caught_stealing("second")
#
#     def test_score(self):
#         """Score should be nil nil."""
#         self.assertEqual(self.my_game.home.score, 0)
#         self.assertEqual(self.my_game.away.score, 0)
#
#     def test_inning(self):
#         """Bottom of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, False)
#
#     def test_batting_order(self):
#         """Home team should still be on leadoff hitter. Away team
#         should be on cleanup hitter.
#
#         """
#         self.assertEqual(self.my_game.home.batter, 1)
#         self.assertEqual(self.my_game.away.batter, 4)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestLotsOfScoring(unittest.TestCase):
#     """Test what happens when we score lots of runs."""
#     def setUp(self):
#         """Setup lots of scoring."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.hit(1)
#         self.my_game.hit(1)
#         self.my_game.hit(1)
#         self.assertEqual(self.my_game.home.score, 0)
#         self.assertEqual(self.my_game.away.score, 1)
#         self.my_game.fly_out()
#         self.my_game.fly_out()
#         self.my_game.fly_out()
#         # bottom of first
#         self.my_game.hit(2)
#         self.my_game.hit(2)
#         self.my_game.fly_out()
#         self.my_game.fly_out()
#         self.my_game.fly_out()
#         self.assertEqual(self.my_game.home.score, 1)
#         self.assertEqual(self.my_game.away.score, 1)
#         # top of second
#         self.my_game.hit(3)
#         self.my_game.hit(2)
#         self.my_game.fly_out()
#         self.my_game.fly_out()
#         self.my_game.fly_out()
#         self.assertEqual(self.my_game.home.score, 1)
#         self.assertEqual(self.my_game.away.score, 2)
#         # bottom of second
#         self.my_game.hit(1)
#         self.my_game.hit(3)
#         self.my_game.ground_out()
#         self.my_game.fly_out()
#         self.my_game.ground_out()
#         self.assertEqual(self.my_game.home.score, 2)
#         self.assertEqual(self.my_game.away.score, 2)
#         # top of third
#
#     def test_inning(self):
#         """Bottom of the first."""
#         self.assertEqual(self.my_game.inning.number, 3)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_score(self):
#         """Score should be nil nil."""
#         self.assertEqual(self.my_game.home.score, 2)
#         self.assertEqual(self.my_game.away.score, 2)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestTriplePlayWithoutEnoughRunners(unittest.TestCase):
#     """Test what happens when batter hits into triple play in an
#     impossible scenario.
#
#     """
#     def setUp(self):
#         """BStart the game, put one runner on."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.hit(1)
#
#     def test_bad_triple_play(self):
#         """Bad triple play."""
#         self.assertRaises(game_exceptions.NotEnoughRunnersOnBase,
#                           self.my_game.triple_play)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_batting_order(self):
#         """Away team should be on second hitter."""
#         self.assertEqual(self.my_game.away.batter, 2)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestDoublePlayWithoutEnoughRunners(unittest.TestCase):
#     """Test what happens when batter hits into double play in an
#     impossible scenario.
#
#     """
#     def setUp(self):
#         """Start the game."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#
#     def test_bad_double_play(self):
#         """Bad double play."""
#         self.assertRaises(game_exceptions.NotEnoughRunnersOnBase,
#                           self.my_game.double_play)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_batting_order(self):
#         """Away team should be on first hitter."""
#         self.assertEqual(self.my_game.away.batter, 1)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestSacrificeNoOneOn(unittest.TestCase):
#     """Test what happens when batter does a sacrifice for no one."""
#     def setUp(self):
#         """Bad sacrifice."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.assertRaises(game_exceptions.NotEnoughRunnersOnBase,
#                           self.my_game.sacrifice)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_batting_order(self):
#         """Away team should be on first hitter."""
#         self.assertEqual(self.my_game.away.batter, 1)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestSacBuntSingleton(unittest.TestCase):
#     """Test what happens when batter does a sac bunt."""
#     def setUp(self):
#         """Sac Bunt to second."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.sacrifice((0, 1))
#
#     def test_outs(self):
#         """One out."""
#         self.assertEqual(self.my_game.inning.outs, 1)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_batting_order(self):
#         """Away team should be on third hitter."""
#         self.assertEqual(self.my_game.away.batter, 3)
#
#     def test_bases(self):
#         """Man on first."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertNotEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestSeveralBadSacrifices(unittest.TestCase):
#     """Test several impossible sac bunts."""
#     def setUp(self):
#         """Bad Sac Bunts."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.assertRaises(game_exceptions.NoRunnerToAdvance,
#                           self.my_game.sacrifice, (2, 3))
#         self.assertRaises(game_exceptions.NoRunnerToAdvance,
#                           self.my_game.sacrifice, [(1, 2)])
#         self.my_game.steal("second")
#         self.assertRaises(game_exceptions.NoRunnerToAdvance,
#                           self.my_game.sacrifice, [(0, 1)])
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_batting_order(self):
#         """Away team should be on second hitter."""
#         self.assertEqual(self.my_game.away.batter, 2)
#
#     def test_bases(self):
#         """Man on first."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertNotEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestSacWithTwoOuts(unittest.TestCase):
#     """Test another impossible sac bunt."""
#     def setUp(self):
#         """Bad Sac Bunts."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.strike()
#         self.my_game.hit(1)
#         # two outs
#         self.assertRaises(game_exceptions.BadSacrifice,
#                           self.my_game.sacrifice, "first")
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 2)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_batting_order(self):
#         """Away team should be on second hitter."""
#         self.assertEqual(self.my_game.away.batter, 4)
#
#     def test_bases(self):
#         """Man on first."""
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestGoodSac(unittest.TestCase):
#     """Test a good sacrifice."""
#     def setUp(self):
#         """Good Sacrifice."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.hit(1)
#         self.my_game.sacrifice()
#
#     def test_outs(self):
#         """One out."""
#         self.assertEqual(self.my_game.inning.outs, 1)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_batting_order(self):
#         """Away team should be on third hitter."""
#         self.assertEqual(self.my_game.away.batter, 3)
#
#     def test_bases(self):
#         """Man on second."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertNotEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestGoodSacToThird(unittest.TestCase):
#     """Test a good sacrifice."""
#     def setUp(self):
#         """Good Sacrifice."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.hit(2)
#         self.my_game.sacrifice()
#
#     def test_outs(self):
#         """One out."""
#         self.assertEqual(self.my_game.inning.outs, 1)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_batting_order(self):
#         """Away team should be on third hitter."""
#         self.assertEqual(self.my_game.away.batter, 3)
#
#     def test_bases(self):
#         """Man on third."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestGoodSacToThirdSpecific(unittest.TestCase):
#     """Test a good sacrifice."""
#     def setUp(self):
#         """Good Sacrifice."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.hit(2)
#         self.my_game.sacrifice((1, 2))
#
#     def test_outs(self):
#         """One out."""
#         self.assertEqual(self.my_game.inning.outs, 1)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_batting_order(self):
#         """Away team should be on third hitter."""
#         self.assertEqual(self.my_game.away.batter, 3)
#
#     def test_bases(self):
#         """Man on third."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestSqueeze(unittest.TestCase):
#     """Test a squeeze.  Same as tag up on deep fly."""
#     def setUp(self):
#         """Squeeze play."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.hit(3)
#         self.my_game.sacrifice()
#
#     def test_outs(self):
#         """One out."""
#         self.assertEqual(self.my_game.inning.outs, 1)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_batting_order(self):
#         """Away team should be on third hitter."""
#         self.assertEqual(self.my_game.away.batter, 3)
#
#     def test_bases(self):
#         """Bases empty."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_score(self):
#         """Score should be 1 nil."""
#         self.assertEqual(self.my_game.home.score, 0)
#         self.assertEqual(self.my_game.away.score, 1)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestSqueezeSpecific(unittest.TestCase):
#     """Test a squeeze.  Same as tag up on deep fly."""
#     def setUp(self):
#         """Squeeze play."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.hit(3)
#         self.my_game.sacrifice((2, 3))
#
#     def test_outs(self):
#         """One out."""
#         self.assertEqual(self.my_game.inning.outs, 1)
#
#     def test_inning(self):
#         """Top of the first."""
#         self.assertEqual(self.my_game.inning.number, 1)
#         self.assertEqual(self.my_game.inning.top, True)
#
#     def test_batting_order(self):
#         """Away team should be on third hitter."""
#         self.assertEqual(self.my_game.away.batter, 3)
#
#     def test_bases(self):
#         """Bases empty."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_score(self):
#         """Score should be 1 nil."""
#         self.assertEqual(self.my_game.home.score, 0)
#         self.assertEqual(self.my_game.away.score, 1)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestError(unittest.TestCase):
#     """Test a fielder error."""
#     def setUp(self):
#         """Setup an error."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.error(True)
#
#     def test_bases(self):
#         """Man on first."""
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_batting_order(self):
#         """Away team should be on second hitter."""
#         self.assertEqual(self.my_game.away.batter, 2)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestErrorMultipleRunners(unittest.TestCase):
#     """Test a fielder error."""
#     def setUp(self):
#         """Setup an error."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.hit(1)
#         self.my_game.hit(1)
#         self.my_game.hit(1)
#         self.my_game.error(True, [(0, 1), (1, 2), (2, 3)])
#
#     def test_bases(self):
#         """Bases loaded."""
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertNotEqual(self.my_game.bases["second"], 0)
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#
#     def test_batting_order(self):
#         """Away team should be on second hitter."""
#         self.assertEqual(self.my_game.away.batter, 5)
#
#     def test_bad_error(self):
#         """Batter goes to second, others score."""
#         self.my_game.error("second", [(0, 2), (1, 3), (2, 3)])
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertNotEqual(self.my_game.bases["second"], 0)
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#         self.assertEqual(self.my_game.away.score, 3)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestInvalidError(unittest.TestCase):
#     """Test an invalid error, trying to advance runners that don't exist."""
#     def setUp(self):
#         """Setup bad advancing."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.assertRaises(game_exceptions.NoRunnerToAdvance,
#                           self.my_game.error,
#                           True,
#                           advances=[(0, 1), (1, 2), (2, 3)])
#         self.assertRaises(game_exceptions.NoRunnerToAdvance,
#                           self.my_game.error,
#                           advances=[(1, 2), (0, 1)])
#         self.assertRaises(game_exceptions.NoRunnerToAdvance,
#                           self.my_game.error,
#                           advances=[(0, 1)])
#
#     def test_batting_order(self):
#         """Away team should be on second hitter."""
#         self.assertEqual(self.my_game.away.batter, 1)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestPickOff(unittest.TestCase):
#     """Test a pickoff."""
#     def setUp(self):
#         """Setup the pickoff."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.my_game.picked_off("first")
#
#     def test_batting_order(self):
#         """Away team should be on second hitter."""
#         self.assertEqual(self.my_game.away.batter, 2)
#
#     def test_bases(self):
#         """Bases empty."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_outs(self):
#         """One out."""
#         self.assertEqual(self.my_game.inning.outs, 1)
#
#     def test_invalid_pickoff(self):
#         """Test an invalid pickoff."""
#         self.assertRaises(game_exceptions.InvalidPickOff,
#                           self.my_game.picked_off, "first")
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestRunnerAdvancesExtra(unittest.TestCase):
#     """Test case where runner goes more bases than batter."""
#     def setUp(self):
#         """Test runner advancing more than batter."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.hit(1, (0, 2))
#
#     def test_batting_order(self):
#         """Away team should be on third hitter."""
#         self.assertEqual(self.my_game.away.batter, 3)
#
#     def test_bases(self):
#         """First and third."""
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestRunnerAdvancesExtraOnDouble(unittest.TestCase):
#     """Test case where runner goes more bases than batter."""
#     def setUp(self):
#         """Test runner advancing more than batter."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.hit(2, (0, 3))
#
#     def test_batting_order(self):
#         """Away team should be on third hitter."""
#         self.assertEqual(self.my_game.away.batter, 3)
#
#     def test_bases(self):
#         """Man on second."""
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertNotEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_score(self):
#         """Score should be 1 nil."""
#         self.assertEqual(self.my_game.home.score, 0)
#         self.assertEqual(self.my_game.away.score, 1)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestRunnerScoresFromFirstOnSingle(unittest.TestCase):
#     """Test case where runner goes more bases than batter."""
#     def setUp(self):
#         """Test runner advancing more than batter."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.hit(1, (0, 3))
#
#     def test_batting_order(self):
#         """Away team should be on third hitter."""
#         self.assertEqual(self.my_game.away.batter, 3)
#
#     def test_bases(self):
#         """Man on first."""
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_score(self):
#         """Score should be 1 nil."""
#         self.assertEqual(self.my_game.home.score, 0)
#         self.assertEqual(self.my_game.away.score, 1)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestRunnerScoresFromSecondOnSingle(unittest.TestCase):
#     """Test case where runner goes more bases than batter."""
#     def setUp(self):
#         """Test runner advancing more than batter."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.ball()
#         self.my_game.steal("second")
#         self.my_game.hit(1, (1, 3))
#
#     def test_batting_order(self):
#         """Away team should be on third hitter."""
#         self.assertEqual(self.my_game.away.batter, 3)
#
#     def test_bases(self):
#         """Man on first."""
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_score(self):
#         """Score should be 1 nil."""
#         self.assertEqual(self.my_game.home.score, 0)
#         self.assertEqual(self.my_game.away.score, 1)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestGameEndsInTie(unittest.TestCase):
#     """Test what happens in case game ends in tie."""
#     def setUp(self):
#         """Strike out everyone."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         # Strike out EVERYONE!
#         # pylint: disable=C0103
#         # pylint: disable=W0612
#         for x in range(162):
#             self.my_game.strike()
#         self.my_game.end_game()
#
#     def test_score(self):
#         """Score should be nil nil."""
#         self.assertEqual(self.my_game.home.score, 0)
#         self.assertEqual(self.my_game.away.score, 0)
#
#     def test_outs(self):
#         """No outs."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#
#     def test_winner_game_over(self):
#         """No one has won, and the game is over."""
#         self.assertEqual(self.my_game.winner, None)
#         self.assertEqual(self.my_game.game_over, True)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestErrorsCalledWrong(unittest.TestCase):
#     """Test what happens when you call error method with both
#     advance_from and advance_from_to set.
#
#     """
#     def setUp(self):
#         """Simple setup."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#
#     def test_no_runner(self):
#         """Test calling the error advancing non-existent runner."""
#         self.assertRaises(game_exceptions.NoRunnerToAdvance,
#                           self.my_game.error, advances=[(0, 2)])
#
#     def test_bad_advance_from_third(self):
#         """Test calling the error advancing wrong way."""
#         self.my_game.hit(3)
#         self.assertRaises(game_exceptions.InvalidAdvance,
#                           self.my_game.error, advances=[(2, 1)])
#
#     def test_good_advance_from_third(self):
#         """Test calling the error advancing right way."""
#         self.my_game.hit(3)
#         self.my_game.error(advances=[(2, 3)])
#         self.assertEqual(self.my_game.away.score, 1)
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_good_advance_from_second(self):
#         """Test calling the error advancing right way."""
#         self.my_game.hit(2)
#         self.my_game.error(advances=[(1, 2)])
#         self.assertEqual(self.my_game.away.score, 0)
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#
#     def test_advance_second_to_home(self):
#         """Test calling the error advancing right way."""
#         self.my_game.hit(2)
#         self.my_game.error(advances=[(1, 3)])
#         self.assertEqual(self.my_game.away.score, 1)
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_bad_advance_from_second(self):
#         """Test calling the error advancing wrong way."""
#         self.my_game.hit(2)
#         self.assertRaises(game_exceptions.InvalidAdvance,
#                           self.my_game.error, advances=[(1, 1)])
#
#     def test_advance_first_to_second(self):
#         """Test calling the error advancing right way."""
#         self.my_game.hit(1)
#         self.my_game.error(advances=[(0, 1)])
#         self.assertEqual(self.my_game.away.score, 0)
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertNotEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_adv_first2third_home2first(self):
#         """Test calling the error advancing right way."""
#         self.my_game.hit(1)
#         self.my_game.error(True, advances=[(0, 2)])
#         self.assertEqual(self.my_game.away.score, 0)
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#
#     def test_monster_error(self):
#         """Test calling the error advancing right way."""
#         self.my_game.hit(1)
#         self.my_game.error(True, advances=[(0, 3)])
#         self.assertEqual(self.my_game.away.score, 1)
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_bad_advance_from_first(self):
#         """Test calling the error advancing wrong way."""
#         self.my_game.hit(1)
#         self.assertRaises(game_exceptions.InvalidAdvance,
#                           self.my_game.error, advances=[(0, 0)])
#
#     def test_bad_adv_home_to_second(self):
#         """Test calling the error advancing wrong way."""
#         self.my_game.hit(1)
#         self.assertRaises(game_exceptions.InvalidAdvance,
#                           self.my_game.error, True)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestHits(unittest.TestCase):
#     """Test the hit method."""
#     def setUp(self):
#         """Simple setup."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#
#     def test_lead_off_single(self):
#         """Test single."""
#         self.my_game.hit()
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#
#     def test_single_double_triple(self):
#         """Test a single followed by a double."""
#         self.my_game.hit(1)
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#         self.my_game.hit(2)
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertNotEqual(self.my_game.bases["second"], 0)
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#         self.my_game.hit(3)
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#         self.assertEqual(self.my_game.away.score, 2)
#
#     def test_single_first_to_third(self):
#         """Single, then a single and runner advances first to third."""
#         self.my_game.hit(1)
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#         self.my_game.hit(1, (0, 2))
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#         self.my_game.hit(1, [(2, 3), (0, 2)])
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#         self.assertEqual(self.my_game.away.score, 1)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestDoublePlays(unittest.TestCase):
#     """Test various double plays."""
#     def setUp(self):
#         """Simple setup."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#
#     def test_643(self):
#         """Test common double play."""
#         self.my_game.hit()
#         self.my_game.double_play()
#         self.assertEqual(self.my_game.inning.outs, 2)
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#         self.assertEqual(self.my_game.away.batter, 3)
#
#     def test_34_double_play(self):
#         """Out at first, throw out at second."""
#         self.my_game.hit()
#         self.my_game.double_play("first", "second")
#         self.assertEqual(self.my_game.inning.outs, 2)
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertEqual(self.my_game.bases["second"], 0)
#         self.assertEqual(self.my_game.bases["third"], 0)
#         self.assertEqual(self.my_game.away.batter, 3)
#
#     def test_double_play_two_outs(self):
#         """Two outs then double play."""
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.hit()
#         self.assertRaises(game_exceptions.TooManyOuts,
#                           self.my_game.double_play)
#
#     def tearDown(self):
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestSingleNoAdvance(unittest.TestCase):
#     """Test a single with runners on second and third, no advances."""
#     def setUp(self):
#         """Simple setup."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#         self.my_game.hit(1)
#         self.my_game.hit(2)
#         self.assertEqual(self.my_game.bases["first"], 0)
#         self.assertNotEqual(self.my_game.bases["second"], 0)
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#         self.my_game.hit(1, advances=None)
#
#     def test_bases(self):
#         """Test for bases loaded."""
#         self.assertEqual(self.my_game.inning.outs, 0)
#         self.assertNotEqual(self.my_game.bases["first"], 0)
#         self.assertNotEqual(self.my_game.bases["second"], 0)
#         self.assertNotEqual(self.my_game.bases["third"], 0)
#         self.assertEqual(self.my_game.away.batter, 4)
#
#     def test_score(self):
#         """Score should be nil nil."""
#         self.assertEqual(self.my_game.home.score, 0)
#         self.assertEqual(self.my_game.away.score, 0)
#
#     def tearDown(self):
#         """Tear down the setup."""
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()
#
#
# class TestStr(unittest.TestCase):
#     """Testing the string output."""
#     def setUp(self):
#         """Setup a game."""
#         con = init_db(":memory:")
#         self.pla0 = Player("Sandy", "Koufax", 32, league=con)
#         self.pla1 = Player("Willie", "Mays", 24, league=con)
#         self.pla2 = Player("Jackie", "Robinson", 42, league=con)
#         self.pla3 = Player("Ted", "Williams", 9, league=con)
#         self.pla4 = Player("Lou", "Gehrig", 4, league=con)
#         self.pla5 = Player("Honus", "Wagner", 33, league=con)
#         self.pla6 = Player("Hank", "Aaron", 44, league=con)
#         self.pla7 = Player("Mike", "Schmidt", 20, league=con)
#         self.pla8 = Player("Babe", "Ruth", 3, league=con)
#         self.pla9 = Player("Johnny", "Bench", 5, league=con)
#         self.pla10 = Player("Jeff", "Kent", 21, league=con)
#
#         self.team_a = Team("team1", league=con)
#
#         self.pla0.set_team_id(self.team_a.team_id)
#         self.pla1.set_team_id(self.team_a.team_id)
#         self.pla2.set_team_id(self.team_a.team_id)
#         self.pla3.set_team_id(self.team_a.team_id)
#         self.pla4.set_team_id(self.team_a.team_id)
#         self.pla5.set_team_id(self.team_a.team_id)
#         self.pla6.set_team_id(self.team_a.team_id)
#         self.pla7.set_team_id(self.team_a.team_id)
#         self.pla8.set_team_id(self.team_a.team_id)
#         self.pla9.set_team_id(self.team_a.team_id)
#         self.pla10.set_team_id(self.team_a.team_id)
#
#         self.plb0 = Player("Nolan", "Ryan", 34, league=con)
#         self.plb1 = Player("Ricky", "Henderson", 24, league=con)
#         self.plb2 = Player("Ryne", "Sandberg", 23, league=con)
#         self.plb3 = Player("Joe", "DiMaggio", 5, league=con)
#         self.plb4 = Player("Jimmie", "Foxx", 3, league=con)
#         self.plb5 = Player("Robin", "Yount", 19, league=con)
#         self.plb6 = Player("Roberto", "Clemente", 21, league=con)
#         self.plb7 = Player("George", "Brett", 6, league=con)
#         self.plb8 = Player("Frank", "Robinson", 20, league=con)
#         self.plb9 = Player("Yogi", "Berra", 8, league=con)
#         self.plb10 = Player("Mickey", "Mantle", 7, league=con)
#
#         self.team_b = Team("team2", league=con)
#
#         self.plb0.set_team_id(self.team_b.team_id)
#         self.plb1.set_team_id(self.team_b.team_id)
#         self.plb2.set_team_id(self.team_b.team_id)
#         self.plb3.set_team_id(self.team_b.team_id)
#         self.plb4.set_team_id(self.team_b.team_id)
#         self.plb5.set_team_id(self.team_b.team_id)
#         self.plb6.set_team_id(self.team_b.team_id)
#         self.plb7.set_team_id(self.team_b.team_id)
#         self.plb8.set_team_id(self.team_b.team_id)
#         self.plb9.set_team_id(self.team_b.team_id)
#         self.plb10.set_team_id(self.team_b.team_id)
#
#         self.my_game = Game(self.team_a.team_id, self.team_b.team_id, con)
#
#     def test_str_output(self):
#         """Test that the game can be printed."""
#         self.assertEqual("It's the top of 1", str(self.my_game)[:17])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the bottom of 1", str(self.my_game)[:20])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the top of 2", str(self.my_game)[:17])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the bottom of 2", str(self.my_game)[:20])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the top of 3", str(self.my_game)[:17])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the bottom of 3", str(self.my_game)[:20])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the top of 4", str(self.my_game)[:17])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the bottom of 4", str(self.my_game)[:20])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the top of 5", str(self.my_game)[:17])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the bottom of 5", str(self.my_game)[:20])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the top of 6", str(self.my_game)[:17])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the bottom of 6", str(self.my_game)[:20])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the top of 7", str(self.my_game)[:17])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the bottom of 7", str(self.my_game)[:20])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the top of 8", str(self.my_game)[:17])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the bottom of 8", str(self.my_game)[:20])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the top of 9", str(self.my_game)[:17])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the bottom of 9", str(self.my_game)[:20])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the top of 10", str(self.my_game)[:18])
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.my_game.ground_out()
#         self.assertEqual("It's the bottom of 10", str(self.my_game)[:21])
#         self.my_game.hit(4)
#         self.assertEqual("The game is over", str(self.my_game)[:16])
#
#     def tearDown(self):
#         """Tear down the setup."""
#         self.team_a.delete()
#         self.pla0.delete()
#         self.pla1.delete()
#         self.pla2.delete()
#         self.pla3.delete()
#         self.pla4.delete()
#         self.pla5.delete()
#         self.pla6.delete()
#         self.pla7.delete()
#         self.pla8.delete()
#         self.pla9.delete()
#         self.pla10.delete()
#         self.team_b.delete()
#         self.plb0.delete()
#         self.plb1.delete()
#         self.plb2.delete()
#         self.plb3.delete()
#         self.plb4.delete()
#         self.plb5.delete()
#         self.plb6.delete()
#         self.plb7.delete()
#         self.plb8.delete()
#         self.plb9.delete()
#         self.plb10.delete()

if __name__ == '__main__':
    unittest.main()