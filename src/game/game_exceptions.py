"""Exceptions class for the baseball simulator."""


class GameException(Exception):
    """Base class for exceptions in this module."""


class NotEnoughRunnersOnBase(GameException):
    """Not enough runners on base."""


class NoRunnerToAdvance(GameException):
    """User tried to advance a runner from an exmpty base."""


class AdvanceToOccupiedBase(GameException):
    """User tried to advance a runner to an occupied base."""


class AdvancePastOccupiedBase(GameException):
    """User tried to advance a runner past an occupied base."""


class BadSacrifice(GameException):
    """User tried to call sac_fly method with 2 outs."""


class ErrorCalledWithTooManyAdvances(GameException):
    """User called the error method with too many parameters."""


class InvalidAdvance(GameException):
    """User called the error method with an invalid baserunner advance."""


class InvalidSteal(GameException):
    """User called a steal, or caught_stealing with a baserunner that wasnt."""


class InvalidPickOff(GameException):
    """User called a pickoff with a baserunner that wasnt."""


class TooManyOuts(GameException):
    """
    User called double_play or triple_play with too many outs.
    Or they called inning.out and ended up with 3 outs, which should
    never happen.

    """


class NoNameException(GameException):
    """Player or Team instantiated with no name."""


class NoJerseyException(GameException):
    """Player instantiated with no jersey number."""


class BadPositionException(GameException):
    """Player generated with bad position."""


class InvalidBase(GameException):
    """Tried to convert a base with an invalid string."""


class BadHandednessException(GameException):
    """Tried to make a Player with an invalid throws or bats value."""
