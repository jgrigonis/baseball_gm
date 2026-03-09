# tests/team/test_roster_assigner.py
"""
Unit tests for RosterAssigner.

Tests cover:
- Basic tier assignment (26man, 40man, minors)
- Pitcher cap (max 13 on 26-man)
- All 8 lineup positions filled
- Flex spots filled
- 40-man split (7 pitchers + 7 hitters)
- Everyone gets assigned
- Edge cases (small roster, exact roster size)
"""

from src.team.roster_assigner import (
    RosterAssigner,
    MAX_PITCHERS,
    FORTY_MAN_PITCHERS,
    FORTY_MAN_HITTERS,
)
from src.player.player_skills import PlayerSkills
from src.player.player_record import PlayerRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_skills(**overrides) -> PlayerSkills:
    """Create a PlayerSkills with default 50s, overriding specific keys."""
    base = {
        "clutch": 50,
        "speed": 50,
        "power": 50,
        "eye": 50,
        "contact": 50,
        "base_running": 50,
        "bunting": 50,
        "catching": 50,
        "infield": 50,
        "outfield": 50,
        "arm": 50,
        "accuracy": 50,
        "stamina": 50,
        "recovery": 50,
        "ground_balls": 50,
        "strikes": 50,
    }
    base.update(overrides)
    return PlayerSkills(base, age=22)


def make_player(
    player_id: str,
    throws: str = "R",
    position: str = "of",
    **skill_overrides,
) -> PlayerRecord:
    return PlayerRecord(
        id=player_id,
        first_name="Player",
        last_name=player_id,
        bats="R",
        throws=throws,
        position=position,
        skills=make_skills(**skill_overrides),
    )


# def make_pitcher(player_id: str, stamina=70, strikes=70, recovery=70, accuracy=70) -> PlayerRecord:
#     return make_player(
#         player_id,
#         position="p",
#         stamina=stamina,
#         strikes=strikes,
#         recovery=recovery,
#         accuracy=accuracy,
#         # Low hitting stats so they don't compete for position spots
#         contact=20, power=20, eye=20, speed=20,
#     )


# def make_hitter(player_id: str, contact=70, power=70, eye=70, speed=70) -> PlayerRecord:
#     return make_player(
#         player_id,
#         position="of",
#         contact=contact,
#         power=power,
#         eye=eye,
#         speed=speed,
#         # Low pitching stats
#         stamina=20, strikes=20, recovery=20, accuracy=20,
#     )


# def make_full_roster(n_pitchers=40, n_hitters=120) -> list[PlayerRecord]:
#     """Generate a realistic-sized roster pool."""
#     players = []
#     for i in range(n_pitchers):
#         # Vary skills so ranking is deterministic
#         players.append(make_pitcher(f"p{i:03d}", stamina=90 - i, strikes=90 - i))
#     for i in range(n_hitters):
#         players.append(make_hitter(f"h{i:03d}", contact=90 - i, power=90 - i))
#     return players


def make_pitcher(
    player_id: str, stamina=70, strikes=70, recovery=70, accuracy=70
) -> PlayerRecord:
    return make_player(
        player_id,
        position="p",
        stamina=max(1, stamina),
        strikes=max(1, strikes),
        recovery=max(1, recovery),
        accuracy=max(1, accuracy),
        contact=20,
        power=20,
        eye=20,
        speed=20,
    )


def make_hitter(player_id: str, contact=70, power=70, eye=70, speed=70) -> PlayerRecord:
    return make_player(
        player_id,
        position="of",
        contact=max(1, contact),
        power=max(1, power),
        eye=max(1, eye),
        speed=max(1, speed),
        stamina=20,
        strikes=20,
        recovery=20,
        accuracy=20,
    )


