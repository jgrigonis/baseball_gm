# src/game/events/out.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class OutRecordedEvent(GameEvent):
    """
    Records an out in the game and as a pitcher stat.
    """

    reason: str
    pitcher: PlayerInGame

    def apply(self, game):
        game.inning.record_out()
        self.pitcher.game_stats.pitching.out()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        if game.inning.outs == 1:
            return "1 out"
        else:
            return f"{game.inning.outs} outs"


@dataclass(frozen=True)
class GroundOutEvent(GameEvent):
    """
    Simply adds an at bat to the batter
    """

    batter: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.at_bat()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} grounded out."


@dataclass(frozen=True)
class FlyOutEvent(GameEvent):
    """
    Simply adds an at bat to the batter
    """

    batter: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.at_bat()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} hit a fly out."


@dataclass(frozen=True)
class LineOutEvent(GameEvent):
    """
    A line drive caught on the fly: an at bat for the batter.
    """

    batter: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.at_bat()

    def describe(self, game) -> str:
        return f"{self.batter.name} lined out."


@dataclass(frozen=True)
class AirDoublePlayEvent(GameEvent):
    """
    A ball caught in the air and a runner doubled off (a line drive) or
    thrown out tagging up (a fly ball). An at bat for the batter and a
    double play for every fielder on it, but not a GIDP: it wasn't a
    ground ball. The outs and the runner's removal are their own events.
    """

    batter: PlayerInGame
    runner: PlayerInGame
    base: int  # where the runner was put out
    fielders: tuple[PlayerInGame, ...] = ()
    kind: str = "line"  # "line": doubled off; "fly": thrown out tagging

    def apply(self, game):
        self.batter.game_stats.batting.at_bat()
        for fielder in self.fielders:
            fielder.game_stats.fielding.double_play()

    def describe(self, game) -> str:
        if self.kind == "line":
            return (
                f"{self.batter.name} lined into a double play, "
                f"{self.runner.name} doubled off."
            )
        return (
            f"{self.batter.name} flied into a double play, "
            f"{self.runner.name} thrown out tagging up."
        )


@dataclass(frozen=True)
class FoulFlyOutEvent(GameEvent):
    """
    Simply adds an at bat to the batter
    """

    batter: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.at_bat()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} hit a foul fly out."


@dataclass(frozen=True)
class PutOutEvent(GameEvent):
    """
    Simply adds an at bat to the batter
    """

    fielder: PlayerInGame
    assist: PlayerInGame | None = None

    def apply(self, game):
        self.fielder.game_stats.fielding.putout()
        if self.assist:
            self.assist.game_stats.fielding.assist()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        msg = f"{self.fielder.name} ({self.fielder.current_position}) with the putout."
        if self.assist:
            msg += (
                f" {self.assist.name} ({self.assist.current_position}) with the assist"
            )
        return msg


def fielders_on(events) -> tuple[PlayerInGame, ...]:
    """Every fielder with a putout or assist among these events, once each,
    in the order they handled the ball."""
    fielders: list[PlayerInGame] = []
    for e in events:
        if not isinstance(e, PutOutEvent):
            continue
        for p in (e.assist, e.fielder):
            if p is not None and not any(p is f for f in fielders):
                fielders.append(p)
    return tuple(fielders)
