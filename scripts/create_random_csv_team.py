# scripts/create_random_csv_team.py

from src.team.team_factory import TeamFactory
from src.io.player_csv_exporter import PlayerCSVExporter

tf = TeamFactory()
home_team = tf.generate_team(city="Team", mascot="One")

exporter = PlayerCSVExporter()
filename = "team_one.csv"
exporter.write(home_team, filename)
print(f"Created {filename}")