def make_full_roster(n_pitchers=40, n_hitters=89) -> list[PlayerRecord]:
    """Generate a realistic-sized roster pool."""
    players = []
    for i in range(n_pitchers):
        players.append(
            make_pitcher(f"p{i:03d}", stamina=max(1, 90 - i), strikes=max(1, 90 - i))
        )
    for i in range(n_hitters):
        players.append(
            make_hitter(f"h{i:03d}", contact=max(1, 90 - i), power=max(1, 90 - i))
        )
    return players


# ---------------------------------------------------------------------------
# Basic assignment
# ---------------------------------------------------------------------------


class TestBasicAssignment:
    def test_everyone_gets_assigned(self):
        players = make_full_roster()
        assignments = RosterAssigner().assign(players)

        assert len(assignments) == len(players)
        for pid, status in assignments.items():
            assert status in (
                "26man",
                "40man",
                "minors",
            ), f"{pid} has invalid status {status}"

    def test_all_player_ids_present(self):
        players = make_full_roster()
        assignments = RosterAssigner().assign(players)
        assigned_ids = set(assignments.keys())
        expected_ids = {p.id for p in players}
        assert assigned_ids == expected_ids

    def test_correct_26man_count(self):
        players = make_full_roster()
        assignments = RosterAssigner().assign(players)
        count_26 = sum(1 for s in assignments.values() if s == "26man")
        assert count_26 == 26

    def test_correct_40man_count(self):
        players = make_full_roster()
        assignments = RosterAssigner().assign(players)
        count_40 = sum(1 for s in assignments.values() if s == "40man")
        assert count_40 == FORTY_MAN_PITCHERS + FORTY_MAN_HITTERS  # 14

    def test_minors_gets_remainder(self):
        players = make_full_roster(n_pitchers=40, n_hitters=89)
        assignments = RosterAssigner().assign(players)
        count_minors = sum(1 for s in assignments.values() if s == "minors")
        assert count_minors == len(players) - 26 - 14


# ---------------------------------------------------------------------------
# Pitcher cap
# ---------------------------------------------------------------------------


class TestPitcherCap:
    def test_max_13_pitchers_on_26man(self):
        """Even with 50 pitchers available, only 13 should make the 26-man."""
        players = make_full_roster(n_pitchers=50, n_hitters=120)
        assignments = RosterAssigner().assign(players)

        pitcher_ids_on_26 = [
            pid for pid, status in assignments.items() if status == "26man"
        ]

        # Count how many 26-man players are pitchers (high sp/rp rating)
        # We can check by seeing if they're from our pitcher pool
        pitcher_pool_ids = {f"p{i:03d}" for i in range(50)}
        pitchers_on_26 = [pid for pid in pitcher_ids_on_26 if pid in pitcher_pool_ids]

        assert len(pitchers_on_26) <= MAX_PITCHERS

    def test_fewer_pitchers_than_max(self):
        """If only 8 pitchers available, fill all 8 spots and don't crash."""
        players = make_full_roster(n_pitchers=8, n_hitters=120)
        assignments = RosterAssigner().assign(players)

        pitcher_pool_ids = {f"p{i:03d}" for i in range(8)}
        pitchers_on_26 = [
            pid
            for pid, s in assignments.items()
            if s == "26man" and pid in pitcher_pool_ids
        ]
        assert len(pitchers_on_26) <= MAX_PITCHERS


# ---------------------------------------------------------------------------
# Lineup positions
# ---------------------------------------------------------------------------


class TestLineupPositions:
    def test_26man_has_at_least_8_hitters(self):
        """The 8 lineup positions should be filled by hitters."""
        players = make_full_roster()
        assignments = RosterAssigner().assign(players)

        hitter_pool_ids = {f"h{i:03d}" for i in range(120)}
        hitters_on_26 = [
            pid
            for pid, s in assignments.items()
            if s == "26man" and pid in hitter_pool_ids
        ]
        # 8 lineup + 5 flex = 13 hitter spots on 26-man
        assert len(hitters_on_26) >= 8


