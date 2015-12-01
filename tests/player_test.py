from unittest import TestCase

from player.player import Player
__author__ = 'jgrigonis'


class TestPlayer(TestCase):
    def test_specific_name(self):
        my_player = Player("Willie", "Mays")
        self.assertEqual(my_player.first_name, "Willie")
        self.assertEqual(my_player.last_name, "Mays")

