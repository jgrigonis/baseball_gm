# src/game/play_resolver.py
"""
BallInPlayResolver responsibilities

It receives
    an EventOutcome with:
        type == "in_play"
        contact != None
    the full immutable game state
It must decide
    outs recorded (0-3)
    bases awarded
    double plays
    runner advancement
    description
It must return
👉 a new EventOutcome (or a ResolvedPlay wrapper if you already have one)
Resolvers never mutate game state directly.

contact type
   ↓
defensive category
   ↓
out / hit / reach
   ↓
runner logic
   ↓
EventOutcome

"""
from dataclasses import dataclass
import random

from src.game.bases import FIRST, SECOND, THIRD
from src.game.event_generator import EventOutcome

# from src.player.player_in_game import PlayerInGame


from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedPlay:
    outs: int
    runner_advances: dict[int, int]  # from_base -> to_base
    batter_to: int | None  # None = out, 0 = first, etc
    runs_scored: int
    description: str


# @dataclass(frozen=True)
# class ResolvedPlay:
#     outs: int
#     batter_to: int | None  # None = batter out
#     runner_advances: dict[int, int]  # base -> bases advanced
#     runs_scored: int
#     description: str


class BallInPlayResolver:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()

    def resolve(self, outcome: EventOutcome, game) -> ResolvedPlay:
        assert outcome.type == "in_play"
        assert outcome.contact is not None

        contact = outcome.contact

        if contact == "ground":
            return self.resolve_ground_ball(game)

        if contact == "fly":
            return self.resolve_fly_ball(game)

        if contact == "line":
            return self.resolve_line_drive(game)

        if contact == "popup":
            return self.resolve_popup(game)

        raise ValueError(f"Unknown contact type: {contact}")

    def resolve_ground_ball(self, game) -> ResolvedPlay:
        if self.rng.random() < 0.7:
            # ground out
            return ResolvedPlay(
                outs=1,
                batter_to=None,
                runner_advances={},
                runs_scored=0,
                description="Grounded out",
            )

        return ResolvedPlay(
            outs=0,
            batter_to=FIRST,
            runner_advances={},
            runs_scored=0,
            description="Ground ball single",
        )

    def resolve_fly_ball(self, game) -> ResolvedPlay:
        if self.rng.random() < 0.75:
            return ResolvedPlay(
                outs=1,
                batter_to=None,
                runner_advances={},
                runs_scored=0,
                description="Fly out",
            )

        return ResolvedPlay(
            outs=0,
            batter_to=SECOND,
            runner_advances={},
            runs_scored=0,
            description="Fly ball double",
        )

    def resolve_line_drive(self, game) -> ResolvedPlay:
        if self.rng.random() < 0.2:
            return ResolvedPlay(
                outs=1,
                batter_to=None,
                runner_advances={},
                runs_scored=0,
                description="Line out",
            )

        bases = SECOND if self.rng.random() < 0.4 else FIRST
        return ResolvedPlay(
            outs=0,
            batter_to=bases,
            runner_advances={},
            runs_scored=0,
            description="Line drive hit",
        )

    def resolve_popup(self, game) -> ResolvedPlay:
        return ResolvedPlay(
            outs=1,
            batter_to=None,
            runner_advances={},
            runs_scored=0,
            description="Popup out",
        )
