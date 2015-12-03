import unittest

from player.player import Player
__author__ = 'jgrigonis'


class TestPlayer(unittest.TestCase):
    def test_specific_name(self):
        my_player = Player("Willie", "Mays")
        self.assertEqual(my_player.first_name, "Willie")
        self.assertEqual(my_player.last_name, "Mays")

if __name__ == '__main__':
    unittest.main()
