from src.team.team_factory import TeamFactory
from src.team.team_exporter import TeamCSVExporter

tf = TeamFactory()

tr = tf.generate_team(city="Portland", mascot="Reign")
TeamCSVExporter.write(tr, "portland_reign.csv")
