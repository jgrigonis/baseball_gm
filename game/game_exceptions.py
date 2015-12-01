"""Exceptions class for the baseball simulator."""


class GameException(Exception):
    """Base class for exceptions in this module."""
    def __init__(self):
        super(Exception, self).__init__(self)


class NotEnoughRunnersOnBase(GameException):
    """Not enough runners on base."""
    def __init__(self, msg=None):
        if msg:
            print msg


class NoRunnerToAdvance(GameException):
    """User tried to advance a runner from an exmpty base."""
    def __init__(self, msg=None):
        if msg:
            print msg


class AdvanceToOccupiedBase(GameException):
    """User tried to advance a runner to an occupied base."""
    def __init__(self, msg=None):
        if msg:
            print msg


class AdvancePastOccupiedBase(GameException):
    """User tried to advance a runner past an occupied base."""
    def __init__(self, msg=None):
        if msg:
            print msg


class BadSacrifice(GameException):
    """User tried to call sacrifice method with 2 outs."""
    def __init__(self, msg=None):
        if msg:
            print msg


class ErrorCalledWithTooManyAdvances(GameException):
    """User called the error method with too many parameters."""
    def __init__(self, msg=None):
        if msg:
            print msg


class InvalidAdvance(GameException):
    """User called the error method with an invalid baserunner advance."""
    def __init__(self, msg=None):
        if msg:
            print msg


class InvalidSteal(GameException):
    """User called a steal, or caught_stealing with a baserunner that wasnt."""
    def __init__(self, msg=None):
        if msg:
            print msg


class InvalidPickOff(GameException):
    """User called a pickoff with a baserunner that wasnt."""
    def __init__(self, msg=None):
        if msg:
            print msg


class TooManyOuts(GameException):
    """User called double_play or triple_play with too many outs.
    Or they called inning.out and ended up with 3 outs, which should
    never happen.

    """
    def __init__(self, msg=None):
        if msg:
            print msg


class NoNameException(GameException):
    """Player or Team instantiated with no name."""
    def __init__(self, msg=None):
        if msg:
            print msg


class NoJerseyException(GameException):
    """Player instantiated with no jersey number."""
    def __init__(self, msg=None):
        if msg:
            print msg
