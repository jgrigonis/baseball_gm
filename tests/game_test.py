# pylint: disable=C0302
# pylint complains about the number of lines in the method.
"""Unit Tests for the Game class."""
import unittest

from src.game.main import Game
import src.game.game_exceptions as game_exceptions
from src.player.player import Player
from src.team.team import Team

# pylint: disable=R0904
# pylint complains about the number of public methods.
# pylint: disable=R0902
# pylint complains about the number of instance attributes.
# pylint: disable=R0915
# pylint complains about the number of statements.


class GameTestBase(unittest.TestCase):
    """Game test base."""

    def setUp(self):
        """Setup the game test base."""
        home = Team("home", "team")
        home.load_team()
        home.set_lineup()
        away = Team("away", "team")
        away.load_team()
        away.set_lineup()
        self.my_game = Game(home, away)


class FakeRNG:
    def __init__(self, values):
        self.values = iter(values)

    def random(self):
        return next(self.values)
    
class TestDefense(GameTestBase):

    def setUp(self):
        super().setUp()
        self.simple_player = Player("Willie", "Mays")


    def test_defensive_play_success(self):
        self.my_game.rng = FakeRNG([0.99])  # no error

        success, error = self.my_game.check_defensive_play(
            defender=self.simple_player,
            play_type="fielding",
            position="ss",
        )

        assert success is True
        assert error is None
    
    def test_defensive_play_error(self):
        self.my_game.rng = FakeRNG([0.001])  # guaranteed error

        success, error = self.my_game.check_defensive_play(
            defender=self.simple_player,
            play_type="fielding",
            position="ss",
        )

        assert success is False
        assert error == "error"
        assert self.simple_player.stats.fielding.errors == 1

    def test_defensive_play_too_slow(self):
        self.my_game.rng = FakeRNG([0.99, 0.001])  # no error, but slow

        success, error = self.my_game.check_defensive_play(
            defender=self.simple_player,
            play_type="both",
            position="ss",
        )

        assert success is False
        assert error == "slow"


class TestInitAnd26Balls(GameTestBase):
    """Fairly boring, just testing the init."""

    def setUp(self):
        """Setup the test."""
        super().setUp()
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
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

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
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertNotEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)

    def test_score_three(self):
        """6 walks should have been issued, leading to 3 scores."""
        # pylint: disable=C0103
        # pylint: disable=W0612
        for _ in range(26):
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


class TestTeamCycles(GameTestBase):
    """Test what happens if the team leads off with a single, double,
    triple and home run in order.

    """

    def setUp(self):
        """Setup instance of Game and have 4 hits in a row."""
        super().setUp()
        game = self.my_game
        game.hit(1)
        game.hit(2)
        game.hit(3)
        game.hit(4)

    def test_score(self):
        """First four batters have all scored."""
        self.assertEqual(self.my_game.score.away, 4)

    def test_outs(self):
        """No outs yet."""
        self.assertEqual(self.my_game.inning.outs, 0)


class TestSingleDoublePlayHitByPitch(GameTestBase):
    """Test what happens if the team leads off with a single, followed
    by a double play, and then a hit batter.

    """

    def setUp(self):
        """Setup instance of Game and have 4 hits in a row."""
        super().setUp()        
        self.my_game.rng = FakeRNG([0.99, 0.99, 0.99])  # no errors
        self.my_game.hit(1)
        self.my_game.double_play("second", "first")
        self.my_game.hit_by_pitch()

    def test_score(self):
        """No score."""
        self.assertEqual(self.my_game.score.away, 0)

    def test_outs(self):
        """Two outs."""
        self.assertEqual(self.my_game.inning.outs, 2)

    def test_bases(self):
        """Hit batter on first."""
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)


class TestMiraclePitching(GameTestBase):
    """Test what happens if the pitchers combine to throw 162
    straight strikes.  2 perfect games should leave us in the
    top of the 10th.

    """

    def setUp(self):
        """Setup instance of Game and have 162 strikes in a row."""
        super().setUp()
        # pylint: disable=C0103
        # pylint: disable=W0612
        for _ in range(162):
            self.my_game.strike()

    def test_score(self):
        """No score."""
        self.assertEqual(self.my_game.score.away, 0)
        self.assertEqual(self.my_game.score.home, 0)

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_inning(self):
        """Start of the top of the tenth."""
        self.assertEqual(self.my_game.inning.number, 10)
        self.assertEqual(self.my_game.inning.top, True)


