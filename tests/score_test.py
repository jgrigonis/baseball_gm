import unittest

from src.game.score import Score

__author__ = "josh"


class TestScore(unittest.TestCase):
    def setUp(self):
        self.my_score = Score()

    def test_empty_score(self):
        self.assertEqual(self.my_score.away_innings, [0])
        self.assertEqual(self.my_score.home_innings, [])
        self.assertEqual(self.my_score.away, 0)
        self.assertEqual(self.my_score.home, 0)

    def test_scores(self):
        self.my_score.score_run()
        self.assertEqual(self.my_score.away, 1)
        self.my_score.score_run()
        self.assertEqual(self.my_score.away, 2)
        self.my_score.new_inning()
        self.my_score.score_run()
        self.assertEqual(self.my_score.home, 1)
        self.assertEqual(self.my_score.away, 2)

    def test_many_innings(self):
        self.my_score.new_inning()  # bottom of first now
        self.my_score.score_run()
        self.assertEqual(self.my_score.home, 1)
        self.my_score.new_inning()  # top of the second now
        self.my_score.score_run()
        self.assertEqual(self.my_score.away, 1)
        self.my_score.new_inning()  # bottom of first now


if __name__ == "__main__":
    unittest.main()
