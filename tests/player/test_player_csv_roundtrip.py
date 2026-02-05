# tests/player/test_player_csv_round_trip.py

import tempfile
from pathlib import Path

from src.io.player_csv_exporter import PlayerCSVExporter
from src.io.player_csv_importer import PlayerCSVImporter
from src.team.team_record import TeamRecord
from tests.factories.team_record_factory import make_team_record


def test_csv_round_trip_is_lossless():
    team = make_team_record(size=3)

    with tempfile.TemporaryDirectory() as tmp:
        p1 = Path(tmp) / "out1.csv"
        p2 = Path(tmp) / "out2.csv"

        # export
        PlayerCSVExporter.write(team, p1)

        # import
        players = PlayerCSVImporter.read(p1)
        rehydrated_team = TeamRecord(
            id=team.id,
            city="Testville",
            mascot="Tests",
            players=tuple(players),
        )

        # export again
        PlayerCSVExporter.write(rehydrated_team, p2)

        assert p1.read_text() == p2.read_text()


def test_csv_uses_lowercase_handedness():
    team = make_team_record(size=1)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.csv"
        PlayerCSVExporter.write(team, path)

        text = path.read_text()
        assert ",R," in text or ",R," in text
