__author__ = 'jgrigonis'
from unittest import TestCase


from player.player import Player


class TestPlayer(TestCase):
    def test_random_name(self):
        my_player = Player()
        self.assertIsNot(my_player.name, None)

    def test_specific_name(self):
        my_player = Player("Willie Mays")
        self.assertEqual(my_player.name, "Willie Mays")

