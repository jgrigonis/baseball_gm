# src/tests/game/test_minimal.py
def test_game_can_play_minimal_steps(game):
    for _ in range(20):
        game.step()
        if game.is_over():
            break

    assert game.inning.number >= 1
