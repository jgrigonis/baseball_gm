import unittest

from src.player.positions import POSITIONS, SKILL_TEMPLATE


__author__ = "josh"


class TestPositions(unittest.TestCase):
    def test_keys(self):
        assert set(POSITIONS) == set(SKILL_TEMPLATE.keys())
