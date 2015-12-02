"""Unit Tests for the Bases class."""
import unittest

from game.bases import Bases
import game.game_exceptions as game_exceptions


# pylint: disable=R0904
# pylint complains about too many public methods, but I don't see it.
class TestBases(unittest.TestCase):
    """Test clearing the bases."""
    def setUp(self):
        """Simple setup."""
        self.my_bases = Bases()

    def test_clear_default(self):
        """Test clearing all bases."""
        self.my_bases.clear()
        self.assertEqual(self.my_bases.bases, [0, 0, 0])

    def test_clear_first(self):
        """Test clearing first base."""
        self.my_bases.bases = [1, 1, 1]
        self.my_bases.clear([0])
        self.assertEqual(self.my_bases.bases[0], 0)
        self.assertNotEqual(self.my_bases.bases[1], 0)
        self.assertNotEqual(self.my_bases.bases[2], 0)

    def test_clear_second_third(self):
        """Test clearing second and third base."""
        self.my_bases.bases = [1, 1, 1]
        self.my_bases.clear([1, 2])
        self.assertNotEqual(self.my_bases.bases[0], 0)
        self.assertEqual(self.my_bases.bases[1], 0)
        self.assertEqual(self.my_bases.bases[2], 0)

    def test_clear_second_with_int(self):
        """Test clearing second base."""
        self.my_bases.bases = [1, 1, 1]
        self.my_bases.clear(1)
        self.assertNotEqual(self.my_bases.bases[0], 0)
        self.assertEqual(self.my_bases.bases[1], 0)
        self.assertNotEqual(self.my_bases.bases[2], 0)

    def test_advance_all(self):
        """Test advancing all the runners."""
        self.my_bases.bases = ["al", "bob", "carl"]
        scored = self.my_bases.advance_all()
        self.assertEqual("carl", scored)
        self.assertEqual(self.my_bases.bases, [0, "al", "bob"])

    def test_men_on(self):
        """Test men_on."""
        self.assertEqual(0, self.my_bases.men_on())
        self.my_bases.bases = ["al", "bob", "carl"]
        self.assertEqual(3, self.my_bases.men_on())
        scored = self.my_bases.advance_all()
        self.assertEqual("carl", scored)
        self.assertEqual(2, self.my_bases.men_on())

    def test_advance_to_third(self):
        """Test advance to third."""
        self.my_bases.bases = [0, "bob", 0]
        self.my_bases.advance(1)
        self.assertEqual(1, self.my_bases.men_on())
        self.assertEqual([0, 0, "bob"], self.my_bases.bases)

    def test_advance_to_occupied(self):
        """Test advance to third."""
        self.my_bases.bases = [0, "bob", "carl"]
        self.assertRaises(game_exceptions.AdvanceToOccupiedBase,
                          self.my_bases.advance, 1)

    def test_advance_no_one(self):
        """Test advance to third."""
        self.my_bases.bases = [0, 0, 0]
        self.assertRaises(game_exceptions.NoRunnerToAdvance,
                          self.my_bases.advance, 1)

    def test_advance_past_occupied(self):
        """Test advance to third."""
        self.my_bases.bases = ["al", "bob", 0]
        self.assertRaises(game_exceptions.AdvancePastOccupiedBase,
                          self.my_bases.advance, 0, 2)


class TestScoring(unittest.TestCase):
    """Test more scoring scenarios."""
    def setUp(self):
        """Simple setup."""
        self.my_bases = Bases()
        self.my_bases.bases = ["al", "bob", "carl"]

    def test_score_from_third(self):
        """Advance all, and score the runner on third."""
        scored = self.my_bases.advance_all()
        self.assertEqual("carl", scored)

    def test_score_several(self):
        """Test several scores."""
        scored = self.my_bases.advance(2, 3)
        self.assertEqual("carl", scored)
        scored = self.my_bases.advance(1, 3)
        self.assertEqual("bob", scored)
        scored = self.my_bases.advance(0, 3)
        self.assertEqual("al", scored)

    def test_advance_many(self):
        """Test the advance_many method."""
        scored = self.my_bases.advance_many([(2, 3), (1, 3), (0, 2)])
        self.assertEqual(["carl", "bob"], scored)
        self.assertEqual(self.my_bases.bases[2], "al")

    def test_advance_many_reversed(self):
        """TEst the advance_many method with tuples in reverse order."""
        scored = self.my_bases.advance_many([(0, 2), (1, 3), (2, 3)])
        self.assertEqual(["carl", "bob"], scored)
        self.assertEqual(self.my_bases.bases[2], "al")


