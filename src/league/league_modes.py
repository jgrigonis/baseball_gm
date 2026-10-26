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
    # One or two sentences on how the mode plays, for the lobby's hover help.
    description: str = ""
    # Settings the create form switches to when this mode is picked. Settings
    # left out keep whatever the form already has.
    form_presets: dict[str, int] = field(default_factory=dict)
    injuries_enabled: bool = True
    # Trades don't exist yet. Check trades_allowed() before offering or
    # accepting one once they do.
    trades_enabled: bool = True
    # Blitz-style leagues run a preference-list draft and play off the 40-man
    # roster; long form drafts interactively and plays off the 26-man.
    blitz_style: bool = False


BLITZ = LeagueMode(
    key="blitz",
    label="Blitz",
    description=(
        "The draft runs from preference lists each GM ranks ahead of time, and "
        "teams play off the full 40-man roster. Injuries are on."
    ),
    # The form's own defaults, so switching back from speed blitz restores them.
    form_presets={
        "sim_period_days": 3,
        "decision_window_sec": 120,
        "num_seasons": 10,
    },
    blitz_style=True,
)

SPEED_BLITZ = LeagueMode(
    key="speed_blitz",
    label="Speed Blitz",
    description=(
        "A faster Blitz: preference-list draft and 40-man rosters, with no "
        "injuries or trades."
    ),
    form_presets={
        "sim_period_days": 30,
        "decision_window_sec": 30,
        "num_seasons": 5,
    },
    injuries_enabled=False,
    trades_enabled=False,
    blitz_style=True,
)

LONGFORM = LeagueMode(
    key="longform",
    label="Long Form",
    description=(
        "GMs draft one pick at a time, and teams play off the 26-man roster."
    ),
)

LEAGUE_MODES: dict[str, LeagueMode] = {m.key: m for m in (BLITZ, SPEED_BLITZ, LONGFORM)}

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


def is_blitz_style(mode: str | None) -> bool:
    return get_mode(mode).blitz_style