class TestAway3Up3DownHomeHomerStrikeOutGroundOut(GameTestBase):
    """Test what happens if the away team goes three up, three down.
    Then the home team hits homer, then strikes out, then grounds out.

    """

    def setUp(self):
        """Setup the described scenario."""
        super().setUp()
        self.my_game.rng = FakeRNG([0.99, 0.99, 0.99])  # no error
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.fly_out()
        self.my_game.ground_out()
        self.my_game.hit(4)
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.ground_out()

    def test_score(self):
        """1-0 Home."""
        self.assertEqual(self.my_game.score.away, 0)
        self.assertEqual(self.my_game.score.home, 1)

    def test_outs(self):
        """2 outs."""
        self.assertEqual(self.my_game.inning.outs, 2)

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_inning(self):
        """Bottom of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, False)

    def test_game_over(self):
        """Test that the game is not over, and the winner is
        still None.

        """
        self.assertEqual(self.my_game.winner, None)
        self.assertEqual(self.my_game.game_over, False)


class TestBottom9thHomeWin(GameTestBase):
    """Test what happens if the bottom of the 9th comes and the
    home team is already winning.

    """

    def setUp(self):
        """Setup instance of Game and have a homer after 135 strike (45 outs)."""
        super().setUp()

        # 7 1/2 inning scoreless
        # pylint: disable=C0103
        # pylint: disable=W0612
        for _ in range(135):
            self.my_game.strike()
        # bottom 8th lead off homer
        self.my_game.hit(4)
        # remainder bottom 8th and top 9th scoreless
        # pylint: disable=C0103
        # pylint: disable=W0612
        for _ in range(18):
            self.my_game.strike()

    def test_score(self):
        """1-0 Home."""
        self.assertEqual(self.my_game.score.away, 0)
        self.assertEqual(self.my_game.score.home, 1)

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_inning(self):
        """Stays in Top of the ninth, game is now over.
        The inning is no longer updated on game over."""
        self.assertEqual(self.my_game.inning.number, 9)
        self.assertEqual(self.my_game.inning.top, True)

    def test_game_over(self):
        """Test that the game is over, and that home team won."""
        self.assertEqual(self.my_game.winner, self.my_game.home)
        self.assertEqual(self.my_game.game_over, True)


class TestLeadOffHomer(GameTestBase):
    """Test what happens if the lead off hitter hits a homer."""

    def setUp(self):
        """Setup Game with leadoff homer with the count of 1-1."""
        super().setUp()
        self.my_game.strike()
        self.my_game.ball()
        self.my_game.hit(4)

    def test_score(self):
        """1-0 Away."""
        self.assertEqual(self.my_game.score.away, 1)
        self.assertEqual(self.my_game.score.home, 0)

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)

    def test_game_over(self):
        """Test that the game is not over, and the winner is
        still None.

        """
        self.assertEqual(self.my_game.winner, None)
        self.assertEqual(self.my_game.game_over, False)


class TestLeadOffHomerHomeTeam(GameTestBase):
    """Test what happens if the lead off hitter hits a homer
    for the home team.

    """

    def setUp(self):
        """Setup Game with leadoff homer with the count of 1-1."""
        super().setUp()
        # Away Team 3 up 3 down
        self.my_game._put_out(next=True)
        self.my_game._put_out(next=True)
        self.my_game._put_out(next=True)
        # get the count to 1-1
        self.my_game.strike()
        self.my_game.ball()
        # hit a homer
        self.my_game.hit(4)

    def test_score(self):
        """1-0 Away."""
        self.assertEqual(self.my_game.score.away, 0)
        self.assertEqual(self.my_game.score.home, 1)

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_inning(self):
        """Bottom of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, False)

    def test_game_over(self):
        """Test that the game is not over, and the winner is
        still None.

        """
        self.assertEqual(self.my_game.winner, None)
        self.assertEqual(self.my_game.game_over, False)


class TestFoulBalls(GameTestBase):
    """Test what happens when hitter start fouling balls off."""

    def setUp(self):
        """Setup Game with strikes and foul balls and balls."""
        super().setUp()
        self.my_game.strike()  # 0-1
        self.my_game.foul_ball()  # 0-2
        self.my_game.foul_ball()  # 0-2 still
        self.my_game.ball()  # 1-2
        self.my_game.foul_ball()  # 1-2 still
        self.my_game.ball()  # 2-2
        self.my_game.ball()  # 3-2

    def test_count(self):
        """Count should be full."""
        self.assertEqual(self.my_game.count.balls, 3)
        self.assertEqual(self.my_game.count.strikes, 2)

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)


