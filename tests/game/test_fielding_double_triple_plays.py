import uuid

import pytest

from src.db.migration_files import (
    migration_028_fielding_double_triple_plays as migration,
)
from src.db.repositories.player_games import PlayerGameRepository
from src.game.bases import FIRST, SECOND, THIRD
from src.game.events.double_play import DoublePlayEvent
from src.game.events.out import PutOutEvent, fielders_on
from src.game.events.triple_play import TriplePlayEvent
from src.game.intents.pitch import PitchIntent
from src.game.resolver import Resolver
from src.game.resolvers.double_play import resolve_double_play
from src.game.resolvers.triple_play import resolve_triple_play
from src.league.offseason.build_season_stats import build_season
from src.player.player_in_game import PlayerInGame
from src.stats.stats import Stats
from tests.factories.player_record_factory import make_player_record
from tests.test_double_play_third_out import MockGame, MockRNG


@pytest.fixture
def game():
    return MockGame()


@pytest.fixture
def pitch_intent():
    return PitchIntent(
        pitcher=PlayerInGame(make_player_record(position="sp")),
        batter=PlayerInGame(make_player_record()),
    )


@pytest.fixture
def resolver():
    return Resolver(rng=MockRNG(0.5))


def _player(pos="ss"):
    return PlayerInGame(make_player_record(position=pos))


def _apply(events, game):
    for e in events:
        if isinstance(e, (PutOutEvent, DoublePlayEvent, TriplePlayEvent)):
            e.apply(game)


def test_fielders_on_lists_each_fielder_once_in_order():
    ss, first = _player("ss"), _player("1b")
    # 3-6-3: first baseman fields it, shortstop covers second, back to first.
    putouts = [PutOutEvent(ss, first), PutOutEvent(first, ss)]
    assert fielders_on(putouts) == (first, ss)


def test_fielders_on_unassisted():
    third = _player("3b")
    assert fielders_on([PutOutEvent(third), PutOutEvent(third)]) == (third,)


def test_double_play_credits_every_fielder_involved(resolver, game, pitch_intent):
    game.bases.set_runner(FIRST, _player())
    game.bases.set_runner(THIRD, _player())

    events = resolve_double_play(resolver, pitch_intent, game)
    dp = next(e for e in events if isinstance(e, DoublePlayEvent))
    _apply(events, game)

    involved = fielders_on(events)
    assert dp.fielders == involved
    assert 1 <= len(involved) <= 3
    everyone = [game.current_pitcher, *game.pitch_team._positions.values()]
    for p in everyone:
        expected = 1 if any(p is f for f in involved) else 0
        assert p.game_stats.fielding.double_plays == expected
        assert p.game_stats.fielding.triple_plays == 0


def test_double_play_without_runner_on_first(resolver, game, pitch_intent):
    game.bases.set_runner(SECOND, _player())

    events = resolve_double_play(resolver, pitch_intent, game)
    dp = next(e for e in events if isinstance(e, DoublePlayEvent))
    assert dp.fielders and dp.fielders == fielders_on(events)


def test_triple_play_credits_every_fielder_involved(resolver, game, pitch_intent):
    game.bases.set_runner(FIRST, _player())
    game.bases.set_runner(SECOND, _player())
    game.bases.is_loaded = False

    events = resolve_triple_play(resolver, pitch_intent, game)
    assert isinstance(events[0], TriplePlayEvent)
    _apply(events, game)

    third, second, first = (game.pos(p) for p in ("3b", "2b", "1b"))
    assert events[0].fielders == (third, second, first)
    for p in (third, second, first):
        assert p.game_stats.fielding.triple_plays == 1
        assert p.game_stats.fielding.double_plays == 0
    assert game.pos("ss").game_stats.fielding.triple_plays == 0


def test_double_and_triple_plays_saved_and_rolled_up(db_conn, factory):
    season = factory.season()
    home, away = factory.team(), factory.team()
    player = factory.player_row()
    repo = PlayerGameRepository(db_conn)
    for date, dps, tps in (("2025-04-01", 2, 0), ("2025-04-02", 1, 1)):
        game_id = str(uuid.uuid4())
        db_conn.execute(
            "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)"
            " VALUES (%s, %s, %s, %s, %s)",
            (game_id, date, season.id, home.id, away.id),
        )
        s = Stats()
        s.fielding.putout()
        for _ in range(dps):
            s.fielding.double_play()
        for _ in range(tps):
            s.fielding.triple_play()
        repo.insert_player_game(
            game_id, player.id, home.id, away.id, s, [("ss", s.fielding)]
        )

    loaded = repo.get_for_game(game_id, player.id)
    assert loaded.fielding.double_plays == 1
    assert loaded.fielding.triple_plays == 1

    (line,) = repo.get_team_fielding_lines(season.id, home.id)
    assert (line["dp"], line["tp"]) == (3, 1)

    build_season(db_conn, season.id)
    row = db_conn.execute(
        """SELECT field_double_plays, field_triple_plays
           FROM player_season_stats WHERE player_id = %s AND season_id = %s""",
        (player.id, season.id),
    ).fetchone()
    assert dict(row) == {"field_double_plays": 3, "field_triple_plays": 1}


def test_migration_is_idempotent(db_conn):
    migration.upgrade(db_conn)
    migration.upgrade(db_conn)
