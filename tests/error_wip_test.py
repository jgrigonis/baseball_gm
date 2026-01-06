def test_defensive_play_error(self):
    resolver = DefensiveResolver(
        rng=FakeRNG([0.001]),
        logger=NullLogger(),
    )

    outcome = resolver.check_play(
        defender=self.simple_player,
        play_type="fielding",
        position="ss",
    )

    assert outcome.success is False
    assert outcome.error is True
    assert outcome.slow is False
    assert self.simple_player.stats.fielding.errors == 1

outcome = resolver.check_play(
    defender=self.simple_player,
    play_type="fielding",
    position="ss",
)

assert outcome.success
assert not outcome.error
assert not outcome.slow

resolver = DefensiveResolver(
    rng=FakeRNG([0.9, 0.01]),
    logger=NullLogger(),
)

outcome = resolver.check_play(
    defender=self.simple_player,
    play_type="both",
    position="ss",
)

assert not outcome.success
assert outcome.slow