class TestStealingBases(GameTestBase):
    """Test what happens when runners start stealing."""

    def setUp(self):
        """Setup Game with strikes and foul balls and balls.

        I put some asserts in this one, for fun.

        """
        super().setUp()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.steal("second")
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertNotEqual(self.my_game.bases[1], 0)
        self.my_game.strike()
        self.my_game.steal("third")
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)
        self.my_game.strike()
        self.my_game.steal("home")
        self.my_game.ball()

    def test_count(self):
        """Count should be 1-2."""
        self.assertEqual(self.my_game.count.balls, 1)
        self.assertEqual(self.my_game.count.strikes, 2)

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)

    def test_score(self):
        """Test score."""
        self.assertEqual(self.my_game.score.home, 0)
        self.assertEqual(self.my_game.score.away, 1)

    def test_invalid_steal(self):
        """Test invalid steal."""
        self.assertRaises(game_exceptions.InvalidSteal, self.my_game.steal, 1)


class TestCaughtStealingBases(GameTestBase):
    """Test what happens when runners get caught stealing."""

    def setUp(self):
        """Runner hits for single, steals second, caught at third."""
        super().setUp()
        self.my_game.strike()
        self.my_game.ball()
        self.my_game.foul_ball()
        self.my_game.ball()
        self.my_game.hit(1)
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.my_game.steal("second")
        self.assertNotEqual(self.my_game.bases[1], 0)
        self.my_game.strike()
        self.assertEqual(self.my_game.inning.outs, 0)
        self.my_game.caught_stealing("third")
        self.my_game.strike()

    def test_count(self):
        """Count should be 0-2."""
        self.assertEqual(self.my_game.count.balls, 0)
        self.assertEqual(self.my_game.count.strikes, 2)

    def test_outs(self):
        """One out."""
        self.assertEqual(self.my_game.inning.outs, 1)

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_invalid_cs(self):
        """Test an invalid caught stealing."""
        self.assertRaises(
            game_exceptions.InvalidSteal, self.my_game.caught_stealing, "home"
        )

    def test_another_invalid(self):
        """Test another invalid stealing."""
        self.assertRaises(
            game_exceptions.InvalidSteal, self.my_game.caught_stealing, "second"
        )

    def test_invalid_base(self):
        """Test another invalid stealing."""
        self.assertRaises(game_exceptions.InvalidBase, self.my_game.caught_stealing, 4)


class TestCaughtStealingSecondAndHome(GameTestBase):
    """Test what happens when runners get caught stealing."""

    def setUp(self):
        """Runner hits for single, caught stealing second, next batter
        triples, but caught stealing home.

        """
        super().setUp()
        self.my_game.strike()
        self.my_game.ball()
        self.my_game.foul_ball()
        self.my_game.ball()
        self.my_game.hit(1)
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.my_game.caught_stealing("second")
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.my_game.strike()
        self.assertEqual(self.my_game.inning.outs, 1)
        self.my_game.ball()
        self.my_game.hit(3)
        self.my_game.caught_stealing("home")
        self.my_game.strike()

    def test_count(self):
        """Count should be 0-1."""
        self.assertEqual(self.my_game.count.balls, 0)
        self.assertEqual(self.my_game.count.strikes, 1)

    def test_outs(self):
        """Two outs."""
        self.assertEqual(self.my_game.inning.outs, 2)

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)


class TestBalks(GameTestBase):
    """Test what happens when runners gets balked around the bases."""

    def setUp(self):
        """Runner hits for single, then pitcher balks 3 straight times."""
        super().setUp()
        self.my_game.hit(1)
        self.my_game.balk()
        self.my_game.balk()
        self.my_game.balk()

    def test_count(self):
        """Count should be empty."""
        self.assertEqual(self.my_game.count.balls, 0)
        self.assertEqual(self.my_game.count.strikes, 0)

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_score(self):
        """1-0 Away."""
        self.assertEqual(self.my_game.score.away, 1)
        self.assertEqual(self.my_game.score.home, 0)

    def test_bases_empty(self):
        """Test a balk with bases empty."""
        self.my_game.balk()
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)


class TestFieldersChoiceRetiresSide(GameTestBase):
    """Test what happens when runner gets forced out for third out."""

    def setUp(self):
        """Runner hits for single, two fly outs then fielders choice."""
        super().setUp()
        self.my_game.hit(1)
        self.my_game.fly_out()
        self.my_game.fly_out()
        self.my_game.fielders_choice("second")

    def test_count(self):
        """Count should be empty."""
        self.assertEqual(self.my_game.count.balls, 0)
        self.assertEqual(self.my_game.count.strikes, 0)

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)


