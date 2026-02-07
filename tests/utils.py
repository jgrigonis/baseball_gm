# tests/utils.py
from copy import deepcopy
import logging
from types import SimpleNamespace

from src.game.count import Count
from src.game.bases import Bases
from src.game.inning import Inning
from src.game.intents.pitch import PrePitchSituation
from src.game.score import Score
from src.game.resolver import Resolver
from src.game.game import Game
from src.player.player_in_game import PlayerInGame
from src.player.player_skills import PlayerSkills
from src.player.positions import SKILLS
from src.util.logger import setup_logger
from tests.factories.player_record_factory import make_player_record


class FakePlayer:
    def __init__(self, id):
        self.id = id
        self.name = id
        # Add pitcher_fatigue attribute
        self.pitcher_fatigue = None  # Or initialize properly if is_pitcher

    def init_game_stats(self):
        pass  # Game calls this, but we don't care in tests


class FakePlayerInGame:
    def __init__(self, id: str):
        self.id = id
        self.name = id

        # game_stats with fielding stats
        self.game_stats = SimpleNamespace(
            fielding=SimpleNamespace(
                putout=lambda: None,  # Mock method that does nothing
                assist=lambda: None,  # You might need this too
            )
        )

        # optional placeholders for future stats
        # self.stats = None
        self.skills = PlayerSkills(deepcopy(dict(SKILLS)))
        self.pitcher_fatigue = None

    def get_effective_stat(self, stat: int):
        return stat


class FakeLineupSlot:
    def __init__(self, player_id: str, position="dh"):
        self.player = FakePlayerInGame(player_id)
        self.position = position


def real_game(
    *,
    rng=None,
    resolver=None,
    home_team=None,
    away_team=None,
):
    rng = rng or FakeRNG([0.5] * 100)

    resolver = resolver or Resolver(rng=rng)

    home_team = home_team or FakeTeam("Home")
    away_team = away_team or FakeTeam("Away")

    game = Game(
        home_team=home_team,
        away_team=away_team,
        resolver=resolver,
        rng=rng,
    )

    # Silence logs for tests
    # game.logger = NullLogger()
    # Verbose logs
    game.logger = setup_logger(
        name="game", level=logging.TRACE, console_level=logging.TRACE
    )

    return game


def fake_game():
    batter = FakeLineupSlot("b1")
    pitcher = FakePlayerInGame("p1")
    catcher = FakePlayerInGame("c1")
    shortstop = FakePlayerInGame("ss1")
    second_baseman = FakePlayerInGame("2b1")
    third_baseman = FakePlayerInGame("3b1")
    first_baseman = FakePlayerInGame("1b1")
    left_fielder = FakePlayerInGame("lf1")
    center_fielder = FakePlayerInGame("cf1")
    right_fielder = FakePlayerInGame("rf1")

    # Create a fake pitch_team with all positions
    pitch_team = SimpleNamespace(
        current_catcher=catcher,
        current_shortstop=shortstop,
        current_second_baseman=second_baseman,
        current_third_baseman=third_baseman,
        current_first_baseman=first_baseman,
        current_left_fielder=left_fielder,
        current_center_fielder=center_fielder,
        current_right_fielder=right_fielder,
    )

    game = SimpleNamespace(
        # core state
        count=Count(),
        bases=Bases(),
        inning=Inning(),
        score=Score(),
        situation=PrePitchSituation(),
        # logger
        logger=NullLogger(),
        # cursors
        current_batter=batter,
        current_pitcher=pitcher,
        # team info
        pitch_team=pitch_team,
        # PA state
        _plate_appearance_complete=False,
        _pa_end_reason=None,
    )

    def pos(position):
        pos_map = {
            "p": pitcher,
            "c": catcher,
            "ss": shortstop,
            "2b": second_baseman,
            "3b": third_baseman,
            "1b": first_baseman,
            "lf": left_fielder,
            "cf": center_fielder,
            "rf": right_fielder,
        }
        return pos_map[position]

    game.pos = pos

    # --- methods expected by events ---
    def _mark_plate_appearance_complete(reason):
        game._plate_appearance_complete = True
        game._pa_end_reason = reason

    game._mark_plate_appearance_complete = _mark_plate_appearance_complete

    return game


class FakeRNG:
    def __init__(self, values):
        self.values = iter(values)
        self.call_count = 0

    def random(self):
        self.call_count += 1
        try:
            return next(self.values)
        except StopIteration:
            print(f"ERROR: FakeRNG exhausted after {self.call_count} calls!")
            raise

    # def random(self):
    #     return next(self.values)


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


class FakeTeam:
    def __init__(self, name="FakeTeam"):
        # Create a fake record to mimic TeamRecord
        self.record = SimpleNamespace(
            id=f"{name.lower()}-id",
            city=f"{name} City",
            mascot=f"{name}s",
        )
        self.name = name

        self.players = [FakePlayer(f"{name}-p{i}") for i in range(1, 10)]

        self.lineup = [FakeLineupSlot(p) for p in self.players]
        self.batter_index = 0

        self._pitcher = FakePlayer(f"{name}-pitcher")

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

    @property
    def current_pitcher(self):
        return self._pitcher


def fake_game_with_batter_cycle():
    game = fake_game()

    batters = [PlayerInGame(make_player_record()), PlayerInGame(make_player_record())]
    game._batter_index = 0
    game.current_batter = batters[0]
    game.current_pitcher = PlayerInGame(make_player_record())

    def _next_batter():
        game._batter_index = (game._batter_index + 1) % len(batters)
        return batters[game._batter_index]

    def _advance_batter():
        game.current_batter = _next_batter()
        game._plate_appearance_complete = False
        game._pa_end_reason = None

    game._next_batter = _next_batter
    game._advance_batter = _advance_batter

    def _post_event():
        if game._plate_appearance_complete:
            game._advance_batter()
            game.count.reset()

    game._next_batter = _next_batter
    game._advance_batter = _advance_batter
    game._post_event = _post_event

    return game
