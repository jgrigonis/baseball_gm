# tests/utils.py
from types import SimpleNamespace
import itertools

from src.game.count import Count
from src.game.bases import Bases
from src.game.inning import Inning
from src.game.score import Score


class FakeRNG:
    def __init__(self, values):
        self.values = iter(values)

    def random(self):
        return next(self.values)


class NullLogger:
    def info(self, msg, *args, **kwargs):
        pass

    def debug(self, msg, *args, **kwargs):
        pass

    def trace(self, msg, *args, **kwargs):
        pass

    def error(self, msg, *args, **kwargs):
        pass

    def warning(self, msg, *args, **kwargs):
        pass

    def critical(self, msg, *args, **kwargs):
        pass


class FakePlayer:
    def __init__(self, player_id, name=None):
        self.id = player_id
        self.name = name or player_id

    def init_game_stats(self):
        pass  # Game calls this, but we don't care in tests


class FakeLineupSlot:
    def __init__(self, player):
        self.player = player


class FakeTeam:
    def __init__(self, name="FakeTeam"):
        self.name = name

        self.players = [
            FakePlayer(f"{name}-p{i}", f"{name} Player {i}") for i in range(1, 10)
        ]

        self.lineup = [FakeLineupSlot(p) for p in self.players]
        self.batter_index = 0

        self._pitcher = FakePlayer(f"{name}-pitcher", f"{name} Pitcher")

    # ---------------------------
    # Required Game API
    # ---------------------------

    @property
    def has_lineup(self):
        return True

    @property
    def current_batter(self):
        return self.lineup[self.batter_index]

    def next_batter(self):
        self.batter_index = (self.batter_index + 1) % len(self.lineup)
        return self.current_batter

    def current_pitcher(self):
        return self._pitcher


def fake_game():
    game = SimpleNamespace()

    # Core state
    game.inning = Inning()
    game.count = Count()
    game.bases = Bases()
    game.score = Score()

    # Plate appearance state
    game._pa_complete = False
    game._pa_end_reason = None

    # --- PA lifecycle API ---

    def _mark_plate_appearance_complete(reason):
        game._pa_complete = True
        game._pa_end_reason = reason

    def _plate_appearance_over():
        return game._pa_complete

    game._mark_plate_appearance_complete = _mark_plate_appearance_complete
    game._plate_appearance_over = _plate_appearance_over

    return game


def fake_game_with_batter_cycle():
    game = fake_game()

    batters = ["b1", "b2"]
    game._batter_index = 0
    game.current_batter = batters[0]

    def _next_batter():
        game._batter_index = (game._batter_index + 1) % len(batters)
        return batters[game._batter_index]

    def _advance_batter():
        game.current_batter = _next_batter()
        game._pa_complete = False
        game._pa_end_reason = None

    game._next_batter = _next_batter
    game._advance_batter = _advance_batter

    def _post_event():
        if game._plate_appearance_over():
            game._advance_batter()
            game.count.reset()

    game._next_batter = _next_batter
    game._advance_batter = _advance_batter
    game._post_event = _post_event

    return game