class TestDoublePlayToEndInning(GameTestBase):
    """Test what happens when batter hits into double play with one out."""

    def setUp(self):
        """Runner hits for single, next batter strikes out, then DP."""
        super().setUp()
        self.my_game.rng = FakeRNG([0.99, 0.99, 0.99])  # no errors
        self.my_game.hit(1)
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.double_play()

    def test_count(self):
        """Count should be empty."""
        self.assertEqual(self.my_game.count.balls, 0)
        self.assertEqual(self.my_game.count.strikes, 0)

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_inning(self):
        """Bottom of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, False)


class TestFieldersChoiceNoOuts(GameTestBase):
    """Test what happens when batter hits into fielder's choice with no outs."""

    def setUp(self):
        """Runner hits for single, next batter hits into fielder's choice."""
        super().setUp()
        self.my_game.hit(1)
        self.my_game.fielders_choice("second")

    def test_count(self):
        """Count should be empty."""
        self.assertEqual(self.my_game.count.balls, 0)
        self.assertEqual(self.my_game.count.strikes, 0)

    def test_outs(self):
        """One out."""
        self.assertEqual(self.my_game.inning.outs, 1)

    def test_bases(self):
        """Man on first."""
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)


class TestAwayTeamWins(GameTestBase):
    """Test what happens when away team wins."""

    def setUp(self):
        """Away team wins with grand slam home run in second inning."""
        super().setUp()
        self.my_game.rng = FakeRNG([0.99] * 50)  # no errors
        # top of first
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.ground_out()
        self.my_game.fly_out()
        # bottom of first
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, False)
        self.my_game.hit(1)
        self.my_game.fielders_choice("second")
        self.my_game.double_play()
        # top of second
        self.assertEqual(self.my_game.inning.number, 2)
        self.assertEqual(self.my_game.inning.top, True)
        self.my_game.strike()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.my_game.hit(1)
        self.assertNotEqual(self.my_game.bases[1], 0)
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.assertNotEqual(self.my_game.bases[2], 0)
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.ball()
        self.my_game.ball()
        # grand slam
        self.my_game.hit(4)
        self.assertEqual(self.my_game.score.away, 4)
        self.my_game.ground_out()
        self.my_game.fly_out()
        self.my_game.ground_out()
        # bottom of second
        self.assertEqual(self.my_game.inning.number, 2)
        self.assertEqual(self.my_game.inning.top, False)
        self.my_game.fly_out()
        self.my_game.ground_out()
        self.my_game.fly_out()
        # top of third
        self.assertEqual(self.my_game.inning.number, 3)
        self.assertEqual(self.my_game.inning.top, True)
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.ground_out()
        self.my_game.fly_out()
        # bottom of third
        self.assertEqual(self.my_game.inning.number, 3)
        self.assertEqual(self.my_game.inning.top, False)
        self.my_game.ground_out()
        self.my_game.fly_out()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        # top of fourth
        self.assertEqual(self.my_game.inning.number, 4)
        self.assertEqual(self.my_game.inning.top, True)
        self.my_game.hit(1)
        self.my_game.hit(1)
        self.my_game.triple_play()
        # bottom of fourth
        self.assertEqual(self.my_game.inning.number, 4)
        self.assertEqual(self.my_game.inning.top, False)
        self.my_game.hit(1)
        self.my_game.double_play()
        self.my_game.hit(1)
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        # top of fifth
        self.assertEqual(self.my_game.inning.number, 5)
        self.assertEqual(self.my_game.inning.top, True)
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        # bottom of fifth
        self.assertEqual(self.my_game.inning.number, 5)
        self.assertEqual(self.my_game.inning.top, False)
        self.my_game.ground_out()
        self.my_game.fly_out()
        self.my_game.ground_out()
        # top of sixth
        self.my_game.fly_out()
        self.my_game.ground_out()
        self.my_game.fly_out()
        # bottom of sixth
        self.my_game.ground_out()
        self.my_game.fly_out()
        self.my_game.ground_out()
        # top of seventh
        self.my_game.fly_out()
        self.my_game.ground_out()
        self.my_game.fly_out()
        # bottom of seventh
        self.my_game.ground_out()
        self.my_game.fly_out()
        self.my_game.ground_out()
        # top of eighth
        self.my_game.fly_out()
        self.my_game.ground_out()
        self.my_game.fly_out()
        # bottom of eighth
        self.my_game.ground_out()
        self.my_game.fly_out()
        self.my_game.ground_out()
        # top of ninth
        self.my_game.fly_out()
        self.my_game.ground_out()
        self.my_game.fly_out()
        # bottom of ninth
        self.assertEqual(self.my_game.inning.number, 9)
        self.assertEqual(self.my_game.inning.top, False)
        self.assertEqual(self.my_game.winner, None)
        self.assertEqual(self.my_game.game_over, False)
        self.my_game.fly_out()
        self.my_game.ground_out()
        self.my_game.fly_out()
        self.assertEqual(self.my_game.winner, self.my_game.away)
        self.assertEqual(self.my_game.game_over, True)

    def test_score(self):
        """Score should be four nil."""
        self.assertEqual(self.my_game.score.home, 0)
        self.assertEqual(self.my_game.score.away, 4)


