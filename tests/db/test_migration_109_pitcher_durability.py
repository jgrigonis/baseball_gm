# tests/db/test_migration_109_pitcher_durability.py

import statistics

from src.db.migration_files.migration_109_pitcher_durability import new_durability


def test_rerolled_pitchers_land_around_fifty_with_a_real_spread():
    values = [new_durability(f"p{i}", 11, 20)[0] for i in range(2000)]
    assert 48 <= statistics.mean(values) <= 55
    assert statistics.pstdev(values) > 10


def test_reroll_keeps_aging_and_is_the_same_every_run():
    young, cap = new_durability("abc", 14, 25)
    assert new_durability("abc", 14, 25) == (young, cap)
    old, _ = new_durability("abc", 4, 25)
    assert old == young - 10
    assert cap >= young


def test_no_cap_row_stays_without_one():
    assert new_durability("abc", 11, None)[1] is None
