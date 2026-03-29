# scripts/cli_game_runner.py
"""
This script is for running an entire league simulation for a 
number of years.

The options needed:

The db file to store the data in. (default to cli.db)
DB files are always stored in the LEAGUE_FILE_LOC imported from locations.py

The manifest file to get teams from
manifest file location also imported

The number of seasons to run default to 1

It should be able to pick up a partally run sim and continue

It should be able to start with a seed for reproducibility

optionally destroy database (only your own)
optionally destroy all log files
optionally destroy team_files (only your own)
optionally destroy all temp_files

create team_files in a a uuid subdir under year

create more seasons of manifests from a single example
create_more_seasons.py gets subsumed and deleted


"""

