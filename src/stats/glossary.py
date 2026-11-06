# src/stats/glossary.py
"""
One-line explanations of every stat the Stats and Leaders tabs show, for
their hover (or tap) tips. A label can mean something different for
hitters, pitchers and fielders (K, BB, H, G), so each has its own list.
"""

from __future__ import annotations

BAT = {
    "G": "Games played",
    "AB": "At-bats: plate appearances that don't end in a walk, hit by pitch, sacrifice or catcher's interference",
    "H": "Hits",
    "2B": "Doubles",
    "3B": "Triples",
    "HR": "Home runs",
    "RBI": "Runs batted in: runners who scored because of his plate appearance",
    "R": "Runs scored",
    "BB": "Walks",
    "K": "Strikeouts",
    "SB": "Stolen bases",
    "AVG": "Batting average: hits per at-bat",
    "OBP": "On-base percentage: how often he reaches on a hit, walk or hit by pitch",
    "SLG": "Slugging percentage: total bases per at-bat (a single is 1, a home run 4)",
    "OPS": "On-base plus slugging: OBP + SLG, a quick all-round hitting number",
    "AB/K": "At-bats per strikeout; higher means he puts the ball in play more",
    "HR/AB": "Home runs per at-bat",
    "AB/HR": "At-bats per home run; lower is more power",
    "BB/K": "Walks per strikeout; above 1 means he walks more than he strikes out",
    "wOBA": "Weighted on-base average: every way of reaching base, weighted by how many runs it is worth.",
    "wRC+": "Runs created per plate appearance against the league; 100 is average, 120 is 20% better",
    "OPS+": "OBP and SLG against the league; 100 is average, 120 is 20% better",
    "ISO": "Isolated power: SLG minus AVG, the extra bases he gets per at-bat",
    "BABIP": "Batting average on balls in play, not counting home runs and strikeouts. Far from .290 often means luck",
    "K%": "Strikeouts per plate appearance",
    "BB%": "Walks per plate appearance",
    "Def": "Defensive runs saved against an average fielder at his main position: mostly his defense rating there, plus plays made, errors avoided and (catchers) runners thrown out",
    "WAR": "Wins above replacement: batting, base stealing, position and defense, against a replacement-level player (regular season). 2 is a solid starter, 5 an All-Star",
    "WPA": "Win probability added: how much his plate appearances raised (or lowered) his team's chance of winning, added up. A big hit in the 9th counts far more than one in a blowout. +3 is an excellent season",
    "RE24": "Runs added: how much his plate appearances changed the runs his team could expect that inning, from the runners on and outs, plus the runs that scored. 0 is average",
}

PIT = {
    "G": "Games pitched",
    "GS": "Games started",
    "CG": "Complete games: he pitched the whole game",
    "SHO": "Shutouts: complete games without allowing a run",
    "NH": "No-hitters",
    "W": "Wins",
    "L": "Losses",
    "SV": "Saves: finished a close win without giving up the lead",
    "HLD": "Holds: kept a save-situation lead before handing the game to another reliever",
    "IP": "Innings pitched (.1 and .2 are one and two outs)",
    "H": "Hits allowed",
    "ER": "Earned runs: runs allowed that didn't come from errors",
    "BB": "Walks allowed",
    "K": "Strikeouts",
    "HR": "Home runs allowed",
    "ERA": "Earned run average: earned runs allowed per nine innings",
    "WHIP": "Walks plus hits per inning pitched",
    "BB/9": "Walks per nine innings",
    "HR/9": "Home runs allowed per nine innings",
    "K/9": "Strikeouts per nine innings",
    "FIP": "Fielding-independent pitching: an ERA from only strikeouts, walks, hit batters and home runs, the things a pitcher controls",
    "ERA+": "League ERA over his ERA; 100 is average, 150 is 50% better",
    "K%": "Strikeouts per batter faced",
    "BB%": "Walks per batter faced",
    "WAR": "Wins above replacement: runs saved against a replacement-level pitcher, half by FIP and half by ERA (regular season)",
    "WPA": "Win probability added: how much he raised his team's chance of winning, added up over every batter he faced. Escaping a late jam counts far more than mop-up work",
    "RE24": "Runs saved: how much the batters he faced lowered the runs the other team could expect that inning, from the runners on and outs. 0 is average",
}

FIELD = {
    "Pos": "Position",
    "G": "Games played at this position",
    "PO": "Putouts: outs he recorded himself (a catch, a tag, a force at his base)",
    "A": "Assists: throws or deflections that led to an out",
    "E": "Errors",
    "DP": "Double plays he took part in",
    "TP": "Triple plays he took part in",
    "PB": "Passed balls: pitches a catcher should have caught that let runners move up",
    "PB/G": "Passed balls per game",
    "FPCT": "Fielding percentage: (putouts + assists) / (putouts + assists + errors)",
    "Def runs": BAT["Def"],
}

_KINDS = {"bat": BAT, "pit": PIT, "field": FIELD}


def tip(kind: str, label: str) -> str:
    """The explanation of `label` ("bat", "pit" or "field"), or "". A
    position in front ("SS FPCT") is skipped."""
    table = _KINDS[kind]
    if label in table:
        return table[label]
    _, _, rest = label.partition(" ")
    return table.get(rest, "")


def tag(cards: list[dict], kind: str) -> list[dict]:
    """Leaders cards with their "tip" filled in."""
    for c in cards:
        c.setdefault("tip", tip(kind, c["label"]))
    return cards
