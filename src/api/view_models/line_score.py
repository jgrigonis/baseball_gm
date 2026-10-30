# src/api/view_models/line_score.py
"""
The game panel's scoreboard: each team's runs by inning in number tiles,
then R/H/E, and a one-line headline picked from what happened in the game.

Games played before line scores were saved have no runs by inning; they get
the R/H/E tiles and a headline from the final score and box score alone.
"""

from __future__ import annotations

from src.team.colors import colors_for


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _padded(runs: list[int] | None, n: int) -> list[int]:
    runs = list(runs or [])
    return runs + [0] * (n - len(runs))


def line_score(game: dict, hits: dict[str, int], errors: dict[str, int]) -> dict:
    """
    The scoreboard rows for a completed game.

    Returns {"innings": [1, 2, ...], "rows": [away_row, home_row]}, where each
    row has the team's code, colors, inning cells (strings: runs, or "X" for
    a bottom half the home team didn't need), R, H, E and whether it won.
    "innings" is empty when the game has no saved line score.
    """
    line = game.get("line_score") or None
    n = max(game.get("innings_played") or 9, 9)
    if line:
        n = max(n, len(line.get("away", [])), len(line.get("home", [])))
        away = _padded(line.get("away"), n)
        home = _padded(line.get("home"), n)
        away_cells = [str(r) for r in away]
        home_cells = [str(r) for r in home]
        # The home team led going into the bottom of the last inning, so it
        # never batted.
        if game["home_score"] - home[-1] > game["away_score"]:
            home_cells[-1] = "X"
        innings = list(range(1, n + 1))
    else:
        away_cells = home_cells = []
        innings = []

    rows = []
    for side, cells in (("away", away_cells), ("home", home_cells)):
        team_id = game[f"{side}_team_id"]
        colors = colors_for(game[f"{side}_city"], game[f"{side}_mascot"])
        rows.append(
            {
                "team_id": team_id,
                "city": game[f"{side}_city"],
                "mascot": game[f"{side}_mascot"],
                "code": colors.code,
                "cells": cells,
                "R": game[f"{side}_score"],
                "H": hits.get(team_id, 0),
                "E": errors.get(team_id, 0),
                "won": game.get("winner_id") == team_id,
            }
        )
    return {"innings": innings, "rows": rows}


def _largest_deficit(away: list[int], home: list[int], winner: str) -> int:
    """How far the winner trailed at its worst, checked after each half."""
    a = h = worst = 0
    for top, bottom in zip(away, home):
        a += top
        worst = max(worst, (a - h) if winner == "home" else (h - a))
        h += bottom
        worst = max(worst, (a - h) if winner == "home" else (h - a))
    return worst


def _number_word(n: int) -> str:
    return {2: "two", 3: "three", 4: "four", 5: "five"}.get(n, str(n))


def headline(
    game: dict,
    bat_rows: list[dict],
    pit_rows: list[dict],
    no_hitters: list[dict],
) -> str:
    """A one-line headline for a completed game, from its most notable
    moment: a no-hitter, a walk-off, a comeback, a shutout, a big day from
    one player, a rout, extra innings, or simply who beat whom."""
    home_won = game["home_score"] > game["away_score"]
    win_side, lose_side = ("home", "away") if home_won else ("away", "home")
    winner = game[f"{win_side}_mascot"]
    loser = game[f"{lose_side}_mascot"]
    win_id = game[f"{win_side}_team_id"]
    w_runs, l_runs = game[f"{win_side}_score"], game[f"{lose_side}_score"]
    score = f"{w_runs}-{l_runs}"
    innings = game.get("innings_played") or 9

    for nh in no_hitters:
        if nh["combined"]:
            return f"{winner} combine to no-hit the {loser}"
        return f"{nh['pitchers'].split('. ', 1)[-1]} no-hits the {loser}"

    line = game.get("line_score") or None
    if line:
        n = max(innings, len(line.get("away", [])), len(line.get("home", [])))
        away = _padded(line.get("away"), n)
        home = _padded(line.get("home"), n)
        if (
            home_won
            and home[-1] > 0
            and game["home_score"] - home[-1] <= game["away_score"]
        ):
            return f"{winner} walk it off in the {_ordinal(n)}, {score}"
        deficit = _largest_deficit(away, home, win_side)
        if deficit >= 3:
            return f"{winner} rally from {_number_word(deficit)} down to beat the {loser}, {score}"

    win_pitchers = [p for p in pit_rows if p["team_id"] == win_id]
    if l_runs == 0:
        if len(win_pitchers) == 1:
            p = win_pitchers[0]
            return f"{p['last_name']} blanks the {loser} on a complete game, {score}"
        return f"{winner} blank the {loser}, {score}"

    win_bats = [b for b in bat_rows if b["team_id"] == win_id]
    big_hr = max(win_bats, key=lambda b: b["HR"] or 0, default=None)
    if big_hr and (big_hr["HR"] or 0) >= 2:
        return (
            f"{big_hr['last_name']}'s {_number_word(big_hr['HR'])} homers "
            f"power the {winner} past the {loser}, {score}"
        )
    big_k = max(win_pitchers, key=lambda p: p.get("K") or 0, default=None)
    if big_k and (big_k.get("K") or 0) >= 10:
        return f"{big_k['last_name']} fans {big_k['K']} as the {winner} top the {loser}, {score}"
    big_h = max(win_bats, key=lambda b: b["H"] or 0, default=None)
    if big_h and (big_h["H"] or 0) >= 4:
        return (
            f"{big_h['last_name']} goes {big_h['H']}-for-{big_h['AB']} "
            f"as the {winner} beat the {loser}, {score}"
        )

    if w_runs - l_runs >= 8:
        return f"{winner} rout the {loser}, {score}"
    if innings > 9:
        return f"{winner} outlast the {loser} in {innings}, {score}"
    if w_runs - l_runs == 1:
        return f"{winner} edge the {loser}, {score}"
    return f"{winner} beat the {loser}, {score}"
