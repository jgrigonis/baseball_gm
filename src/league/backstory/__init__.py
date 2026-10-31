# src/league/backstory/__init__.py
"""
League backstory (plans/league-backstory.md): when a league starts, it gets
a few past seasons generated from its rosters, so there's a defending
champion, standings and playoff results to look back on, veterans with
career lines and All-Star selections, and players who have since retired.

The seasons are generated, not played: playing one full season with the
engine takes minutes and over 100 MB, so instead each team's strength and
each player's stat line come from their ratings, using coefficients fitted
to seasons the engine did play (calibration.py, refitted by
scripts/calibrate_backstory.py). Every game still gets a score, so the
standings, playoff bracket and History pages read past seasons the same
way as played ones. There are no box scores and no All-Star Game.

  rewind.py    ratings at younger ages
  careers.py   who played where each year, and the retired veterans
  season.py    one season: playing time, stat lines, games, playoffs
  service.py   runs it for a league and saves it
"""
