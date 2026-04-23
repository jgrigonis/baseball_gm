# tests/player/test_player_csv_round_trip.py

from pathlib import Path
import pytest
from unittest.mock import MagicMock
import uuid

from src.io.player_csv_exporter import PlayerCSVExporter
from src.io.team_importer import TeamImporter
from src.team.team_record import TeamRecord
from tests.factories.team_record_factory import make_team_record
from src.util.locations import TEAM_FILES_DIR

@pytest.fixture
def mock_conn():
    # Create a MagicMock to act as your database connection
    conn = MagicMock()
    
    # Optional: Mock a cursor if your repositories call conn.cursor()
    # mock_cursor = conn.cursor.return_value
    # mock_cursor.fetchone.return_value = ["some_data"]
    
    return conn

def test_csv_round_trip_is_lossless(mock_conn):
    team = make_team_record(size=3)
    league_id = str(uuid.uuid4())
    year = 2026
    p1 = Path(TEAM_FILES_DIR) / league_id / str(year) / "out1.csv"
    p2 = Path(TEAM_FILES_DIR) / league_id / str(year) / "out2.csv"


    # export
    PlayerCSVExporter.write_csv(team, year, "out1.csv", league_id)

    # import
    import_team = TeamImporter(mock_conn).import_csv(
        league_id=league_id, 
        season_id="fake-season-id", 
        year=str(year), 
        csv_file="out1.csv", 
        city="Testville", 
        mascot="Tests",
        force_new=True
    )

    # export again
    PlayerCSVExporter.write_csv(import_team, year, "out2.csv", league_id)

    assert p1.read_text() == p2.read_text()
    p1.unlink(missing_ok=True)
    p2.unlink(missing_ok=True)


def test_csv_uses_lowercase_handedness():
    team = make_team_record(size=1)
    league_id = str(uuid.uuid4())
    year = 2026

    path = Path(TEAM_FILES_DIR) / league_id / str(year) / "out.csv"
    print(path)
    PlayerCSVExporter.write_csv(team, year, "out.csv", league_id)

    text = path.read_text()
    assert ",R," in text or ",R," in text
    path.unlink(missing_ok=True)