class TestTriplePlay(GameTestBase):
    """Test what happens when batter hits into triple play."""

    def setUp(self):
        """Setup for a triple play."""
        super().setUp()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.triple_play()

    def test_score(self):
        """Score should be nil nil."""
        self.assertEqual(self.my_game.score.home, 0)
        self.assertEqual(self.my_game.score.away, 0)

    def test_inning(self):
        """Bottom of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, False)

    def test_too_many_outs(self):
        """Test triple play called with too many outs."""
        self.my_game.ground_out()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.assertRaises(game_exceptions.TooManyOuts, self.my_game.triple_play)


class TestCaughtStealingToEndInning(GameTestBase):
    """Test what happens when runner caught stealing to end inning."""

    def setUp(self):
        """Get caught stealing to end inning."""
        super().setUp()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.fielders_choice()
        self.my_game.fly_out()
        self.my_game.caught_stealing("second")

    def test_score(self):
        """Score should be nil nil."""
        self.assertEqual(self.my_game.score.home, 0)
        self.assertEqual(self.my_game.score.away, 0)

    def test_inning(self):
        """Bottom of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, False)


class TestLotsOfScoring(GameTestBase):
    """Test what happens when we score lots of runs."""

    def setUp(self):
        """Setup lots of scoring."""
        super().setUp()
        self.my_game.rng = FakeRNG([0.99] * 50)  # no errors
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.hit(1)
        self.my_game.hit(1)
        self.my_game.hit(1)
        self.assertEqual(self.my_game.score.home, 0)
        self.assertEqual(self.my_game.score.away, 1)
        self.my_game.fly_out()
        self.my_game.fly_out()
        self.my_game.fly_out()
        # bottom of first
        self.my_game.hit(2)
        self.my_game.hit(2)
        self.my_game.fly_out()
        self.my_game.fly_out()
        self.my_game.fly_out()
        self.assertEqual(self.my_game.score.home, 1)
        self.assertEqual(self.my_game.score.away, 1)
        # top of second
        self.my_game.hit(3)
        self.my_game.hit(2)
        self.my_game.fly_out()
        self.my_game.fly_out()
        self.my_game.fly_out()
        self.assertEqual(self.my_game.score.home, 1)
        self.assertEqual(self.my_game.score.away, 2)
        # bottom of second
        self.my_game.hit(1)
        self.my_game.hit(3)
        self.my_game.ground_out()
        self.my_game.fly_out()
        self.my_game.ground_out()
        self.assertEqual(self.my_game.score.home, 2)
        self.assertEqual(self.my_game.score.away, 2)
        # top of third

    def test_inning(self):
        """Bottom of the first."""
        self.assertEqual(self.my_game.inning.number, 3)
        self.assertEqual(self.my_game.inning.top, True)

    def test_score(self):
        """Score should be nil nil."""
        self.assertEqual(self.my_game.score.home, 2)
        self.assertEqual(self.my_game.score.away, 2)


class TestTriplePlayWithoutEnoughRunners(GameTestBase):
    """Test what happens when batter hits into triple play in an
    impossible scenario.

    """

    def setUp(self):
        """BStart the game, put one runner on."""
        super().setUp()
        self.my_game.hit(1)

    def test_bad_triple_play(self):
        """Bad triple play."""
        self.assertRaises(
            game_exceptions.NotEnoughRunnersOnBase, self.my_game.triple_play
        )

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)


class TestDoublePlayWithoutEnoughRunners(GameTestBase):
    """Test what happens when batter hits into double play in an
    impossible scenario.

    """

    def setUp(self):
        """Start the game."""
        super().setUp()

    def test_bad_double_play(self):
        """Bad double play."""
        self.assertRaises(
            game_exceptions.NotEnoughRunnersOnBase, self.my_game.double_play
        )

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)


class TestSacrificeNoOneOn(GameTestBase):
    """Test what happens when batter does a sac_fly for no one."""

    def setUp(self):
        """Bad sac_fly."""
        super().setUp()
        self.assertRaises(game_exceptions.NotEnoughRunnersOnBase, self.my_game.sac_fly)

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)


