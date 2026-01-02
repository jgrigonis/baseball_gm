import unittest

from src.game.game_exceptions import TooManyOuts
from src.game.inning import Inning

__author__ = "josh"


class TestInning(unittest.TestCase):
    """Test the inning."""
    def setUp(self):
        """Setup the test."""
        self.my_inning = Inning()

    def test_new_inning(self):
        """Test the new inning."""
        self.assertEqual(self.my_inning.number, 1)
        self.assertTrue(self.my_inning.top)
        self.assertEqual(self.my_inning.outs, 0)

    def test_increments(self):
        """Test the increments."""
        self.my_inning.increment()
        self.assertEqual(self.my_inning.number, 1)
        self.assertFalse(self.my_inning.top)
        self.assertEqual(self.my_inning.outs, 0)
        self.my_inning.increment()
        self.assertEqual(self.my_inning.number, 2)
        self.assertTrue(self.my_inning.top)
        self.assertEqual(self.my_inning.outs, 0)

    def test_outs(self):
        """Test the outs."""
        self.my_inning.out()
        self.assertEqual(self.my_inning.outs, 1)
        self.my_inning.out()
        self.assertEqual(self.my_inning.outs, 2)
        self.assertRaises(TooManyOuts, self.my_inning.out)
        self.my_inning.reset_outs()
        self.assertEqual(self.my_inning.outs, 0)


if __name__ == "__main__":
    unittest.main()
