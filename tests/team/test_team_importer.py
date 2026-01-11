# # tests/team/test_team_importer.py
# """
# What we test (behavior)
# Core responsibilities
# Validates CSV path
# Handles existing vs new team logic
# Delegates correctly to repositories
# Creates Player objects from rows
# Commits on success
# Rolls back on failure
# Returns a populated Team

# What we do not test
# CSV parsing correctness (stdlib)
# SHA256 correctness (stdlib)
# Repository SQL internals (repo tests handle that)

# Test setup philosophy

# We will:
# Mock repositories
# Mock Player.from_row
# Mock file + CSV
# Inject a fake connection
# Patch at import location, not definition
# """

# import io
# import pytest
# from unittest.mock import MagicMock, patch
# from pathlib import Path

# from src.team.team_importer import TeamImporter

# @pytest.fixture
# def mock_conn():
#     conn = MagicMock()
#     conn.execute = MagicMock()
#     conn.commit = MagicMock()
#     conn.rollback = MagicMock()
#     return conn

# @pytest.fixture
# def importer(mock_conn):
#     importer = TeamImporter(mock_conn)
#     importer.player_repo = MagicMock()
#     importer.team_repo = MagicMock()
#     return importer

# @pytest.fixture
# def fake_csv():
#     return (
#         "first_name,last_name,bats,throws\n"
#         "Mike,Trout,R,R\n"
#         "Shohei,Ohtani,L,R\n"
#     )

# def test_import_csv_missing_file(importer):
#     with pytest.raises(FileNotFoundError):
#         importer.import_csv(
#             league_id="L1",
#             path="missing.csv",
#             city="LA",
#             mascot="Angels",
#         )
