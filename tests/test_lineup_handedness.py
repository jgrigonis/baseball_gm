# tests/test_lineup_handedness.py

"""
Verify that left-handed throwers are not assigned to infield positions
(or are extremely rare, matching real baseball).
"""

import pytest
import random
from src.team.team_factory import TeamFactory
from src.team.team_in_game_factory import TeamInGameFactory

INFIELD_POSITIONS = {"c", "ss", "2b", "3b"}
# In real baseball, lefties at these positions are essentially nonexistent.
# 1B is fine for lefties, so excluded.
NUM_ROSTERS = 500
MAX_VIOLATION_RATE = 0.01  # allow up to 1%

@pytest.mark.slow
def test_left_handed_infielders_are_rare():
    violations = []

    for i in range(NUM_ROSTERS):
        rng = random.Random(i)
        tf = TeamFactory(rng=rng)
        record = tf.generate_team(city="Test", mascot=f"Team{i}")
        team = TeamInGameFactory.from_record(record)
        team.set_lineup()

        for slot in team.lineup:
            pos = (slot.player.current_position or "").lower()
            throws = (slot.player.record.throws or "R").upper()

            if pos in INFIELD_POSITIONS and throws == "L":
                violations.append(
                    f"Roster {i}: {slot.player.record.name} throws L, assigned to {pos.upper()}"
                )

    if violations:
        violation_rate = len(violations) / NUM_ROSTERS
        if violation_rate > MAX_VIOLATION_RATE:
            pytest.fail(
                f"Found {len(violations)} left-handed infielder assignments "
                f"across {NUM_ROSTERS} rosters ({violation_rate:.1%} rate):\n"
                + "\n".join(violations[:20])  # show first 20
            )

# def test_left_handed_infielders_are_rare_single_roster():
#     violations = []
#     rng = random.Random(83)
#     tf = TeamFactory(rng=rng)
#     record = tf.generate_team(city="Test", mascot="Team83")
#     team = TeamInGameFactory.from_record(record)
#     team.set_lineup()

#     print("\nFull roster:")
#     for p in team.players:
#         print(f"  {p.record.name:<25} throws={p.throws}  3b={p.ratings.get('3b', 0)}  2b={p.ratings.get('2b', 0)}  ss={p.ratings.get('ss', 0)}  c={p.ratings.get('c', 0)}")

#     print("\nLineup:")
#     for i, slot in enumerate(team.lineup, 1):
#         print(f"  {i}. {slot.player.record.name:<25} pos={slot.position}  throws={slot.player.throws}")

#     for slot in team.lineup:
#         pos = (slot.player.current_position or "").lower()
#         throws = (slot.player.record.throws or "R").upper()

#         if pos in INFIELD_POSITIONS and throws == "L":
#             violations.append(
#                 f"Roster 83: {slot.player.record.name} throws L, assigned to {pos.upper()}"
#             )
    
#     if violations:
#         violation_rate = len(violations) / 1
#         pytest.fail(
#             f"Found {len(violations)} left-handed infielder assignments "
#             f"across 1 rosters ({violation_rate:.1%} rate):\n"
#             + "\n".join(violations[:20])  # show first 20
#         )