class TestStrings(unittest.TestCase):
    """Test the __str__ function."""
    def setUp(self):
        """Simple setup."""
        self.my_bases = Bases()

    def test_bases_empty(self):
        """Test that it says bases empty."""
        self.assertEqual(str(self.my_bases), "Bases empty.")

    def test_one_on(self):
        """Test that there is one runner on."""
        self.my_bases.bases = [7, 0, 0]
        self.assertEqual(str(self.my_bases), "Runner on first.")
        self.my_bases.advance_all()
        self.assertEqual(str(self.my_bases), "Runner on second.")
        self.my_bases.advance_many([(1, 2)])
        self.assertEqual(str(self.my_bases), "Runner on third.")

    def test_two_on(self):
        """Test that there are two runners on."""
        self.my_bases.bases = [3, 5, 0]
        self.assertEqual(str(self.my_bases), "Runners at first and second.")
        self.my_bases.advance_many([(1, 2)])
        self.assertEqual(str(self.my_bases), "Runners at first and third.")
        self.my_bases.advance_many([(0, 1)])
        self.assertEqual(str(self.my_bases), "Runners on second and third.")

    def test_bases_loaded(self):
        """Test bases loaded."""
        self.my_bases.bases = [3, 5, 6]
        self.assertEqual(str(self.my_bases), "Bases loaded.")


class TestIteration(unittest.TestCase):
    """Test iterating through bases."""
    def setUp(self):
        """Simple setup."""
        self.my_bases = Bases()

    def test_iteration(self):
        """Test iteration."""
        self.my_bases.bases = [0, 0, 0]
        for base in self.my_bases:
            self.assertEqual(base, 0)

    def test_get_item(self):
        """Test getting individual bases."""
        self.my_bases.bases = [1, 2, 3]
        self.assertEqual(self.my_bases["first"], 1)
        self.assertEqual(self.my_bases["second"], 2)
        self.assertEqual(self.my_bases["third"], 3)

    def test_set_item(self):
        """Test getting individual bases."""
        self.my_bases["first"] = 6
        self.my_bases["second"] = 7
        self.my_bases["third"] = 8
        self.assertEqual(self.my_bases.bases, [6, 7, 8])


class TestExceptions(unittest.TestCase):
    """Test some bad advance_many."""
    def setUp(self):
        """Simple setup."""
        self.my_bases = Bases()

    def test_bad_advance(self):
        """Test a bad base runner advance."""
        self.my_bases.bases = [3, 6, 7]
        self.assertRaises(game_exceptions.InvalidAdvance,
                          self.my_bases.advance, 1, 0)

    def test_backwards_advance(self):
        """Test a backwards base runner advance."""
        self.my_bases.bases = [3, 6, 7]
        self.assertRaises(game_exceptions.InvalidAdvance,
                          self.my_bases.advance, 2, 1)


class TestTupleToList(unittest.TestCase):
    """Test converting the tuple to list of tuples."""
    def setUp(self):
        """Simple setup."""
        self.my_bases = Bases()

    def test_tuple_to_list(self):
        """Test tuple to list conversion."""
        self.my_bases.bases = [3, 0, 0]
        self.my_bases.advance_many((0, 3))
        self.assertEqual(self.my_bases.bases, [0, 0, 0])


class TestBasesEmpty(unittest.TestCase):
    """Test empty_base method."""
    def setUp(self):
        """Simple setup."""
        self.my_bases = Bases()

    def test_is_empty(self):
        """Test if the base is empty and it is."""
        self.assertEqual(self.my_bases.empty_base(0), True)

    def test_isnt_empty(self):
        """Test if the base is empty and it isnt."""
        self.my_bases.bases = [0, 0, 3]
        self.assertEqual(self.my_bases.empty_base(2), False)

if __name__ == '__main__':
    unittest.main()