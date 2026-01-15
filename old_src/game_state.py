# src/game/game_state.py
"""
Nothing mutates game state except Game.apply(event)
No exceptions for inning flow
No resolver sees global state directly
All events are ordered

Pitch → PitchIntent → PitchEvents → PlayIntent → PlayEvents → Game.apply()

Pickoffs	            Before PitchIntent
Steals	                Parallel to pitch
Dropped third strike	PitchResolver
Foul popups	            PlayResolver
Tag vs force timing	    Event ordering
Replay / sim	        Event log


"""
from dataclasses import dataclass

from src.game.bases import Bases
from src.game.inning import Inning
from src.team.team_in_game import TeamInGame as Team
from src.player.player_in_game import PlayerInGame as Player


@dataclass
class GameState:
    inning: Inning
    bases: Bases
    offense: Team
    defense: Team
    batter: Player
    pitcher: Player


@dataclass(frozen=True)
class PlayIntent:
    """Created only after BallInPlayEvent"""

    contact: str | None = None  # ground, fly, line, popup


@dataclass(frozen=True)
class OutEvent:
    runner: Player
    reason: str  # "force", "fly", "tag"

    def apply(self, game):
        game.inning.outs += 1


@dataclass(frozen=True)
class AdvanceEvent:
    runner: Player
    start: int
    end: int

    def apply(self, game):
        game.bases[start] = 0
        if end < 3:
            game.bases[end] = runner


@dataclass(frozen=True)
class RunEvent:
    runner: Player

    def apply(self, game):
        game.score_run()


class GroundBallResolver:
    def resolve(self, intent: PlayIntent, state: GameState) -> list[GameEvent]:
        batter = state.batter

        return [
            OutEvent(runner=batter, reason="groundout"),
        ]


@dataclass(frozen=True)
class PitchIntent:
    kind: str
    # "ball", "called_strike", "swinging_strike", "foul", "in_play"


class PitchResolver:
    def resolve(self, intent: PitchIntent, count: Count) -> list[GameEvent]:
        events: list[GameEvent] = []

        match intent.kind:

            case "ball":
                if count.is_three_balls:
                    events.append(WalkEvent())
                else:
                    events.append(BallEvent())

            case "called_strike" | "swinging_strike":
                if count.is_two_strikes:
                    events.append(StrikeoutEvent())
                else:
                    events.append(StrikeEvent())

            case "foul":
                if not count.is_two_strikes:
                    events.append(StrikeEvent())
                else:
                    events.append(FoulEvent())

            case "in_play":
                events.append(BallInPlayEvent())

        return events


@dataclass
class BallEvent:
    def apply(self, game):
        game.count.add_ball()


@dataclass
class StrikeEvent:
    def apply(self, game):
        game.count.add_strike()


@dataclass
class FoulEvent:
    def apply(self, game):
        game.pitch_count += 1


@dataclass
class StrikeoutEvent:
    def apply(self, game):
        game.count.reset()
        game.queue.append(OutEvent(game.current_batter, "strikeout"))


@dataclass
class WalkEvent:
    def apply(self, game):
        game.count.reset()
        # base advancement handled elsewhere


@dataclass
class BallInPlayEvent:
    def apply(self, game):
        game.count.reset_count()
        game.pending_play = True


class BallInPlayResolver:
    def resolve(self, intent: PlayIntent, state: GameState) -> list[GameEvent]:
        if intent.contact == "ground":
            return [OutEvent(state.batter, "groundout")]

        if intent.contact == "fly":
            return [OutEvent(state.batter, "flyout")]

        # placeholders
        return []
