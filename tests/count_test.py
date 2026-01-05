"""Unit Tests for the Count class."""

import unittest

from src.game.count import Count


class TestInit(unittest.TestCase):
    """Fairly boring, just testing the init."""

    def setUp(self):
        """Initialize the count."""
        self.my_count = Count()

    def test_count(self):
        """Count should be empty."""
        self.assertEqual(self.my_count.balls, 0)
        self.assertEqual(self.my_count.strikes, 0)


class TestStr(unittest.TestCase):
    """Test printing of the class."""

    def setUp(self):
        """Initialize the count."""
        self.my_count = Count()

    def test_print(self):
        """Convert the count to a str."""
        self.my_count.strike()
        self.assertEqual(str(self.my_count), "0 balls, 1 strikes")


class TestReset(unittest.TestCase):
    """Test resetting the count."""

    def setUp(self):
        """Initialize the count."""
        self.my_count = Count()

    def test_reset(self):
        """Reset the count."""
        self.my_count.strike()
        self.my_count.strike()
        self.my_count.ball()
        self.my_count.reset_count()
        self.assertEqual(self.my_count.balls, 0)
        self.assertEqual(self.my_count.strikes, 0)


class TestStrikeOut(unittest.TestCase):
    """Test resetting the count on strike out."""

    def setUp(self):
        """Initialize the count."""
        self.my_count = Count()

    def test_strikeout(self):
        """Reset the count after strikeout."""
        self.my_count.strike()
        self.my_count.strike()
        self.my_count.ball()
        self.my_count.strike()
        self.assertEqual(self.my_count.balls, 0)
        self.assertEqual(self.my_count.strikes, 0)


class TestWalk(unittest.TestCase):
    """Test resetting the count on a walk."""

    def setUp(self):
        """Initialize the count."""
        self.my_count = Count()

    def test_walk(self):
        """Reset the count after a walk."""
        self.my_count.strike()
        self.my_count.strike()
        self.my_count.ball()
        self.my_count.ball()
        self.my_count.ball()
        self.my_count.ball()
        self.assertEqual(self.my_count.balls, 0)
        self.assertEqual(self.my_count.strikes, 0)


if __name__ == "__main__":
    unittest.main()
