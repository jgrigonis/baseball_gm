# src/team/team_in_game_factory.py
from src.team.team_in_game import TeamInGame
from src.team.team_record import TeamRecord

class TeamInGameFactory:
    @staticmethod
    def from_record(record: TeamRecord) -> TeamInGame:
        team = TeamInGame(record)
        return team
