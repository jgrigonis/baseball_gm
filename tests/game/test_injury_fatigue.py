# tests/game/test_injury_fatigue.py

import pytest

from src.db.repositories.player_energy import PlayerEnergyState
from src.game.game import Game
from src.game.probabilities import INJURY_ACTIVITY_WEIGHT, INJURY_BASE_PROB
from tests.game.test_wild_pitch_walk_scenarios import (
    create_test_player,
    create_test_team,
)
from src.player.player_in_game import PlayerInGame
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.player.positions import SKILLS


def _pitcher(player_id="P1"):
    return PlayerInGame(
        PlayerRecord(
            id=player_id,
            first_name="Test",
            last_name=player_id,
            bats="R",
            throws="R",
            skills=PlayerSkills({skill: 50 for skill in SKILLS}),
            position="p",
        )
    )


@pytest.fixture
def game():
    return Game(home_team=create_test_team("Home"), away_team=create_test_team("Away"))


def _batting_prob(game, player, energy):
    game.player_energy_states[player.id] = PlayerEnergyState(
        player_id=player.id, current_energy=energy
    )
    return game._injury_probability(player, "batting")


@pytest.mark.parametrize(
    "energy, mult",
    [(1.0, 0.8), (0.7, 1.0), (0.5, 1.4), (0.2, 2.0), (0.0, 3.0)],
)
def test_position_player_risk_scales_with_live_energy(game, energy, mult):
    player = PlayerInGame(create_test_player("H1"))
    base = INJURY_BASE_PROB * INJURY_ACTIVITY_WEIGHT["batting"]
    assert _batting_prob(game, player, energy) == pytest.approx(base * mult)


def test_live_energy_wins_over_pregame_energy(game):
    player = PlayerInGame(create_test_player("H1"))
    player.player_energy.set_position_energy(1.0)
    assert _batting_prob(game, player, 0.2) > _batting_prob(game, player, 1.0)


def test_pitcher_risk_ignores_position_fatigue(game):
    pitcher = _pitcher()
    assert pitcher.player_energy is None
    expected = INJURY_BASE_PROB * INJURY_ACTIVITY_WEIGHT["pitching"]
    assert game._injury_probability(pitcher, "pitching") == pytest.approx(expected)
    assert game._live_energy(pitcher) is None