class TestSacBuntSingleton(GameTestBase):
    """Test what happens when batter does a sac_fly."""

    def setUp(self):
        """Sac Fly to second."""
        super().setUp()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.sac_fly((0, 1))

    def test_outs(self):
        """One out."""
        self.assertEqual(self.my_game.inning.outs, 1)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)

    def test_bases(self):
        """Man on first."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertNotEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)


class TestSeveralBadSacrifices(GameTestBase):
    """Test several impossible sac_flys"""

    def setUp(self):
        """Bad Sac Fly."""
        super().setUp()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.assertRaises(
            game_exceptions.NoRunnerToAdvance, self.my_game.sac_fly, (2, 3)
        )
        self.assertRaises(
            game_exceptions.NoRunnerToAdvance, self.my_game.sac_fly, [(1, 2)]
        )
        self.my_game.steal("second")
        self.assertRaises(
            game_exceptions.NoRunnerToAdvance, self.my_game.sac_fly, [(0, 1)]
        )

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)

    def test_bases(self):
        """Man on first."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertNotEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)


class TestSacWithTwoOuts(GameTestBase):
    """Test another impossible sac_fly."""

    def setUp(self):
        """Bad Sac Flies."""
        super().setUp()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.strike()
        self.my_game.hit(1)
        # two outs
        self.assertRaises(game_exceptions.BadSacrifice, self.my_game.sac_fly, "first")

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 2)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)

    def test_bases(self):
        """Man on first."""
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)


class TestGoodSac(GameTestBase):
    """Test a good sac_fly."""

    def setUp(self):
        """Good Sacrifice."""
        super().setUp()
        self.my_game.hit(1)
        self.my_game.sac_fly()

    def test_outs(self):
        """One out."""
        self.assertEqual(self.my_game.inning.outs, 1)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)

    def test_bases(self):
        """Man on second."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertNotEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)


class TestGoodSacToThird(GameTestBase):
    """Test a good sac_fly."""

    def setUp(self):
        """Good Sacrifice."""
        super().setUp()
        self.my_game.hit(2)
        self.my_game.sac_fly()

    def test_outs(self):
        """One out."""
        self.assertEqual(self.my_game.inning.outs, 1)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)

    def test_bases(self):
        """Man on third."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)


class TestGoodSacToThirdSpecific(GameTestBase):
    """Test a good sac_fly."""

    def setUp(self):
        """Good Sacrifice."""
        super().setUp()
        self.my_game.hit(2)
        self.my_game.sac_fly((1, 2))

    def test_outs(self):
        """One out."""
        self.assertEqual(self.my_game.inning.outs, 1)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)

    def test_bases(self):
        """Man on third."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)


class TestSqueeze(GameTestBase):
    """Test a squeeze.  Same as tag up on deep fly."""

    def setUp(self):
        """Squeeze play."""
        super().setUp()
        self.my_game.hit(3)
        self.my_game.sac_fly()

    def test_outs(self):
        """One out."""
        self.assertEqual(self.my_game.inning.outs, 1)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_score(self):
        """Score should be 1 nil."""
        self.assertEqual(self.my_game.score.home, 0)
        self.assertEqual(self.my_game.score.away, 1)


class TestSqueezeSpecific(GameTestBase):
    """Test a squeeze.  Same as tag up on deep fly."""

    def setUp(self):
        """Squeeze play."""
        super().setUp()
        self.my_game.hit(3)
        self.my_game.sac_fly((2, 3))

    def test_outs(self):
        """One out."""
        self.assertEqual(self.my_game.inning.outs, 1)

    def test_inning(self):
        """Top of the first."""
        self.assertEqual(self.my_game.inning.number, 1)
        self.assertEqual(self.my_game.inning.top, True)

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_score(self):
        """Score should be 1 nil."""
        self.assertEqual(self.my_game.score.home, 0)
        self.assertEqual(self.my_game.score.away, 1)


class TestError(GameTestBase):
    """Test a fielder error."""

    def setUp(self):
        """Setup an error."""
        super().setUp()
        self.my_game.error(True)

    def test_bases(self):
        """Man on first."""
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)


class TestErrorMultipleRunners(GameTestBase):
    """Test a fielder error."""

    def setUp(self):
        """Setup an error."""
        super().setUp()
        self.my_game.hit(1)
        self.my_game.hit(1)
        self.my_game.hit(1)
        self.my_game.error(True, [(0, 1), (1, 2), (2, 3)])

    def test_bases(self):
        """Bases loaded."""
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertNotEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)

    def test_bad_error(self):
        """Batter goes to second, others score."""
        self.my_game.error("second", [(0, 2), (1, 3), (2, 3)])
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertNotEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)
        self.assertEqual(self.my_game.score.away, 3)


class TestInvalidError(GameTestBase):
    """Test an invalid error, trying to advance runners that don't exist."""

    def setUp(self):
        """Setup bad advancing."""
        super().setUp()
        self.assertRaises(
            game_exceptions.NoRunnerToAdvance,
            self.my_game.error,
            True,
            advances=[(0, 1), (1, 2), (2, 3)],
        )
        self.assertRaises(
            game_exceptions.NoRunnerToAdvance,
            self.my_game.error,
            advances=[(1, 2), (0, 1)],
        )
        self.assertRaises(
            game_exceptions.NoRunnerToAdvance, self.my_game.error, advances=[(0, 1)]
        )