# ---------------------------------------------------------------------------
# 40-man split
# ---------------------------------------------------------------------------


class TestFortyManSplit:
    def test_40man_has_pitchers(self):
        players = make_full_roster()
        assignments = RosterAssigner().assign(players)

        pitcher_pool_ids = {f"p{i:03d}" for i in range(40)}
        pitchers_on_40 = [
            pid
            for pid, s in assignments.items()
            if s == "40man" and pid in pitcher_pool_ids
        ]
        assert len(pitchers_on_40) == FORTY_MAN_PITCHERS

    def test_40man_has_hitters(self):
        players = make_full_roster()
        assignments = RosterAssigner().assign(players)

        hitter_pool_ids = {f"h{i:03d}" for i in range(89)}
        hitters_on_40 = [
            pid
            for pid, s in assignments.items()
            if s == "40man" and pid in hitter_pool_ids
        ]
        assert len(hitters_on_40) == FORTY_MAN_HITTERS


# ---------------------------------------------------------------------------
# Best players selected
# ---------------------------------------------------------------------------


class TestBestPlayersSelected:
    def test_best_pitchers_on_26man(self):
        """Top 5 pitchers by sp rating should be starters on 26-man."""
        players = make_full_roster(n_pitchers=40, n_hitters=120)
        assignments = RosterAssigner().assign(players)

        # p000 has highest stamina/strikes, should be on 26-man
        assert assignments["p000"] == "26man"
        assert assignments["p001"] == "26man"
        assert assignments["p002"] == "26man"
        assert assignments["p003"] == "26man"
        assert assignments["p004"] == "26man"

    def test_worst_pitchers_in_minors(self):
        """Bottom pitchers should end up in minors."""
        players = make_full_roster(n_pitchers=40, n_hitters=120)
        assignments = RosterAssigner().assign(players)

        # p039 has the worst pitching stats
        assert assignments["p039"] == "minors"

    def test_best_hitters_on_26man(self):
        """Top hitters should appear on the 26-man."""
        players = make_full_roster(n_pitchers=40, n_hitters=120)
        assignments = RosterAssigner().assign(players)

        # h000 is the best hitter
        assert assignments["h000"] == "26man"

    def test_worst_hitters_in_minors(self):
        """Bottom hitters should end up in minors."""
        players = make_full_roster(n_pitchers=40, n_hitters=120)
        assignments = RosterAssigner().assign(players)

        # h119 is the worst hitter
        assert assignments["h119"] == "minors"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_exact_26_players(self):
        """With exactly 26 players, all should be on 26-man, none in 40-man or minors."""
        players = make_full_roster(n_pitchers=13, n_hitters=13)
        assignments = RosterAssigner().assign(players)

        assert all(s == "26man" for s in assignments.values())

    def test_empty_roster(self):
        """Empty roster should return empty assignments."""
        assignments = RosterAssigner().assign([])
        assert assignments == {}

    def test_only_pitchers(self):
        """Roster of only pitchers should still assign without crashing."""
        players = [make_pitcher(f"p{i:03d}") for i in range(30)]
        assignments = RosterAssigner().assign(players)
        assert len(assignments) == 30
        assert all(s in ("26man", "40man", "minors") for s in assignments.values())

    def test_only_hitters(self):
        """Roster of only hitters should still assign without crashing."""
        players = [make_hitter(f"h{i:03d}") for i in range(30)]
        assignments = RosterAssigner().assign(players)
        assert len(assignments) == 30
        assert all(s in ("26man", "40man", "minors") for s in assignments.values())

    def test_single_player(self):
        """Single player should be assigned to 26-man."""
        players = [make_hitter("h000")]
        assignments = RosterAssigner().assign(players)
        assert assignments["h000"] == "26man"

    def test_no_duplicate_assignments(self):
        """Each player should appear exactly once in assignments."""
        players = make_full_roster()
        assignments = RosterAssigner().assign(players)
        assert len(assignments) == len(players)
