import random
import unittest

from src.player.player_factory import PlayerFactory
from src.player.player_skills import PlayerSkills
from src.player.positions import SKILLS

__author__ = "josh"


class TestPlayerFactory(unittest.TestCase):
    def test_factory_creates_player(self):
        factory = PlayerFactory(rng=random.Random(123))
        player = factory.create(position="ss")

        assert player.id
        assert player.first_name
        assert player.skills["contact"] > 0

    def test_specific_name(self):
        factory = PlayerFactory()
        my_player = factory.create(position="3b", bats="R", throws="R")
        self.assertEqual(my_player.bats, "R")
        self.assertEqual(my_player.throws, "R")
        my_player2 = factory.create(position="1b", bats="L", throws="L")
        self.assertEqual(my_player2.bats, "L")
        self.assertEqual(my_player2.throws, "L")
        self.assertNotEqual(my_player2.name, None)

    def test_lefty_1b_probability(self):
        rng = random.Random(40)
        factory = PlayerFactory(rng)
        players = [factory.create(position="1b") for _ in range(1000)]
        lefties = sum(1 for p in players if p.throws == "L")
        print(lefties)
        assert 250 < lefties < 400  # approx 33%

    def test_lefty_catcher_is_bad_at_catching(self):
        rng = random.Random(1)
        ps = PlayerSkills(SKILLS)

        skills = ps.generate(rng, position="c", throws="L")
        assert skills["catching"] < 25


if __name__ == "__main__":
    unittest.main()