class TestPickOff(GameTestBase):
    """Test a pickoff."""

    def setUp(self):
        """Setup the pickoff."""
        super().setUp()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.my_game.picked_off("first")

    def test_bases(self):
        """Bases empty."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_outs(self):
        """One out."""
        self.assertEqual(self.my_game.inning.outs, 1)

    def test_invalid_pickoff(self):
        """Test an invalid pickoff."""
        self.assertRaises(
            game_exceptions.InvalidPickOff, self.my_game.picked_off, "first"
        )


class TestRunnerAdvancesExtra(GameTestBase):
    """Test case where runner goes more bases than batter."""

    def setUp(self):
        """Test runner advancing more than batter."""
        super().setUp()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.hit(1, [(0, 2)])

    def test_bases(self):
        """First and third."""
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)


class TestRunnerAdvancesExtraOnDouble(GameTestBase):
    """Test case where runner goes more bases than batter."""

    def setUp(self):
        """Test runner advancing more than batter."""
        super().setUp()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.hit(2, [(0, 3)])

    def test_bases(self):
        """Man on second."""
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertNotEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_score(self):
        """Score should be 1 nil."""
        self.assertEqual(self.my_game.score.home, 0)
        self.assertEqual(self.my_game.score.away, 1)


class TestRunnerScoresFromFirstOnSingle(GameTestBase):
    """Test case where runner goes more bases than batter."""

    def setUp(self):
        """Test runner advancing more than batter."""
        super().setUp()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.hit(1, [(0, 3)])

    def test_bases(self):
        """Man on first."""
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_score(self):
        """Score should be 1 nil."""
        self.assertEqual(self.my_game.score.home, 0)
        self.assertEqual(self.my_game.score.away, 1)


class TestRunnerScoresFromSecondOnSingle(GameTestBase):
    """Test case where runner goes more bases than batter."""

    def setUp(self):
        """Test runner advancing more than batter."""
        super().setUp()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.ball()
        self.my_game.steal("second")
        self.my_game.hit(1, [(1, 3)])

    def test_bases(self):
        """Man on first."""
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_score(self):
        """Score should be 1 nil."""
        self.assertEqual(self.my_game.score.home, 0)
        self.assertEqual(self.my_game.score.away, 1)


class TestGameEndsInTie(GameTestBase):
    """Test what happens in case game ends in tie."""

    def setUp(self):
        """Strike out everyone."""
        super().setUp()
        # Strike out EVERYONE!
        # pylint: disable=C0103
        # pylint: disable=W0612
        for _ in range(162):
            self.my_game.strike()
        self.my_game._end_game()

    def test_score(self):
        """Score should be nil nil."""
        self.assertEqual(self.my_game.score.home, 0)
        self.assertEqual(self.my_game.score.away, 0)

    def test_outs(self):
        """No outs."""
        self.assertEqual(self.my_game.inning.outs, 0)

    def test_winner_game_over(self):
        """No one has won, and the game is over."""
        self.assertEqual(self.my_game.winner, None)
        self.assertEqual(self.my_game.game_over, True)


class TestErrorsCalledWrong(GameTestBase):
    """Test what happens when you call error method with both
    advance_from and advance_from_to set.

    """

    def setUp(self):
        """Simple setup."""
        super().setUp()

    def test_no_runner(self):
        """Test calling the error advancing non-existent runner."""
        self.assertRaises(
            game_exceptions.NoRunnerToAdvance, self.my_game.error, advances=[(0, 2)]
        )

    def test_bad_advance_from_third(self):
        """Test calling the error advancing wrong way."""
        self.my_game.hit(3)
        self.assertRaises(
            game_exceptions.InvalidAdvance, self.my_game.error, advances=[(2, 1)]
        )

    def test_good_advance_from_third(self):
        """Test calling the error advancing right way."""
        self.my_game.hit(3)
        self.my_game.error(advances=[(2, 3)])
        self.assertEqual(self.my_game.score.away, 1)
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_good_advance_from_second(self):
        """Test calling the error advancing right way."""
        self.my_game.hit(2)
        self.my_game.error(advances=[(1, 2)])
        self.assertEqual(self.my_game.score.away, 0)
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)

    def test_advance_second_to_home(self):
        """Test calling the error advancing right way."""
        self.my_game.hit(2)
        self.my_game.error(advances=[(1, 3)])
        self.assertEqual(self.my_game.score.away, 1)
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_bad_advance_from_second(self):
        """Test calling the error advancing wrong way."""
        self.my_game.hit(2)
        self.assertRaises(
            game_exceptions.InvalidAdvance, self.my_game.error, advances=[(1, 1)]
        )

    def test_advance_first_to_second(self):
        """Test calling the error advancing right way."""
        self.my_game.hit(1)
        self.my_game.error(advances=[(0, 1)])
        self.assertEqual(self.my_game.score.away, 0)
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertNotEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_adv_first2third_home2first(self):
        """Test calling the error advancing right way."""
        self.my_game.hit(1)
        self.my_game.error(True, advances=[(0, 2)])
        self.assertEqual(self.my_game.score.away, 0)
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)

    def test_monster_error(self):
        """Test calling the error advancing right way."""
        self.my_game.hit(1)
        self.my_game.error(True, advances=[(0, 3)])
        self.assertEqual(self.my_game.score.away, 1)
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_bad_advance_from_first(self):
        """Test calling the error advancing wrong way."""
        self.my_game.hit(1)
        self.assertRaises(
            game_exceptions.InvalidAdvance, self.my_game.error, advances=[(0, 0)]
        )

    def test_bad_adv_home_to_second(self):
        """Test calling the error advancing wrong way."""
        self.my_game.hit(1)
        self.assertRaises(game_exceptions.InvalidAdvance, self.my_game.error, True)


class TestHits(GameTestBase):
    """Test the hit method."""

    def setUp(self):
        """Simple setup."""
        super().setUp()

    def test_lead_off_single(self):
        """Test single."""
        self.my_game.hit()
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_single_double_triple(self):
        """Test a single followed by a double."""
        self.my_game.hit(1)
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)
        self.my_game.hit(2)
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertNotEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)
        self.my_game.hit(3)
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)
        self.assertEqual(self.my_game.score.away, 2)

    def test_single_first_to_third(self):
        """Single, then a single and runner advances first to third."""
        self.my_game.hit(1)
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)
        self.my_game.hit(1, [(0, 2)])
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)
        self.my_game.hit(1, [(2, 3), (0, 2)])
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)
        self.assertEqual(self.my_game.score.away, 1)


class TestDoublePlays(GameTestBase):
    """Test various double plays."""

    def setUp(self):
        """Simple setup."""
        super().setUp()
        self.my_game.rng = FakeRNG([0.99, 0.99, 0.99])  # no errors

    def test_643(self):
        """Test common double play."""
        self.my_game.hit()
        self.my_game.double_play()
        self.assertEqual(self.my_game.inning.outs, 2)
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_34_double_play(self):
        """Out at first, throw out at second."""
        self.my_game.hit()
        self.my_game.double_play("first", "second")
        self.assertEqual(self.my_game.inning.outs, 2)
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertEqual(self.my_game.bases[1], 0)
        self.assertEqual(self.my_game.bases[2], 0)

    def test_double_play_two_outs(self):
        """Two outs then double play."""
        self.my_game.ground_out()
        self.my_game.ground_out()
        self.my_game.hit()
        self.assertRaises(game_exceptions.TooManyOuts, self.my_game.double_play)


class TestSingleNoAdvance(GameTestBase):
    """Test a single with runners on second and third, no advances."""

    def setUp(self):
        """Simple setup."""
        super().setUp()
        self.my_game.hit(1)
        self.my_game.hit(2)
        self.assertEqual(self.my_game.bases[0], 0)
        self.assertNotEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)
        self.my_game.hit(1, advances=None)

    def test_bases(self):
        """Test for bases loaded."""
        self.assertEqual(self.my_game.inning.outs, 0)
        self.assertNotEqual(self.my_game.bases[0], 0)
        self.assertNotEqual(self.my_game.bases[1], 0)
        self.assertNotEqual(self.my_game.bases[2], 0)

    def test_score(self):
        """Score should be nil nil."""
        self.assertEqual(self.my_game.score.home, 0)
        self.assertEqual(self.my_game.score.away, 0)


if __name__ == "__main__":
    unittest.main()
