# src/api/services/records/defs.py
"""
What the single-game and streak records track, and the rules for each.

Single games (regular season, one player): a performance is kept in
record_feats when it's at least ``keep`` and good enough for the league's
top five or its club's top five. Once kept it's never dropped, so "done N
times" and who held a record before are always there.

Floors: a league with no backstory has nobody's games to start from, so its
book opens at a league mark about as good as one season's best (measured on
engine seasons), which a player has to beat, not tie. A backstory league
starts from its replayed seasons instead (replay.py).

Streaks follow MLB's conventions:
  hit      a game with a hit extends it; one with an at-bat or a sacrifice
           fly and no hit ends it; a game of walks, hit by pitches and
           sacrifice bunts (or pinch running) leaves it alone
  hr       games with a home run, in games he came to the plate
  onbase   games reaching on a hit, walk or hit by pitch, in games he came
           to the plate
  pwin     decisions that were wins: no-decisions leave it alone
  twin     a club's wins in a row (regular season)
  tloss    a club's losses in a row
A streak stays inside one regular season.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GameStat:
    key: str
    column: str  # player_game_stats column
    label: str
    keep: int  # smallest performance worth keeping
    floor: int  # the league mark without a backstory
    pitching: bool = False


GAME_STATS = [
    GameStat("H", "bat_hits", "Hits", 4, 5),
    GameStat("HR", "bat_home_runs", "Home runs", 2, 3),
    GameStat("2B", "bat_doubles", "Doubles", 2, 3),
    GameStat("3B", "bat_triples", "Triples", 2, 2),
    GameStat("R", "bat_runs", "Runs", 3, 4),
    GameStat("RBI", "bat_rbi", "RBI", 5, 7),
    GameStat("SB", "bat_stolen_bases", "Stolen bases", 3, 4),
    GameStat("BB", "bat_walks", "Walks", 3, 4),
    GameStat("K", "bat_strike_outs", "Strikeouts (batting)", 4, 4),
    GameStat("PK", "pitch_strike_outs", "Strikeouts (pitching)", 10, 12, True),
]
GAME_BY_KEY = {s.key: s for s in GAME_STATS}

# A single game this good is news even when it only ties the record.
RARE_TIE = {"HR": 4, "PK": 18, "H": 7, "RBI": 10}


@dataclass(frozen=True)
class StreakStat:
    key: str
    label: str
    keep: int
    floor: int
    team: bool = False


STREAKS = [
    StreakStat("hit", "Hitting streak", 10, 25),
    StreakStat("hr", "Home run streak", 3, 4),
    StreakStat("onbase", "On-base streak", 15, 45),
    StreakStat("pwin", "Pitcher win streak", 5, 11),
    StreakStat("twin", "Winning streak", 6, 12, team=True),
    StreakStat("tloss", "Losing streak", 6, 12, team=True),
]
STREAK_BY_KEY = {s.key: s for s in STREAKS}
PLAYER_STREAKS = [s for s in STREAKS if not s.team]
TEAM_STREAKS = [s for s in STREAKS if s.team]

EXTEND, BREAK, SKIP = 1, -1, 0


def hitter_outcomes(g: dict) -> dict[str, int]:
    """What one game does to each of a hitter's streaks. ``g`` has ab, h,
    hr, bb, hbp, sf."""
    pa = g["ab"] + g["bb"] + g["hbp"] + g["sf"]
    if g["h"] > 0:
        hit = EXTEND
    elif g["ab"] > 0 or g["sf"] > 0:
        hit = BREAK
    else:
        hit = SKIP
    if pa == 0:
        return {"hit": hit, "hr": SKIP, "onbase": SKIP}
    return {
        "hit": hit,
        "hr": EXTEND if g["hr"] > 0 else BREAK,
        "onbase": EXTEND if g["h"] + g["bb"] + g["hbp"] > 0 else BREAK,
    }


def pitcher_outcome(win: int, loss: int) -> int:
    return EXTEND if win else BREAK if loss else SKIP


@dataclass
class Run:
    """A streak in progress: ``length`` games from ``start`` to ``last``."""

    length: int = 0
    start: str | None = None
    last: str | None = None
    start_game: str | None = None
    last_game: str | None = None
    team_id: str | None = None

    def feed(self, outcome: int, date: str, game_id: str | None, team_id=None):
        """Apply one game. Returns the run it ended (a copy), if any."""
        if outcome == EXTEND:
            if self.length == 0:
                self.start, self.start_game = date, game_id
            self.length += 1
            self.last, self.last_game = date, game_id
            if team_id:
                self.team_id = team_id
            return None
        if outcome == BREAK and self.length:
            ended = Run(**self.__dict__)
            self.length, self.start, self.last = 0, None, None
            self.start_game = self.last_game = None
            return ended
        return None
