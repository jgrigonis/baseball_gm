# tests/test_inning.py
def test_three_outs_end_half_inning(game):
    game.inning.outs = 3
    assert game._half_inning_over()


def test_half_inning_reset_clears_bases_and_count(game):
    game.inning.outs = 3
    # print(game.bases._bases)
    game.bases.advance(runner="p1", from_base=None, to_base=1)
    # print(game.bases._bases)
    game.count.balls = 2
    assert game.bases.occupied_map() == {1: "p1"}
    game._end_half_inning()

    assert game.bases.occupied_map() == {}
    assert game.count.balls == 0
