# src/league/league_modes.py
#
# League modes and the rules each one plays by.
#
# A mode carries two things: the settings the create-league form fills in when
# the mode is picked (the GM can still change them), and the rules the game
# enforces for the whole life of the league (they can't be changed).

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LeagueMode:
    key: str
    label: str
    # Settings the create form switches to when this mode is picked. Settings
    # left out keep whatever the form already has.
    form_presets: dict[str, int] = field(default_factory=dict)
    injuries_enabled: bool = True
    # Trades don't exist yet. Check trades_allowed() before offering or
    # accepting one once they do.
    trades_enabled: bool = True


BLITZ = LeagueMode(
    key="blitz",
    label="Speed Blitz",
    form_presets={
        "sim_period_days": 30,
        "decision_window_sec": 30,
        "num_seasons": 5,
    },
    injuries_enabled=False,
    trades_enabled=False,
)

LONGFORM = LeagueMode(key="longform", label="Long Form")

LEAGUE_MODES: dict[str, LeagueMode] = {m.key: m for m in (BLITZ, LONGFORM)}

DEFAULT_MODE = BLITZ.key


def get_mode(mode: str | None) -> LeagueMode:
    """The rules for a league's mode. Leagues without one are blitz."""
    if not mode:
        return LEAGUE_MODES[DEFAULT_MODE]
    if mode not in LEAGUE_MODES:
        raise ValueError(f"Unknown league mode '{mode}'.")
    return LEAGUE_MODES[mode]


def injuries_allowed(mode: str | None) -> bool:
    return get_mode(mode).injuries_enabled


def trades_allowed(mode: str | None) -> bool:
    return get_mode(mode).trades_enabled
